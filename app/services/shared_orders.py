from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.models import (
    DiningTable,
    DisplayNumberCounter,
    MenuItem,
    MenuItemModifierGroup,
    MenuCategory,
    MenuVersionItem,
    ModifierOption,
    Order,
    OrderItem,
    OrderItemModifier,
    TableSession,
)
from app.schemas import SharedItemCreate, SharedItemUpdate
from app.config import settings
from app.services.menu_catalog import load_current_menu_version


class SharedOrderError(ValueError):
    pass


class VersionConflict(SharedOrderError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _business_date() -> str:
    # 日本には夏時間がないため、WindowsにIANA tzdataがなくても動く固定JSTを使う。
    return datetime.now(timezone(timedelta(hours=9))).date().isoformat()


def _load_order(db: Session, order_id: int) -> Order | None:
    return db.scalar(
        select(Order)
        .where(Order.id == order_id, Order.transaction_id.is_not(None))
        .options(selectinload(Order.items).selectinload(OrderItem.modifiers))
    )


def get_or_create_shared_order(db: Session, session_id: int) -> Order:
    session = db.scalar(
        select(TableSession)
        .where(TableSession.id == session_id, TableSession.status.in_(["open", "checkout_requested"]))
        .options(selectinload(TableSession.table))
    )
    if not session:
        raise SharedOrderError("利用中のテーブルではありません")
    order = db.scalar(
        select(Order)
        .where(
            Order.session_id == session_id,
            Order.transaction_id.is_not(None),
            Order.status == "open",
            Order.business_date == _business_date(),
        )
        .options(selectinload(Order.items).selectinload(OrderItem.modifiers))
        .order_by(Order.id.desc())
    )
    if order:
        if session.table.current_order_id != order.id:
            session.table.current_order_id = order.id
            session.table.usage_status = "occupied"
            db.commit()
        return order
    now = _now()
    transaction_id = str(uuid4())
    order = Order(
        session_id=session_id,
        client_request_id=f"shared-{transaction_id}",
        transaction_id=transaction_id,
        business_date=_business_date(),
        status="open",
        created_at=now,
        updated_at=now,
        version=1,
        confirmation_batches=0,
    )
    db.add(order)
    db.flush()
    session.table.usage_status = "occupied"
    session.table.current_order_id = order.id
    db.commit()
    return _load_order(db, order.id)  # type: ignore[return-value]


def get_shared_order_for_table(db: Session, table_id: int) -> tuple[TableSession, Order]:
    session = db.scalar(
        select(TableSession)
        .where(TableSession.table_id == table_id, TableSession.status.in_(["open", "checkout_requested"]))
        .options(selectinload(TableSession.table))
        .order_by(TableSession.id.desc())
    )
    if not session:
        raise SharedOrderError("テーブルが利用開始されていません")
    return session, get_or_create_shared_order(db, session.id)


def _menu_and_options(db: Session, menu_item_id: int, option_ids: list[int]) -> tuple[MenuItem, list[ModifierOption]]:
    menu_item = db.scalar(
        select(MenuItem)
        .where(MenuItem.id == menu_item_id)
        .options(
            selectinload(MenuItem.modifier_groups)
            .selectinload(MenuItemModifierGroup.group)
            .selectinload(MenuCategory.options)
        )
    )
    if not menu_item or not menu_item.is_available:
        raise SharedOrderError("売り切れ、または存在しない商品です")
    active_links = [link for link in menu_item.modifier_groups if link.group.is_active]
    allowed = {option.id: option for link in active_links for option in link.group.options if option.is_available}
    selected_by_id: dict[int, ModifierOption] = {}
    for option_id in dict.fromkeys(option_ids):
        if option_id not in allowed:
            raise SharedOrderError("商品に設定されていない調整項目です")
        selected_by_id[option_id] = allowed[option_id]
    for link in active_links:
        group_options = [option for option in link.group.options if option.is_available]
        selected_in_group = [option for option in group_options if option.id in selected_by_id]
        if not selected_in_group and not link.required:
            for option in group_options:
                if option.is_default:
                    selected_by_id[option.id] = option
            selected_in_group = [option for option in group_options if option.id in selected_by_id]
        if link.required and not selected_in_group:
            raise SharedOrderError(f"{link.group.name}を選んでください")
        if link.group.selection_type == "single" and len(selected_in_group) > 1:
            raise SharedOrderError(f"{link.group.name}は一つだけ選んでください")
    return menu_item, list(selected_by_id.values())


def _reserve_version(db: Session, order_id: int, expected: int) -> int:
    result = db.execute(
        update(Order)
        .where(Order.id == order_id, Order.version == expected, Order.status == "open")
        .values(version=Order.version + 1, updated_at=_now())
    )
    if result.rowcount != 1:
        db.rollback()
        raise VersionConflict("別の端末で注文が更新されました。最新内容を読み込み直しました")
    return expected + 1


def add_shared_item(db: Session, order_id: int, payload: SharedItemCreate) -> Order:
    menu_item, selected = _menu_and_options(db, payload.menu_item_id, payload.modifier_option_ids)
    current_version = load_current_menu_version(db, menu_item.store_id or settings.default_store_id)
    if not current_version:
        raise SharedOrderError("現在有効なメニューがありません")
    if payload.menu_version and payload.menu_version != current_version.version:
        raise SharedOrderError("メニューが更新されました。商品を選び直してください")
    catalog_item = next((value for value in current_version.items if value.menu_item_id == menu_item.id), None)
    if not catalog_item or catalog_item.sold_out:
        raise SharedOrderError("売り切れ、または現在のメニューにない商品です")
    if payload.selected_candidate and int(payload.selected_candidate.get("menu_item_id", -1)) != menu_item.id:
        raise SharedOrderError("選択した候補と商品が一致しません")
    new_version = _reserve_version(db, order_id, payload.expected_version)
    # AIの返答ではなく、現在有効な店舗メニューの価格を使う。
    unit_price = catalog_item.price + sum(option.price_delta for option in selected)
    item = OrderItem(
        order_id=order_id,
        menu_item_id=menu_item.id,
        menu_name_snapshot=catalog_item.name,
        unit_price_snapshot=unit_price,
        menu_version_snapshot=current_version.version,
        llm_candidates_json=json.dumps(payload.llm_candidates, ensure_ascii=False),
        selected_candidate_json=json.dumps(payload.selected_candidate or {}, ensure_ascii=False),
        quantity=payload.quantity,
        line_total=unit_price * payload.quantity,
        status="draft",
        kitchen_status="not_started",
        input_by=payload.input_by,
        input_language=payload.input_language,
        input_at=_now(),
        original_text=payload.original_text,
        notes=payload.notes,
        change_type="added",
    )
    item.modifiers = [
        OrderItemModifier(
            modifier_option_id=option.id,
            group_name_snapshot=option.group.name,
            name_snapshot=option.name,
            price_delta_snapshot=option.price_delta,
        )
        for option in selected
    ]
    db.add(item)
    db.commit()
    order = _load_order(db, order_id)
    if not order or order.version != new_version:
        raise SharedOrderError("注文を再読込できませんでした")
    return order


def update_shared_item(db: Session, order_id: int, item_id: int, payload: SharedItemUpdate) -> Order:
    item = db.scalar(select(OrderItem).where(OrderItem.id == item_id, OrderItem.order_id == order_id))
    if not item or item.status != "draft":
        raise SharedOrderError("確定前の明細だけ変更できます")
    option_ids = payload.modifier_option_ids
    selected: list[ModifierOption] | None = None
    if option_ids is not None:
        _, selected = _menu_and_options(db, item.menu_item_id, option_ids)
    _reserve_version(db, order_id, payload.expected_version)
    if payload.quantity is not None:
        item.previous_quantity = item.quantity
        item.quantity = payload.quantity
        item.change_type = "changed"
    if payload.notes is not None:
        item.notes = payload.notes
    if selected is not None:
        base_price_snapshot = item.unit_price_snapshot - sum(modifier.price_delta_snapshot for modifier in item.modifiers)
        item.modifiers.clear()
        item.modifiers.extend(
            OrderItemModifier(
                modifier_option_id=option.id,
                group_name_snapshot=option.group.name,
                name_snapshot=option.name,
                price_delta_snapshot=option.price_delta,
            )
            for option in selected
        )
        item.unit_price_snapshot = base_price_snapshot + sum(option.price_delta for option in selected)
    item.line_total = item.unit_price_snapshot * item.quantity
    db.commit()
    return _load_order(db, order_id)  # type: ignore[return-value]


def cancel_shared_item(db: Session, order_id: int, item_id: int, expected_version: int, input_by: str) -> Order:
    item = db.scalar(select(OrderItem).where(OrderItem.id == item_id, OrderItem.order_id == order_id))
    if not item or item.status in {"cancelled", "cancel_requested"}:
        raise SharedOrderError("取消できる明細がありません")
    if item.status == "confirmed" and input_by == "customer" and item.kitchen_status == "served":
        raise SharedOrderError("提供済みの商品は取り消しできません")
    if item.status == "confirmed" and input_by != "customer" and item.kitchen_status != "not_started":
        raise SharedOrderError("調理開始後は取り消しできません")
    _reserve_version(db, order_id, expected_version)
    if item.status == "confirmed" and input_by == "customer":
        item.status = "cancel_requested"
        item.change_type = "cancel_requested"
    else:
        item.status = "cancelled"
        item.kitchen_status = "cancelled"
        item.change_type = "cancelled"
    db.commit()
    return _load_order(db, order_id)  # type: ignore[return-value]


def resolve_cancel_request(db: Session, item_id: int, approved: bool) -> Order:
    item = db.scalar(select(OrderItem).where(OrderItem.id == item_id))
    if not item or item.status != "cancel_requested":
        raise SharedOrderError("取消依頼が見つかりません")
    if approved:
        item.status = "cancelled"
        item.kitchen_status = "cancelled"
        item.change_type = "cancelled"
    else:
        item.status = "confirmed"
        item.change_type = "cancel_rejected"
    order = db.get(Order, item.order_id)
    order.version += 1  # type: ignore[union-attr]
    order.updated_at = _now()  # type: ignore[union-attr]
    db.commit()
    return _load_order(db, item.order_id)  # type: ignore[return-value]


def confirm_shared_order(
    db: Session, order_id: int, expected_version: int, confirmed_by: str, confirmation_method: str
) -> Order:
    order = _load_order(db, order_id)
    if not order:
        raise SharedOrderError("注文が見つかりません")
    drafts = [item for item in order.items if item.status == "draft"]
    if not drafts:
        raise SharedOrderError("確定する注文候補がありません")
    _reserve_version(db, order_id, expected_version)
    now = _now()
    batch = order.confirmation_batches + 1
    if order.display_number is None:
        counter = db.scalar(select(DisplayNumberCounter).where(DisplayNumberCounter.business_date == order.business_date))
        if not counter:
            highest = db.scalar(select(func.max(Order.display_number)).where(Order.business_date == order.business_date)) or 0
            counter = DisplayNumberCounter(business_date=order.business_date, next_number=highest + 1)
            db.add(counter)
            db.flush()
        order.display_number = counter.next_number
        counter.next_number += 1
    order.confirmation_batches = batch
    order.confirmed_at = now
    order.confirmed_by = confirmed_by
    order.confirmation_method = confirmation_method
    for item in drafts:
        item.status = "confirmed"
        item.confirmed_at = now
        item.submission_batch = batch
        item.kitchen_status = "not_started"
    db.commit()
    return _load_order(db, order_id)  # type: ignore[return-value]


def update_kitchen_status(db: Session, item_id: int, new_status: str) -> Order:
    item = db.scalar(select(OrderItem).where(OrderItem.id == item_id))
    if not item or item.status not in {"confirmed", "cancel_requested", "cancelled"}:
        raise SharedOrderError("厨房対象の明細が見つかりません")
    allowed = {
        "not_started": {"preparing", "served", "cancelled"},
        "preparing": {"served"},
        "served": set(),
        "cancelled": set(),
    }
    if new_status not in allowed.get(item.kitchen_status, set()):
        raise SharedOrderError("その調理状態には変更できません")
    item.kitchen_status = new_status
    if new_status == "cancelled":
        item.status = "cancelled"
        item.change_type = "cancelled"
    order = db.get(Order, item.order_id)
    order.version += 1  # type: ignore[union-attr]
    order.updated_at = _now()  # type: ignore[union-attr]
    db.commit()
    return _load_order(db, item.order_id)  # type: ignore[return-value]


def order_view(db: Session, order: Order) -> dict:
    session = db.scalar(
        select(TableSession).where(TableSession.id == order.session_id).options(selectinload(TableSession.table))
    )
    lines = []
    for item in sorted(order.items, key=lambda value: value.id):
        lines.append(
            {
                "id": item.id,
                "menu_item_id": item.menu_item_id,
                "name": item.menu_name_snapshot,
                "unit_price": item.unit_price_snapshot,
                "quantity": item.quantity,
                "line_total": item.line_total,
                "modifiers": [modifier.display_name for modifier in item.modifiers],
                "notes": item.notes,
                "status": item.status,
                "kitchen_status": item.kitchen_status,
                "input_by": item.input_by,
                "input_language": item.input_language,
                "input_at": item.input_at.isoformat() if item.input_at else None,
                "confirmed_at": item.confirmed_at.isoformat() if item.confirmed_at else None,
                "original_text": item.original_text,
                "menu_version": item.menu_version_snapshot,
                "llm_candidates": json.loads(item.llm_candidates_json or "[]"),
                "selected_candidate": json.loads(item.selected_candidate_json or "{}"),
                "change_type": item.change_type,
                "submission_batch": item.submission_batch,
                "is_additional": item.submission_batch > 1,
            }
        )
    active = [line for line in lines if line["status"] != "cancelled"]
    drafts = [line for line in active if line["status"] == "draft"]
    confirmed = [line for line in active if line["status"] in {"confirmed", "cancel_requested"}]
    return {
        "id": order.id,
        "transaction_id": order.transaction_id,
        "business_date": order.business_date,
        "display_number": order.display_number,
        "table_id": session.table_id if session else None,
        "table_number": session.table.number if session else "?",
        "session_id": order.session_id,
        "status": order.status,
        "version": order.version,
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat() if order.updated_at else order.created_at.isoformat(),
        "items": lines,
        "draft_total": sum(line["line_total"] for line in active),
        "pending_total": sum(line["line_total"] for line in drafts),
        "current_total": sum(line["line_total"] for line in active),
        "confirmed_total": sum(line["line_total"] for line in confirmed),
    }


def kitchen_shared_snapshot(db: Session) -> list[dict]:
    orders = list(
        db.scalars(
            select(Order)
            .where(
                Order.transaction_id.is_not(None),
                Order.business_date == _business_date(),
                Order.status == "open",
            )
            .options(selectinload(Order.items).selectinload(OrderItem.modifiers))
            .order_by(Order.confirmed_at, Order.id)
        )
    )
    result = []
    for order in orders:
        view = order_view(db, order)
        view["items"] = [
            item for item in view["items"]
            if item["status"] in {"confirmed", "cancel_requested"} and item["kitchen_status"] != "cancelled"
        ]
        if view["items"]:
            result.append(view)
    return result


def reset_display_numbers(db: Session, next_number: int = 1) -> dict:
    today = _business_date()
    counter = db.scalar(select(DisplayNumberCounter).where(DisplayNumberCounter.business_date == today))
    if not counter:
        counter = DisplayNumberCounter(business_date=today, next_number=next_number)
        db.add(counter)
    else:
        counter.next_number = next_number
    db.commit()
    return {"business_date": today, "next_number": next_number, "note": "過去の表示番号は保持し、次の確定注文から指定番号で採番します"}
