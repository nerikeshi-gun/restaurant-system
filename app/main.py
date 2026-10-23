from contextlib import asynccontextmanager
import csv
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import BASE_DIR, settings
from app.database import Base, SessionLocal, engine, get_db
from app.migrations import ensure_sqlite_schema
from app.models import DiningTable, MenuAlias, MenuCategory, MenuItem, MenuItemModifierGroup, MenuVersionItem, Message, ModifierOption, Order, OrderItem, OrderItemModifier, ServiceRequest, Store, TableSession
from app.realtime import manager
from app.schemas import (
    AvailabilityUpdate,
    AdminMenuItemCreate,
    AdminMenuItemUpdate,
    AdminModifierGroupCreate,
    AdminModifierGroupUpdate,
    AdminModifierOptionCreate,
    AdminModifierOptionUpdate,
    DisplayNumberReset,
    InterpretRequest,
    InterpretResponse,
    KitchenItemStatusUpdate,
    MenuCategoryCreate,
    MenuCategoryUpdate,
    MenuItemCategoryUpdate,
    MessageCreate,
    OrderCreate,
    ResolveOrderRequest,
    ResolveOrderResponse,
    ServiceRequestCreate,
    SharedItemCancel,
    SharedItemCreate,
    SharedItemUpdate,
    SharedOrderConfirm,
    StatusUpdate,
    StoreSettingsUpdate,
    TableResetRequest,
)
from app.seed import seed_database
from app.services.interpreter import interpret_input
from app.services.ai_order import resolve_order
from app.services.menu import load_available_menu, to_menu_view
from app.services.menu_catalog import import_menu_csv, load_current_menu_version, snapshot_current_menu
from app.services.menu_excel import build_menu_workbook, import_menu_workbook
from app.services.orders import OrderValidationError, calculate_bill, create_order
from app.services.pos import pos_adapter
from app.services.shared_orders import (
    SharedOrderError,
    VersionConflict,
    add_shared_item,
    cancel_shared_item,
    confirm_shared_order,
    get_or_create_shared_order,
    get_shared_order_for_table,
    kitchen_shared_snapshot,
    order_view,
    reset_display_numbers,
    resolve_cancel_request,
    update_kitchen_status,
    update_shared_item,
)
from app.services.translation import translator
from app.default_translations import backfill_default_menu_translations


def order_dict(order: Order) -> dict:
    return {
        "id": order.id,
        "session_id": order.session_id,
        "status": order.status,
        "original_text": order.original_text,
        "created_at": order.created_at.isoformat(),
        "items": [
            {
                "id": item.id,
                "name": item.menu_name_snapshot,
                "unit_price": item.unit_price_snapshot,
                "quantity": item.quantity,
                "line_total": item.line_total,
                "modifiers": [modifier.display_name for modifier in item.modifiers],
            }
            for item in order.items
        ],
    }


def request_dict(item: ServiceRequest) -> dict:
    return {
        "id": item.id,
        "session_id": item.session_id,
        "request_type": item.request_type,
        "message": item.message,
        "status": item.status,
        "created_at": item.created_at.isoformat(),
    }


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_sqlite_schema(engine)
    with SessionLocal() as db:
        seed_database(db)
        backfill_default_menu_translations(db)
    yield


app = FastAPI(title="飲食店注文システム", version="0.2.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")

DEFAULT_DEVICE_LAYOUT = {"block_order": ["input", "menu", "service"], "order_position": "right"}
DEFAULT_STORE_LAYOUT = {"desktop": DEFAULT_DEVICE_LAYOUT, "tablet": DEFAULT_DEVICE_LAYOUT}


def _valid_device_layout(value: object) -> dict:
    if not isinstance(value, dict):
        value = {}
    block_order = value.get("block_order")
    if not isinstance(block_order, list) or set(block_order) != {"input", "menu", "service"} or len(block_order) != 3:
        block_order = DEFAULT_DEVICE_LAYOUT["block_order"]
    order_position = value.get("order_position") if value.get("order_position") in {"right", "top", "bottom"} else "right"
    return {"block_order": list(block_order), "order_position": order_position}


def _store_context(db: Session) -> tuple[Store, dict]:
    store = db.get(Store, settings.default_store_id)
    if not store:
        store = Store(id=settings.default_store_id, name=settings.restaurant_name)
        db.add(store)
        db.commit()
        db.refresh(store)
    try:
        layout = json.loads(store.ui_layout_json or "{}")
    except json.JSONDecodeError:
        layout = {}
    if not isinstance(layout, dict):
        layout = {}
    # 旧形式はPC・タブレットの両方へ引き継ぐ。
    if "block_order" in layout:
        legacy = _valid_device_layout(layout)
        return store, {"desktop": legacy, "tablet": dict(legacy)}
    return store, {
        "desktop": _valid_device_layout(layout.get("desktop")),
        "tablet": _valid_device_layout(layout.get("tablet")),
    }


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    tables = list(db.scalars(select(DiningTable).where(DiningTable.is_active.is_(True)).order_by(DiningTable.id)))
    store, _ = _store_context(db)
    return templates.TemplateResponse(request, "home.html", {"tables": tables, "restaurant_name": store.name})


@app.get("/setup/local-ca")
def download_local_ca():
    local_app_data = Path(os.environ.get("LOCALAPPDATA", BASE_DIR / "data"))
    certificate = local_app_data / "GreitRestaurantOrder" / "certs" / "restaurant-local-ca.crt"
    if not certificate.exists():
        raise HTTPException(404, "先に setup-https.ps1 を実行してください")
    return FileResponse(
        certificate,
        media_type="application/x-x509-ca-cert",
        filename="restaurant-local-ca-v2.crt",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/staff", response_class=HTMLResponse)
def staff_tables_page(request: Request, db: Session = Depends(get_db)):
    tables = list(db.scalars(select(DiningTable).where(DiningTable.is_active.is_(True)).order_by(DiningTable.id)))
    store, _ = _store_context(db)
    return templates.TemplateResponse(
        request, "staff_tables.html", {"tables": tables, "restaurant_name": store.name}
    )


@app.get("/staff/table/{table_id}", response_class=HTMLResponse)
def staff_order_page(table_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        session, _ = get_shared_order_for_table(db, table_id)
    except SharedOrderError as exc:
        raise HTTPException(404, str(exc)) from exc
    store, _ = _store_context(db)
    response = templates.TemplateResponse(
        request,
        "staff_order.html",
        {"table": session.table, "session": session, "restaurant_name": store.name, "theme_color": store.theme_color},
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/table/{table_number}", response_class=HTMLResponse)
def customer_table_page(table_number: str, request: Request, db: Session = Depends(get_db)):
    table = db.scalar(select(DiningTable).where(DiningTable.number == table_number, DiningTable.is_active.is_(True)))
    if not table:
        raise HTTPException(404, "テーブルが見つかりません")
    store, _ = _store_context(db)
    response = templates.TemplateResponse(
        request,
        "language_select.html",
        {"table": table, "restaurant_name": store.name, "theme_color": store.theme_color, "order_path": f"/table/{table.number}/order"},
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/table/{table_number}/order", response_class=HTMLResponse)
def customer_table_order_page(table_number: str, request: Request, lang: str = "ja", mode: str = "choice", db: Session = Depends(get_db)):
    table = db.scalar(select(DiningTable).where(DiningTable.number == table_number, DiningTable.is_active.is_(True)))
    if not table:
        raise HTTPException(404, "テーブルが見つかりません")
    try:
        session, _ = get_shared_order_for_table(db, table.id)
    except SharedOrderError as exc:
        raise HTTPException(409, str(exc)) from exc
    store, layout = _store_context(db)
    language = lang if lang in {"ja", "en", "zh", "ko", "vi", "ur"} else "ja"
    order_mode = mode if mode in {"voice", "menu"} else "choice"
    order_path = f"/table/{table.number}/order?lang={language}"
    response = templates.TemplateResponse(
        request,
        "order.html",
        {"table": table, "session": session, "actor": "customer", "language": language, "order_mode": order_mode, "order_path": order_path, "voice_path": f"{order_path}&mode=voice", "menu_path": f"{order_path}&mode=menu", "language_path": f"/table/{table.number}", "restaurant_name": store.name, "store_id": settings.default_store_id, "theme_color": store.theme_color, "ui_layout": layout},
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/t/{token}", response_class=HTMLResponse)
def customer_page(token: str, request: Request, db: Session = Depends(get_db)):
    table = db.scalar(select(DiningTable).where(DiningTable.access_token == token, DiningTable.is_active.is_(True)))
    if not table:
        raise HTTPException(404, "テーブルが見つかりません")
    store, _ = _store_context(db)
    response = templates.TemplateResponse(
        request,
        "language_select.html",
        {"table": table, "restaurant_name": store.name, "theme_color": store.theme_color, "order_path": f"/t/{token}/order"},
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/t/{token}/order", response_class=HTMLResponse)
def customer_order_page(token: str, request: Request, lang: str = "ja", mode: str = "choice", db: Session = Depends(get_db)):
    table = db.scalar(select(DiningTable).where(DiningTable.access_token == token, DiningTable.is_active.is_(True)))
    if not table:
        raise HTTPException(404, "テーブルが見つかりません")
    session = db.scalar(
        select(TableSession).where(TableSession.table_id == table.id, TableSession.status.in_(["open", "checkout_requested"]))
    )
    if not session:
        raise HTTPException(409, "このテーブルは利用開始前です")
    store, layout = _store_context(db)
    language = lang if lang in {"ja", "en", "zh", "ko", "vi", "ur"} else "ja"
    order_mode = mode if mode in {"voice", "menu"} else "choice"
    order_path = f"/t/{token}/order?lang={language}"
    response = templates.TemplateResponse(
        request,
        "order.html",
        {"table": table, "session": session, "actor": "customer", "language": language, "order_mode": order_mode, "order_path": order_path, "voice_path": f"{order_path}&mode=voice", "menu_path": f"{order_path}&mode=menu", "language_path": f"/t/{token}", "restaurant_name": store.name, "store_id": settings.default_store_id, "theme_color": store.theme_color, "ui_layout": layout},
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/kitchen", response_class=HTMLResponse)
def kitchen_page(request: Request, db: Session = Depends(get_db)):
    store, _ = _store_context(db)
    return templates.TemplateResponse(request, "kitchen.html", {"restaurant_name": store.name})


@app.get("/admin", response_class=HTMLResponse)
def table_admin_page(request: Request, db: Session = Depends(get_db)):
    store, _ = _store_context(db)
    response = templates.TemplateResponse(request, "table_admin.html", {"restaurant_name": store.name})
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/admin/menu", response_class=HTMLResponse)
def admin_page(request: Request, db: Session = Depends(get_db)):
    store, _ = _store_context(db)
    return templates.TemplateResponse(request, "admin.html", {"restaurant_name": store.name})


@app.get("/admin/menu/new", response_class=HTMLResponse)
def new_menu_item_page(request: Request, db: Session = Depends(get_db)):
    store, _ = _store_context(db)
    return templates.TemplateResponse(
        request,
        "menu_form.html",
        {"restaurant_name": store.name, "item_id": "", "page_title": "メニュー登録"},
    )


@app.get("/admin/menu/{item_id}/edit", response_class=HTMLResponse)
def edit_menu_item_page(item_id: int, request: Request, db: Session = Depends(get_db)):
    if not db.get(MenuItem, item_id):
        raise HTTPException(404, "商品が見つかりません")
    store, _ = _store_context(db)
    return templates.TemplateResponse(
        request,
        "menu_form.html",
        {"restaurant_name": store.name, "item_id": item_id, "page_title": "メニュー編集"},
    )


@app.get("/admin/options", response_class=HTMLResponse)
def modifier_options_page(request: Request, db: Session = Depends(get_db)):
    store, _ = _store_context(db)
    return templates.TemplateResponse(request, "options_admin.html", {"restaurant_name": store.name})


@app.get("/admin/store", response_class=HTMLResponse)
def store_settings_page(request: Request, db: Session = Depends(get_db)):
    store, _ = _store_context(db)
    return templates.TemplateResponse(request, "store_settings.html", {"restaurant_name": store.name})


@app.get("/api/v1/admin/store-settings")
def get_store_settings(db: Session = Depends(get_db)):
    store, layout = _store_context(db)
    return {"store_id": store.id, "name": store.name, "theme_color": store.theme_color, "layout": layout}


@app.patch("/api/v1/admin/store-settings")
async def update_store_settings(payload: StoreSettingsUpdate, db: Session = Depends(get_db)):
    for device_layout in (payload.layout.desktop, payload.layout.tablet):
        if len(device_layout.block_order) != 3 or set(device_layout.block_order) != {"input", "menu", "service"}:
            raise HTTPException(422, "画面の箱は重複なく三つ指定してください")
    store_name = payload.name.strip()
    if not store_name:
        raise HTTPException(422, "店名を入力してください")
    store, _ = _store_context(db)
    store.name = store_name
    store.theme_color = payload.theme_color.lower()
    store.ui_layout_json = json.dumps(payload.layout.model_dump(), ensure_ascii=False)
    db.commit()
    event = {
        "type": "store.settings_changed",
        "data": {
            "store_id": store.id,
            "name": store.name,
            "theme_color": store.theme_color,
            "layout": payload.layout.model_dump(),
        },
    }
    await manager.broadcast_kitchen(event)
    await manager.broadcast_all_customers(event)
    return {"store_id": store.id, "name": store.name, "theme_color": store.theme_color, "layout": payload.layout.model_dump()}


@app.get("/api/v1/menu")
def get_menu(db: Session = Depends(get_db)):
    return [to_menu_view(item) for item in load_available_menu(db, settings.default_store_id)]


@app.get("/api/v1/admin/menu")
def get_admin_menu(db: Session = Depends(get_db)):
    items = list(db.scalars(select(MenuItem).join(MenuCategory).where(MenuItem.is_archived.is_(False)).options(selectinload(MenuItem.category)).order_by(MenuCategory.display_order, MenuItem.display_order, MenuItem.id)))
    return [
        {"id": item.id, "menu_code": item.menu_code, "name": item.name, "category_id": item.category_id, "category": item.category.name, "price": item.price, "is_available": item.is_available, "edit_url": f"/admin/menu/{item.id}/edit"}
        for item in items
    ]


def _admin_menu_item_view(item: MenuItem) -> dict:
    try:
        localized_names = json.loads(item.localized_names_json or "{}")
        if not isinstance(localized_names, dict):
            localized_names = {}
    except (TypeError, ValueError):
        localized_names = {}
    return {
        "id": item.id,
        "menu_code": item.menu_code or "",
        "category_id": item.category_id,
        "name": item.name,
        "short_name": item.short_name,
        "reading": item.reading,
        "aliases": [alias.alias for alias in item.aliases],
        "localized_names": localized_names,
        "price": item.price,
        "display_order": item.display_order,
        "size_label": item.size_label,
        "set_contents": item.set_contents,
        "is_available": item.is_available,
        "modifier_groups": [
            {"group_id": link.group_id, "required": link.required, "display_order": link.display_order}
            for link in sorted(item.modifier_groups, key=lambda value: (value.display_order, value.id or 0))
        ],
    }


def _validate_admin_menu_item(db: Session, payload: AdminMenuItemCreate, item_id: int | None = None) -> tuple[MenuCategory, str]:
    category = db.get(MenuCategory, payload.category_id)
    if not category or not category.is_menu_category:
        raise HTTPException(422, "カテゴリが見つかりません")
    menu_code = payload.menu_code.strip()
    duplicate = db.scalar(
        select(MenuItem.id).where(
            MenuItem.store_id == settings.default_store_id,
            MenuItem.menu_code == menu_code,
            *([MenuItem.id != item_id] if item_id else []),
        )
    )
    if duplicate:
        raise HTTPException(409, "同じ商品コードが既にあります")
    return category, menu_code


def _apply_admin_menu_payload(db: Session, item: MenuItem, payload: AdminMenuItemCreate, menu_code: str) -> None:
    item.menu_code = menu_code
    item.category_id = payload.category_id
    item.name = payload.name.strip()
    item.short_name = payload.short_name.strip() or item.name
    item.reading = payload.reading.strip()
    item.price = payload.price
    item.display_order = payload.display_order
    item.size_label = payload.size_label.strip()
    item.set_contents = payload.set_contents.strip()
    localized_names = {
        code: value.strip()
        for code, value in payload.localized_names.items()
        if code in {"ja", "en", "zh", "ko", "vi", "ur"} and value.strip()
    }
    localized_names["ja"] = item.name
    item.localized_names_json = json.dumps(localized_names, ensure_ascii=False)
    item.is_available = payload.is_available
    aliases = list(dict.fromkeys(value.strip() for value in payload.aliases if value.strip()))
    item.aliases = [MenuAlias(alias=value) for value in aliases]
    links = []
    for value in {link.group_id: link for link in payload.modifier_groups}.values():
        group = db.get(MenuCategory, value.group_id)
        if not group or not group.is_option_group:
            raise HTTPException(422, "選択肢グループが見つかりません")
        links.append(MenuItemModifierGroup(group_id=value.group_id, required=value.required, display_order=value.display_order))
    item.modifier_groups = links


async def _publish_admin_menu_change(db: Session) -> None:
    version = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f-admin")
    snapshot_current_menu(db, settings.default_store_id, version)
    event = {"type": "menu.availability_changed", "data": {"menu_version": version}}
    await manager.broadcast_kitchen(event)
    await manager.broadcast_all_customers(event)


@app.get("/api/v1/admin/menu/{item_id}")
def get_admin_menu_item(item_id: int, db: Session = Depends(get_db)):
    item = db.scalar(select(MenuItem).where(MenuItem.id == item_id).options(selectinload(MenuItem.aliases), selectinload(MenuItem.modifier_groups)))
    if not item:
        raise HTTPException(404, "商品が見つかりません")
    return _admin_menu_item_view(item)


@app.post("/api/v1/admin/menu")
async def create_admin_menu_item(payload: AdminMenuItemCreate, db: Session = Depends(get_db)):
    _, menu_code = _validate_admin_menu_item(db, payload)
    item = MenuItem(
        store_id=settings.default_store_id,
        category_id=payload.category_id,
        menu_code=menu_code,
        name=payload.name.strip(),
        short_name=payload.short_name.strip() or payload.name.strip(),
        price=payload.price,
    )
    _apply_admin_menu_payload(db, item, payload, menu_code)
    db.add(item)
    db.commit()
    db.refresh(item)
    await _publish_admin_menu_change(db)
    return _admin_menu_item_view(item)


@app.put("/api/v1/admin/menu/{item_id}")
async def update_admin_menu_item(item_id: int, payload: AdminMenuItemUpdate, db: Session = Depends(get_db)):
    item = db.scalar(select(MenuItem).where(MenuItem.id == item_id).options(selectinload(MenuItem.aliases), selectinload(MenuItem.modifier_groups)))
    if not item:
        raise HTTPException(404, "商品が見つかりません")
    _, menu_code = _validate_admin_menu_item(db, payload, item_id)
    _apply_admin_menu_payload(db, item, payload, menu_code)
    db.commit()
    await _publish_admin_menu_change(db)
    return _admin_menu_item_view(item)


def _admin_modifier_group_view(group: MenuCategory) -> dict:
    return {
        "id": group.id,
        "name": group.name,
        "selection_type": group.selection_type,
        "display_order": group.display_order,
        "is_active": group.is_active,
        "options": [
            {
                "id": option.id,
                "name": option.name,
                "price_delta": option.price_delta,
                "is_default": option.is_default,
                "display_order": option.display_order,
                "is_available": option.is_available,
            }
            for option in sorted(group.options, key=lambda value: (value.display_order, value.id))
        ],
    }


@app.get("/api/v1/admin/modifier-groups")
def get_admin_modifier_groups(db: Session = Depends(get_db)):
    groups = list(
        db.scalars(
            select(MenuCategory)
            .where(MenuCategory.is_option_group.is_(True))
            .options(selectinload(MenuCategory.options))
            .order_by(MenuCategory.display_order, MenuCategory.id)
        )
    )
    return [_admin_modifier_group_view(group) for group in groups]


@app.post("/api/v1/admin/modifier-groups")
async def create_admin_modifier_group(payload: AdminModifierGroupCreate, db: Session = Depends(get_db)):
    name = payload.name.strip()
    group = db.scalar(select(MenuCategory).where(MenuCategory.name == name).options(selectinload(MenuCategory.options)))
    if group and group.is_option_group:
        raise HTTPException(409, "同じ選択肢グループ名が既にあります")
    if not group:
        group = MenuCategory(name=name, is_menu_category=False, is_option_group=True)
        db.add(group)
    group.is_option_group = True
    group.selection_type = payload.selection_type
    group.display_order = payload.display_order
    group.is_active = payload.is_active
    db.flush()
    default_used = False
    for option_payload in payload.options:
        option_name = option_payload.name.strip()
        is_default = option_payload.is_default and (payload.selection_type == "multiple" or not default_used)
        default_used = default_used or is_default
        db.add(ModifierOption(group_id=group.id, name=option_name, price_delta=option_payload.price_delta, is_default=is_default, display_order=option_payload.display_order, is_available=option_payload.is_available))
    db.commit()
    group = db.scalar(select(MenuCategory).where(MenuCategory.id == group.id).options(selectinload(MenuCategory.options)))
    return _admin_modifier_group_view(group)


@app.patch("/api/v1/admin/modifier-groups/{group_id}")
async def update_admin_modifier_group(group_id: int, payload: AdminModifierGroupUpdate, db: Session = Depends(get_db)):
    group = db.scalar(select(MenuCategory).where(MenuCategory.id == group_id, MenuCategory.is_option_group.is_(True)).options(selectinload(MenuCategory.options)))
    if not group:
        raise HTTPException(404, "選択肢グループが見つかりません")
    name = payload.name.strip()
    if db.scalar(select(MenuCategory.id).where(MenuCategory.name == name, MenuCategory.id != group_id)):
        raise HTTPException(409, "同じ選択肢グループ名が既にあります")
    group.name = name
    group.selection_type = payload.selection_type
    group.display_order = payload.display_order
    group.is_active = payload.is_active
    db.commit()
    await _publish_admin_menu_change(db)
    return _admin_modifier_group_view(group)


@app.post("/api/v1/admin/modifier-groups/{group_id}/options")
async def create_admin_modifier_option(group_id: int, payload: AdminModifierOptionCreate, db: Session = Depends(get_db)):
    group = db.scalar(select(MenuCategory).where(MenuCategory.id == group_id, MenuCategory.is_option_group.is_(True)).options(selectinload(MenuCategory.options)))
    if not group:
        raise HTTPException(404, "選択肢グループが見つかりません")
    if payload.is_default and group.selection_type == "single":
        for option in group.options:
            option.is_default = False
    option = ModifierOption(group_id=group.id, name=payload.name.strip(), price_delta=payload.price_delta, is_default=payload.is_default, display_order=payload.display_order, is_available=payload.is_available)
    db.add(option)
    db.commit()
    await _publish_admin_menu_change(db)
    db.refresh(option)
    return {"id": option.id, "group_id": group.id}


@app.patch("/api/v1/admin/modifier-options/{option_id}")
async def update_admin_modifier_option(option_id: int, payload: AdminModifierOptionUpdate, db: Session = Depends(get_db)):
    option = db.get(ModifierOption, option_id)
    if not option:
        raise HTTPException(404, "選択肢が見つかりません")
    group = db.scalar(select(MenuCategory).where(MenuCategory.id == option.group_id, MenuCategory.is_option_group.is_(True)).options(selectinload(MenuCategory.options)))
    if payload.is_default and group and group.selection_type == "single":
        for other in group.options:
            other.is_default = other.id == option.id
    option.name = payload.name.strip()
    option.price_delta = payload.price_delta
    option.is_default = payload.is_default
    option.display_order = payload.display_order
    option.is_available = payload.is_available
    db.commit()
    await _publish_admin_menu_change(db)
    return {"id": option.id, "group_id": option.group_id}


@app.delete("/api/v1/admin/modifier-options/{option_id}")
async def delete_admin_modifier_option(option_id: int, db: Session = Depends(get_db)):
    option = db.get(ModifierOption, option_id)
    if not option:
        raise HTTPException(404, "選択ボタンが見つかりません")
    if db.scalar(select(OrderItemModifier.id).where(OrderItemModifier.modifier_option_id == option_id).limit(1)):
        raise HTTPException(409, "注文履歴で使用済みのため削除できません。「使用」を外してください")
    group_id = option.group_id
    db.delete(option)
    db.commit()
    await _publish_admin_menu_change(db)
    return {"deleted": option_id, "group_id": group_id}


@app.delete("/api/v1/admin/modifier-groups/{group_id}")
async def delete_admin_modifier_group(group_id: int, db: Session = Depends(get_db)):
    group = db.scalar(
        select(MenuCategory)
        .where(MenuCategory.id == group_id, MenuCategory.is_option_group.is_(True))
        .options(selectinload(MenuCategory.options))
    )
    if not group:
        raise HTTPException(404, "オプションが見つかりません")
    if db.scalar(select(MenuItemModifierGroup.id).where(MenuItemModifierGroup.group_id == group_id).limit(1)):
        raise HTTPException(409, "メニューで使用中のため削除できません。先に商品のオプション割当を外してください")
    option_ids = [option.id for option in group.options]
    if option_ids and db.scalar(select(OrderItemModifier.id).where(OrderItemModifier.modifier_option_id.in_(option_ids)).limit(1)):
        raise HTTPException(409, "注文履歴で使用済みのため削除できません。「使用する」を外してください")
    for option in list(group.options):
        db.delete(option)
    if group.is_menu_category:
        group.is_option_group = False
        group.selection_type = "single"
        group.is_active = False
    else:
        db.delete(group)
    db.commit()
    await _publish_admin_menu_change(db)
    return {"deleted": group_id}


@app.delete("/api/v1/admin/menu/{item_id}")
async def delete_admin_menu_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(MenuItem, item_id)
    if not item or item.is_archived:
        raise HTTPException(404, "商品が見つかりません")
    item.is_available = False
    item.is_archived = True
    db.commit()
    await _publish_admin_menu_change(db)
    return {"deleted": item_id}


@app.get("/api/v1/admin/menu-categories")
def get_menu_categories(db: Session = Depends(get_db)):
    categories = list(db.scalars(select(MenuCategory).where(MenuCategory.is_menu_category.is_(True)).order_by(MenuCategory.display_order, MenuCategory.id)))
    return [
        {
            "id": category.id,
            "name": category.name,
            "display_order": category.display_order,
            "item_count": len(list(db.scalars(select(MenuItem.id).where(MenuItem.category_id == category.id)))),
        }
        for category in categories
    ]


@app.post("/api/v1/admin/menu-categories")
async def create_menu_category(payload: MenuCategoryCreate, db: Session = Depends(get_db)):
    name = payload.name.strip()
    category = db.scalar(select(MenuCategory).where(MenuCategory.name == name))
    if category and category.is_menu_category:
        raise HTTPException(409, "同じカテゴリ名が既にあります")
    if not category:
        category = MenuCategory(name=name)
        db.add(category)
    category.is_menu_category = True
    category.display_order = payload.display_order
    db.commit()
    db.refresh(category)
    return {"id": category.id, "name": category.name, "display_order": category.display_order, "item_count": 0}


@app.patch("/api/v1/admin/menu-categories/{category_id}")
async def update_menu_category(category_id: int, payload: MenuCategoryUpdate, db: Session = Depends(get_db)):
    category = db.get(MenuCategory, category_id)
    if not category or not category.is_menu_category:
        raise HTTPException(404, "カテゴリが見つかりません")
    name = payload.name.strip()
    duplicate = db.scalar(select(MenuCategory.id).where(MenuCategory.name == name, MenuCategory.id != category_id))
    if duplicate:
        raise HTTPException(409, "同じカテゴリ名が既にあります")
    category.name = name
    category.display_order = payload.display_order
    db.commit()
    await manager.broadcast_all_customers({"type": "menu.availability_changed", "data": {"category_id": category.id}})
    return {"id": category.id, "name": category.name, "display_order": category.display_order}


@app.delete("/api/v1/admin/menu-categories/{category_id}")
async def delete_menu_category(category_id: int, db: Session = Depends(get_db)):
    category = db.get(MenuCategory, category_id)
    if not category:
        raise HTTPException(404, "カテゴリが見つかりません")
    if not category.is_menu_category:
        raise HTTPException(404, "カテゴリが見つかりません")
    if db.scalar(select(MenuItem.id).where(MenuItem.category_id == category_id)):
        raise HTTPException(409, "商品が登録されているカテゴリは削除できません")
    if category.is_option_group:
        category.is_menu_category = False
    else:
        db.delete(category)
    db.commit()
    return {"deleted": category_id}


@app.patch("/api/v1/admin/menu/{item_id}/category")
async def update_menu_item_category(item_id: int, payload: MenuItemCategoryUpdate, db: Session = Depends(get_db)):
    item = db.get(MenuItem, item_id)
    category = db.get(MenuCategory, payload.category_id)
    if not item:
        raise HTTPException(404, "商品が見つかりません")
    if not category or not category.is_menu_category:
        raise HTTPException(404, "カテゴリが見つかりません")
    item.category_id = category.id
    db.commit()
    await manager.broadcast_all_customers({"type": "menu.availability_changed", "data": {"id": item.id}})
    return {"id": item.id, "category_id": category.id, "category": category.name}


@app.get("/api/v1/admin/ai-status")
def get_ai_status():
    provider = settings.llm_provider
    key_configured = bool(settings.gemini_api_key if provider == "gemini" else settings.openai_api_key)
    model = settings.gemini_model if provider == "gemini" else settings.openai_model
    fallback_model = None if provider == "gemini" else settings.openai_fallback_model
    return {
        "enabled": settings.llm_enabled,
        "key_configured": key_configured,
        "model": model,
        "fallback_model": fallback_model,
        "timeout_seconds": settings.llm_timeout_seconds,
        "model_chain": [model, *( [fallback_model] if fallback_model else []), "local_fallback"],
        "active_provider": provider if settings.llm_enabled and key_configured else "local_fallback",
    }


@app.patch("/api/v1/admin/menu/{item_id}/availability")
async def update_availability(item_id: int, payload: AvailabilityUpdate, db: Session = Depends(get_db)):
    item = db.get(MenuItem, item_id)
    if not item:
        raise HTTPException(404, "商品が見つかりません")
    item.is_available = payload.is_available
    version = load_current_menu_version(db, item.store_id)
    if version:
        snapshot = next((value for value in version.items if value.menu_item_id == item.id), None)
        if snapshot:
            snapshot.sold_out = not payload.is_available
    db.commit()
    await manager.broadcast_kitchen({"type": "menu.availability_changed", "data": {"id": item.id}})
    await manager.broadcast_all_customers({"type": "menu.availability_changed", "data": {"id": item.id}})
    return {"id": item.id, "is_available": item.is_available}


@app.post("/api/v1/admin/menu/import-csv")
async def upload_menu_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith((".csv", ".xlsx")):
        raise HTTPException(422, "CSVまたはExcelファイルを選択してください")
    try:
        raw = await file.read()
        return import_menu_workbook(db, raw) if file.filename.lower().endswith(".xlsx") else import_menu_csv(db, raw)
    except (UnicodeDecodeError, ValueError) as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/v1/admin/menu-template.xlsx")
def menu_excel_template(db: Session = Depends(get_db)):
    return Response(
        content=build_menu_workbook(db, current=False),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="menu-template.xlsx"'},
    )


@app.get("/api/v1/admin/menu-current.xlsx")
def current_menu_excel(db: Session = Depends(get_db)):
    return Response(
        content=build_menu_workbook(db, current=True),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="menu-current.xlsx"'},
    )


@app.get("/api/v1/admin/menu-template.csv")
def menu_csv_template():
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["menu_id", "name_ja", "price", "category", "category_order", "available", "alias", "reading", "short_name", "display_order", "size", "set_contents", "toppings", "localized_names"])
    writer.writerow(["M001", "チキンカレー", 1100, "カレー", 10, 1, "チキン|チキンカレー", "ちきんかれー", "チキン", 10, "", "サラダ付き", "辛さ,大,中,小", '{"en":"Chicken Curry"}'])
    writer.writerow(["M002", "マトンマサラ", 1000, "カレー", 10, 1, "マトン", "まとんまさら", "マトン", 20, "", "", "辛さ,大,中,小 / ご飯量,大盛,普通,小盛", '{"en":"Mutton Masala"}'])
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="menu-template.csv"'},
    )


@app.get("/api/v1/admin/menu-current.csv")
def current_menu_csv(db: Session = Depends(get_db)):
    items = list(
        db.scalars(
            select(MenuItem)
            .join(MenuCategory)
            .where(MenuItem.store_id == settings.default_store_id, MenuItem.is_archived.is_(False))
            .options(
                selectinload(MenuItem.category),
                selectinload(MenuItem.aliases),
                selectinload(MenuItem.modifier_groups)
                .selectinload(MenuItemModifierGroup.group)
                .selectinload(MenuCategory.options),
            )
            .order_by(MenuCategory.display_order, MenuItem.display_order, MenuItem.id)
        )
    )
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["menu_id", "name_ja", "price", "category", "category_order", "available", "alias", "reading", "short_name", "display_order", "size", "set_contents", "toppings", "localized_names"])
    for item in items:
        topping_groups = []
        for link in sorted(item.modifier_groups, key=lambda value: (value.display_order, value.id)):
            group = link.group
            if not group.is_active:
                continue
            option_names = [option.name for option in sorted(group.options, key=lambda value: (value.display_order, value.id)) if option.is_available]
            if option_names:
                topping_groups.append(",".join([group.name, *option_names]))
        writer.writerow([
            item.menu_code or f"M{item.id:03d}",
            item.name,
            item.price,
            item.category.name,
            item.category.display_order,
            1 if item.is_available else 0,
            "|".join(alias.alias for alias in item.aliases),
            item.reading,
            item.short_name,
            item.display_order,
            item.size_label,
            item.set_contents,
            " / ".join(topping_groups),
            item.localized_names_json or "{}",
        ])
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="menu-current.csv"'},
    )


@app.get("/api/v1/tables")
def table_list(db: Session = Depends(get_db)):
    tables = list(db.scalars(select(DiningTable).where(DiningTable.is_active.is_(True)).order_by(DiningTable.id)))
    sessions = {
        session.table_id: session
        for session in db.scalars(select(TableSession).where(TableSession.status.in_(["open", "checkout_requested"])))
    }
    return [
        {
            "id": table.id,
            "number": table.number,
            "usage_status": table.usage_status,
            "session_id": sessions.get(table.id).id if sessions.get(table.id) else None,
            "current_order_id": table.current_order_id,
            "customer_url": f"/table/{table.number}",
        }
        for table in tables
    ]


@app.get("/api/v1/tables/{table_id}/shared-order")
def shared_order_for_table(table_id: int, db: Session = Depends(get_db)):
    try:
        _, order = get_shared_order_for_table(db, table_id)
        return order_view(db, order)
    except SharedOrderError as exc:
        raise HTTPException(409, str(exc)) from exc


def _admin_table_reset_state(db: Session, table: DiningTable) -> dict:
    session = db.scalar(
        select(TableSession)
        .where(TableSession.table_id == table.id, TableSession.status.in_(["open", "checkout_requested"]))
        .order_by(TableSession.id.desc())
    )
    order = None
    if session:
        order = db.scalar(
            select(Order)
            .where(Order.session_id == session.id, Order.transaction_id.is_not(None), Order.status == "open")
            .options(selectinload(Order.items))
            .order_by(Order.id.desc())
        )
    items = list(order.items) if order else []
    drafts = [item for item in items if item.status == "draft"]
    confirmed = [item for item in items if item.status == "confirmed"]
    unserved = [item for item in confirmed if item.kitchen_status not in {"served", "cancelled"}]
    pending_requests = 0
    if session:
        pending_requests = len(list(db.scalars(select(ServiceRequest).where(
            ServiceRequest.session_id == session.id,
            ServiceRequest.status.not_in(["completed", "cancelled"]),
        ))))
    has_activity = bool(order or pending_requests or (session and session.status == "checkout_requested"))
    return {
        "table_id": table.id,
        "table_number": table.number,
        "usage_status": table.usage_status,
        "session_id": session.id if session else None,
        "session_status": session.status if session else None,
        "order_id": order.id if order else None,
        "display_number": order.display_number if order else None,
        "confirmed_total": sum(item.line_total for item in confirmed),
        "draft_item_count": sum(item.quantity for item in drafts),
        "unserved_item_count": sum(item.quantity for item in unserved),
        "pending_request_count": pending_requests,
        "has_activity": has_activity,
        "can_reset": bool(session and has_activity and not unserved),
        "block_reason": "未提供の商品があります" if unserved else None,
    }


@app.get("/api/v1/admin/table-reset-status")
def admin_table_reset_status(response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    tables = list(db.scalars(select(DiningTable).where(DiningTable.is_active.is_(True)).order_by(DiningTable.id)))
    return [_admin_table_reset_state(db, table) for table in tables]


@app.post("/api/v1/admin/tables/{table_id}/reset")
async def reset_table_after_departure(table_id: int, payload: TableResetRequest, db: Session = Depends(get_db)):
    table = db.get(DiningTable, table_id)
    if not table or not table.is_active:
        raise HTTPException(404, "テーブルが見つかりません")
    sessions = list(db.scalars(
        select(TableSession)
        .where(TableSession.table_id == table_id, TableSession.status.in_(["open", "checkout_requested"]))
        .order_by(TableSession.id.desc())
    ))
    if not sessions or sessions[0].id != payload.expected_session_id:
        raise HTTPException(409, "テーブルの利用状況が更新されています。画面を読み直してください")
    session = sessions[0]
    order = db.scalar(
        select(Order)
        .where(Order.session_id == session.id, Order.transaction_id.is_not(None), Order.status == "open")
        .options(selectinload(Order.items))
        .order_by(Order.id.desc())
    )
    if order:
        unserved = [
            item for item in order.items
            if item.status == "confirmed" and item.kitchen_status not in {"served", "cancelled"}
        ]
        if unserved:
            raise HTTPException(409, f"未提供の商品が{sum(item.quantity for item in unserved)}点あるため退店処理できません")

    now = datetime.now(timezone.utc)
    old_session_ids = [item.id for item in sessions]
    for active_session in sessions:
        active_session.status = "closed"
        active_session.closed_at = now
    if order:
        for item in order.items:
            if item.status == "draft":
                item.status = "cancelled"
                item.kitchen_status = "cancelled"
                item.change_type = "cancelled"
        order.status = "closed"
        order.updated_at = now
    for request_item in db.scalars(select(ServiceRequest).where(
        ServiceRequest.session_id.in_(old_session_ids),
        ServiceRequest.status.not_in(["completed", "cancelled"]),
    )):
        request_item.status = "cancelled"
    for message in db.scalars(select(Message).where(
        Message.session_id.in_(old_session_ids),
        Message.sender_type == "kitchen",
        Message.dismissed_at.is_(None),
    )):
        message.dismissed_at = now
    table.usage_status = "available"
    table.current_order_id = None
    new_session = TableSession(table_id=table.id, status="open", opened_at=now)
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    result = {
        "table_id": table.id,
        "table_number": table.number,
        "closed_session_id": session.id,
        "new_session_id": new_session.id,
        "reset_at": now.isoformat(),
    }
    event = {"type": "table.session_reset", "data": result}
    for old_session_id in old_session_ids:
        await manager.broadcast_customer(old_session_id, event)
    await manager.broadcast_kitchen(event)
    return result


@app.get("/api/v1/sessions/{session_id}/shared-order")
def shared_order_for_session(session_id: int, db: Session = Depends(get_db)):
    try:
        return order_view(db, get_or_create_shared_order(db, session_id))
    except SharedOrderError as exc:
        raise HTTPException(409, str(exc)) from exc


async def _broadcast_shared(db: Session, order: Order, event_type: str) -> dict:
    result = order_view(db, order)
    event = {"type": event_type, "data": result}
    await manager.broadcast_customer(order.session_id, event)
    await manager.broadcast_kitchen(event)
    return result


@app.post("/api/v1/shared-orders/{order_id}/items")
async def add_item_to_shared_order(order_id: int, payload: SharedItemCreate, db: Session = Depends(get_db)):
    try:
        order = add_shared_item(db, order_id, payload)
    except VersionConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except SharedOrderError as exc:
        raise HTTPException(422, str(exc)) from exc
    return await _broadcast_shared(db, order, "shared_order.changed")


@app.patch("/api/v1/shared-orders/{order_id}/items/{item_id}")
async def change_shared_order_item(
    order_id: int, item_id: int, payload: SharedItemUpdate, db: Session = Depends(get_db)
):
    try:
        order = update_shared_item(db, order_id, item_id, payload)
    except VersionConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except SharedOrderError as exc:
        raise HTTPException(422, str(exc)) from exc
    return await _broadcast_shared(db, order, "shared_order.changed")


@app.post("/api/v1/shared-orders/{order_id}/items/{item_id}/cancel")
async def cancel_item_from_shared_order(
    order_id: int, item_id: int, payload: SharedItemCancel, db: Session = Depends(get_db)
):
    try:
        order = cancel_shared_item(db, order_id, item_id, payload.expected_version, payload.input_by)
    except VersionConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except SharedOrderError as exc:
        raise HTTPException(422, str(exc)) from exc
    return await _broadcast_shared(db, order, "shared_order.changed")


@app.post("/api/v1/kitchen/items/{item_id}/cancel-request/{action}")
async def decide_item_cancel_request(item_id: int, action: str, db: Session = Depends(get_db)):
    if action not in {"approve", "reject"}:
        raise HTTPException(400, "取消依頼の操作が正しくありません")
    try:
        order = resolve_cancel_request(db, item_id, approved=action == "approve")
    except SharedOrderError as exc:
        raise HTTPException(409, str(exc)) from exc
    event_type = "shared_order.cancel_approved" if action == "approve" else "shared_order.cancel_rejected"
    return await _broadcast_shared(db, order, event_type)


@app.post("/api/v1/shared-orders/{order_id}/confirm")
async def confirm_items_in_shared_order(
    order_id: int, payload: SharedOrderConfirm, db: Session = Depends(get_db)
):
    try:
        order = confirm_shared_order(
            db, order_id, payload.expected_version, payload.confirmed_by, payload.confirmation_method
        )
    except VersionConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except SharedOrderError as exc:
        raise HTTPException(422, str(exc)) from exc
    result = await _broadcast_shared(db, order, "shared_order.confirmed")
    return {**result, "pos_export_preview": pos_adapter.export_confirmed_order(order)}


@app.get("/api/v1/shared-orders/{order_id}/pos-export")
def preview_pos_export(order_id: int, db: Session = Depends(get_db)):
    order = db.scalar(
        select(Order)
        .where(Order.id == order_id, Order.transaction_id.is_not(None))
        .options(selectinload(Order.items))
    )
    if not order:
        raise HTTPException(404, "注文が見つかりません")
    return pos_adapter.export_confirmed_order(order)


@app.patch("/api/v1/kitchen/items/{item_id}/status")
async def change_kitchen_item_status(
    item_id: int, payload: KitchenItemStatusUpdate, db: Session = Depends(get_db)
):
    try:
        order = update_kitchen_status(db, item_id, payload.status)
    except SharedOrderError as exc:
        raise HTTPException(409, str(exc)) from exc
    return await _broadcast_shared(db, order, "kitchen.status_changed")


@app.post("/api/v1/admin/display-number/reset")
def reset_display_number(payload: DisplayNumberReset, db: Session = Depends(get_db)):
    return reset_display_numbers(db, payload.next_number)


@app.post("/api/v1/translation/prepare")
def prepare_translation(payload: dict):
    source_text = str(payload.get("source_text", "")).strip()
    source_language = str(payload.get("source_language", "ja"))
    target_language = str(payload.get("target_language", "ja"))
    if not source_text:
        raise HTTPException(422, "原文を入力してください")
    return translator.prepare(source_text, source_language, target_language)


@app.post("/api/v1/input/interpret", response_model=InterpretResponse)
def interpret(payload: InterpretRequest, db: Session = Depends(get_db)):
    if not db.get(TableSession, payload.session_id):
        raise HTTPException(404, "テーブル利用情報が見つかりません")
    return interpret_input(db, payload)


@app.post("/api/ai/resolve-order", response_model=ResolveOrderResponse)
def resolve_ai_order(payload: ResolveOrderRequest, db: Session = Depends(get_db)):
    try:
        return resolve_order(db, payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/v1/orders")
async def submit_order(payload: OrderCreate, db: Session = Depends(get_db)):
    try:
        order = create_order(db, payload)
    except OrderValidationError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.refresh(order, attribute_names=["items"])
    for item in order.items:
        db.refresh(item, attribute_names=["modifiers"])
    result = order_dict(order)
    await manager.broadcast_kitchen({"type": "order.submitted", "data": result})
    return result


@app.get("/api/v1/kitchen/snapshot")
def kitchen_snapshot(db: Session = Depends(get_db)):
    orders = list(
        db.scalars(
            select(Order)
            .where(Order.status.not_in(["served", "rejected", "cancelled"]))
            .options(selectinload(Order.items).selectinload(OrderItem.modifiers))
            .order_by(Order.created_at.desc())
        )
    )
    service_requests = list(
        db.scalars(
            select(ServiceRequest)
            .where(ServiceRequest.status.not_in(["completed", "cancelled"]))
            .order_by(ServiceRequest.created_at.desc())
        )
    )
    sessions = {session.id: session for session in db.scalars(select(TableSession).options(selectinload(TableSession.table)))}
    return {
        "shared_orders": kitchen_shared_snapshot(db),
        "orders": [{**order_dict(order), "table_number": sessions[order.session_id].table.number} for order in orders],
        "service_requests": [
            {
                **request_dict(item),
                "table_number": sessions[item.session_id].table.number,
                "bill": calculate_bill(db, item.session_id) if item.request_type == "checkout" else None,
            }
            for item in service_requests
        ],
    }


@app.patch("/api/v1/orders/{order_id}/status")
async def update_order_status(order_id: int, payload: StatusUpdate, db: Session = Depends(get_db)):
    order = db.scalar(
        select(Order).where(Order.id == order_id).options(selectinload(Order.items).selectinload(OrderItem.modifiers))
    )
    if not order:
        raise HTTPException(404, "注文が見つかりません")
    allowed_transitions = {
        "submitted": {"confirmed", "rejected", "cancelled"},
        "confirmed": {"preparing", "cancelled"},
        "preparing": {"ready", "cancelled"},
        "ready": {"served", "cancelled"},
        "served": set(),
        "rejected": set(),
        "cancelled": set(),
    }
    if payload.status not in allowed_transitions.get(order.status, set()):
        raise HTTPException(409, f"{order.status}から{payload.status}へは変更できません")
    order.status = payload.status
    if payload.status == "confirmed":
        order.confirmed_at = datetime.now(timezone.utc)
    db.commit()
    result = order_dict(order)
    await manager.broadcast_kitchen({"type": "order.status_changed", "data": result})
    await manager.broadcast_customer(order.session_id, {"type": "order.status_changed", "data": result})
    return result


@app.post("/api/v1/service-requests")
async def create_service_request(payload: ServiceRequestCreate, db: Session = Depends(get_db)):
    session = db.get(TableSession, payload.session_id)
    if not session:
        raise HTTPException(404, "テーブル利用情報が見つかりません")
    if session.status not in {"open", "checkout_requested"}:
        raise HTTPException(409, "このテーブルの利用は終了しています")
    if payload.request_type == "other" and not payload.message.strip():
        raise HTTPException(422, "問い合わせ内容を入力してください")
    if payload.request_type == "checkout" and session.status == "checkout_requested":
        existing = db.scalar(
            select(ServiceRequest)
            .where(
                ServiceRequest.session_id == payload.session_id,
                ServiceRequest.request_type == "checkout",
            )
            .order_by(ServiceRequest.id.desc())
        )
        if existing:
            return request_dict(existing)
    item = ServiceRequest(**payload.model_dump())
    db.add(item)
    if payload.request_type == "checkout":
        session.status = "checkout_requested"
    db.commit()
    db.refresh(item)
    result = request_dict(item)
    await manager.broadcast_kitchen({"type": "service_request.created", "data": result})
    return result


@app.patch("/api/v1/service-requests/{request_id}/{action}")
async def update_service_request(request_id: int, action: str, db: Session = Depends(get_db)):
    item = db.get(ServiceRequest, request_id)
    if not item:
        raise HTTPException(404, "依頼が見つかりません")
    statuses = {"acknowledge": "acknowledged", "complete": "completed", "cancel": "cancelled"}
    if action not in statuses:
        raise HTTPException(400, "不正な操作です")
    item.status = statuses[action]
    db.commit()
    result = request_dict(item)
    await manager.broadcast_kitchen({"type": "service_request.status_changed", "data": result})
    await manager.broadcast_customer(item.session_id, {"type": "service_request.status_changed", "data": result})
    return result


@app.get("/api/v1/sessions/{session_id}/bill")
def get_bill(session_id: int, db: Session = Depends(get_db)):
    return calculate_bill(db, session_id)


@app.get("/api/v1/sessions/{session_id}/messages/latest")
def get_latest_kitchen_message(session_id: int, response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    message = db.scalar(
        select(Message)
        .where(
            Message.session_id == session_id,
            Message.sender_type == "kitchen",
            Message.dismissed_at.is_(None),
        )
        .order_by(Message.id.desc())
    )
    if not message:
        return None
    return {
        "id": message.id,
        "session_id": message.session_id,
        "sender_type": message.sender_type,
        "text": message.text,
        "created_at": message.created_at.isoformat(),
    }


@app.post("/api/v1/messages")
async def create_message(payload: MessageCreate, db: Session = Depends(get_db)):
    message = Message(**payload.model_dump())
    db.add(message)
    db.commit()
    db.refresh(message)
    result = {
        "id": message.id,
        "session_id": message.session_id,
        "sender_type": message.sender_type,
        "text": message.text,
        "created_at": message.created_at.isoformat(),
    }
    await manager.broadcast_kitchen({"type": "message.created", "data": result})
    await manager.broadcast_customer(message.session_id, {"type": "message.created", "data": result})
    return result


@app.patch("/api/v1/sessions/{session_id}/messages/{message_id}/dismiss")
async def dismiss_kitchen_message(session_id: int, message_id: int, db: Session = Depends(get_db)):
    message = db.scalar(
        select(Message).where(
            Message.id == message_id,
            Message.session_id == session_id,
            Message.sender_type == "kitchen",
        )
    )
    if not message:
        raise HTTPException(404, "返答が見つかりません")
    dismissed_at = message.dismissed_at or datetime.now(timezone.utc)
    messages = db.scalars(
        select(Message).where(
            Message.session_id == session_id,
            Message.sender_type == "kitchen",
            Message.id <= message_id,
            Message.dismissed_at.is_(None),
        )
    ).all()
    for item in messages:
        item.dismissed_at = dismissed_at
    db.commit()
    result = {"id": message_id, "session_id": session_id, "dismissed_at": dismissed_at.isoformat()}
    await manager.broadcast_customer(session_id, {"type": "message.dismissed", "data": result})
    return result


@app.websocket("/api/v1/ws/kitchen")
async def kitchen_websocket(websocket: WebSocket):
    await manager.connect_kitchen(websocket)
    try:
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_json({"type": "connection.pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/api/v1/health")
def health():
    # 端末側が「サーバーに届くか」を確認するための軽量な窓口（DBには触れない）
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@app.websocket("/api/v1/ws/customer/{session_id}")
async def customer_websocket(session_id: int, websocket: WebSocket):
    await manager.connect_customer(session_id, websocket)
    try:
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_json({"type": "connection.pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.websocket("/api/v1/ws/orders/{session_id}")
async def shared_order_websocket(session_id: int, websocket: WebSocket):
    await manager.connect_customer(session_id, websocket)
    try:
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_json({"type": "connection.pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
