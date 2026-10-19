import csv
import io
import json
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.models import (
    MenuAlias,
    MenuCategory,
    MenuItem,
    MenuItemModifierGroup,
    MenuVersion,
    MenuVersionItem,
    ModifierOption,
    Store,
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_topping_groups(value: str) -> list[tuple[str, list[str]]]:
    """人が編集しやすい「辛さ,大,中,小 / ご飯量,大盛,普通」を解析する。"""
    value = value.strip()
    if not value:
        return []
    legacy_parts = [part.strip() for part in value.split("|") if part.strip()]
    if legacy_parts and all(":" in part or "：" in part for part in legacy_parts):
        grouped: dict[str, list[str]] = {}
        for part in legacy_parts:
            group_name, option_name = re.split(r"[:：]", part, maxsplit=1)
            grouped.setdefault(group_name.strip(), []).append(option_name.strip())
        return [(name, list(dict.fromkeys(options))) for name, options in grouped.items() if name and any(options)]
    groups = []
    for block in re.split(r"\s*(?:/|／|\r?\n)\s*", value):
        parts = [part.strip() for part in re.split(r"[,、]", block) if part.strip()]
        if len(parts) >= 2:
            groups.append((parts[0], list(dict.fromkeys(parts[1:]))))
    return groups


def load_current_menu_version(db: Session, store_id: str, at: datetime | None = None) -> MenuVersion | None:
    at = at or now_utc()
    return db.scalar(
        select(MenuVersion)
        .where(
            MenuVersion.store_id == store_id,
            MenuVersion.valid_from <= at,
            (MenuVersion.valid_to.is_(None) | (MenuVersion.valid_to > at)),
        )
        .options(selectinload(MenuVersion.items))
        .order_by(MenuVersion.valid_from.desc(), MenuVersion.id.desc())
    )


def snapshot_current_menu(db: Session, store_id: str, version: str, valid_from: datetime | None = None) -> MenuVersion:
    existing = db.scalar(select(MenuVersion).where(MenuVersion.store_id == store_id, MenuVersion.version == version))
    if existing:
        return existing
    valid_from = valid_from or now_utc()
    store = db.get(Store, store_id)
    if not store:
        store = Store(id=store_id, name=settings.restaurant_name, monthly_ai_request_limit=settings.store_monthly_ai_limit)
        db.add(store)
        db.flush()
    current = load_current_menu_version(db, store_id, valid_from)
    if current:
        current.valid_to = valid_from
    menu_version = MenuVersion(store_id=store_id, version=version, valid_from=valid_from)
    db.add(menu_version)
    db.flush()
    items = list(
        db.scalars(
            select(MenuItem)
            .where(MenuItem.store_id == store_id)
            .options(
                selectinload(MenuItem.aliases),
                selectinload(MenuItem.modifier_groups)
                .selectinload(MenuItemModifierGroup.group)
                .selectinload(MenuCategory.options),
            )
            .order_by(MenuItem.display_order, MenuItem.id)
        )
    )
    for item in items:
        toppings = [
            {"id": option.id, "name": option.name, "price_delta": option.price_delta}
            for link in item.modifier_groups
            for option in link.group.options
            if link.group.is_active and option.is_available
        ]
        db.add(
            MenuVersionItem(
                menu_version_id=menu_version.id,
                menu_item_id=item.id,
                menu_id=item.menu_code or f"M{item.id:03d}",
                name=item.name,
                category_name=item.category.name,
                reading=item.reading,
                aliases_json=json.dumps([alias.alias for alias in item.aliases], ensure_ascii=False),
                price=item.price,
                size_label=item.size_label,
                set_contents=item.set_contents,
                toppings_json=json.dumps(toppings, ensure_ascii=False),
                sold_out=not item.is_available,
                localized_names_json=item.localized_names_json,
                valid_from=valid_from,
            )
        )
    db.commit()
    return load_current_menu_version(db, store_id, valid_from)  # type: ignore[return-value]


def _parse_datetime(value: str, default: datetime | None = None) -> datetime | None:
    if not value.strip():
        return default
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def import_menu_csv(db: Session, raw: bytes) -> dict:
    text = raw.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise ValueError("CSVに商品がありません")

    def cell(row: dict, key: str) -> str:
        return str(row.get(key) or "").strip()

    headers = set(rows[0])
    missing = {"menu_id", "price"} - headers
    if missing or not ({"name", "name_ja"} & headers):
        required = sorted(missing | ({"name または name_ja"} if not ({"name", "name_ja"} & headers) else set()))
        raise ValueError(f"必須列がありません: {', '.join(required)}")

    generated_at = now_utc()
    store_id = cell(rows[0], "store_id") or settings.default_store_id
    version_name = cell(rows[0], "menu_version") or generated_at.strftime("%Y%m%d-%H%M%S-%f-csv")
    if any((cell(row, "store_id") and cell(row, "store_id") != store_id) or (cell(row, "menu_version") and cell(row, "menu_version") != version_name) for row in rows):
        raise ValueError("一つのCSVには一店舗・一メニューバージョンだけ指定してください")
    if db.scalar(select(MenuVersion).where(MenuVersion.store_id == store_id, MenuVersion.version == version_name)):
        raise ValueError("同じメニューバージョンは既に登録されています")
    start = _parse_datetime(cell(rows[0], "valid_from"), generated_at)
    end = _parse_datetime(cell(rows[0], "valid_to"))
    store = db.get(Store, store_id)
    if not store:
        store = Store(id=store_id, name=cell(rows[0], "store_name") or store_id)
        db.add(store)
        db.flush()
    current = load_current_menu_version(db, store_id, start)
    if current:
        current.valid_to = start
    version = MenuVersion(store_id=store_id, version=version_name, valid_from=start, valid_to=end)
    db.add(version)
    db.flush()

    # A menu CSV is a complete catalog snapshot. Items omitted from the new
    # snapshot must not remain orderable through the live MenuItem table.
    for existing_item in db.scalars(select(MenuItem).where(MenuItem.store_id == store_id)):
        existing_item.is_available = False

    for index, row in enumerate(rows, start=1):
        menu_code = cell(row, "menu_id")
        item_name = cell(row, "name") or cell(row, "name_ja")
        if not menu_code or not item_name:
            raise ValueError(f"{index}行目の商品コードまたは商品名が空です")
        try:
            price = int(cell(row, "price"))
        except ValueError as exc:
            raise ValueError(f"{index}行目の価格が数値ではありません") from exc
        if price < 0:
            raise ValueError(f"{index}行目の価格は0以上にしてください")

        category_name = cell(row, "category") or "CSV取込"
        category = db.scalar(select(MenuCategory).where(MenuCategory.name == category_name))
        if not category:
            try:
                category_order = int(cell(row, "category_order") or 50)
            except ValueError as exc:
                raise ValueError(f"{index}行目のカテゴリ表示順が数値ではありません") from exc
            category = MenuCategory(name=category_name, display_order=category_order)
            db.add(category)
            db.flush()
        category.is_menu_category = True
        item = db.scalar(select(MenuItem).where(MenuItem.store_id == store_id, MenuItem.menu_code == menu_code))
        if not item:
            item = MenuItem(category_id=category.id, store_id=store_id, menu_code=menu_code, name=item_name, short_name=cell(row, "short_name") or item_name, price=price, display_order=index)
            db.add(item)
            db.flush()
        item.name = item_name
        item.category_id = category.id
        item.short_name = cell(row, "short_name") or item.name
        item.reading = cell(row, "reading")
        item.price = price
        try:
            item.display_order = int(cell(row, "display_order") or index)
        except ValueError as exc:
            raise ValueError(f"{index}行目の商品表示順が数値ではありません") from exc
        item.size_label = cell(row, "size")
        item.set_contents = cell(row, "set_contents")
        available = cell(row, "available").casefold()
        item.is_available = available in {"1", "true", "yes", "販売中", "available"} if "available" in headers else cell(row, "sold_out").casefold() not in {"1", "true", "yes", "売り切れ"}
        item.is_archived = False
        item.localized_names_json = cell(row, "localized_names") or cell(row, "translations") or "{}"
        alias_text = cell(row, "aliases") or cell(row, "alias")
        aliases = [value.strip() for value in re.split(r"[|,、]", alias_text) if value.strip()]
        item.aliases = [MenuAlias(alias=value) for value in aliases]
        topping_groups = parse_topping_groups(cell(row, "toppings"))
        existing_links = {link.group_id: link for link in item.modifier_groups}
        links = []
        topping_snapshot = []
        for group_order, (group_name, option_names) in enumerate(topping_groups, start=1):
            group = db.scalar(select(MenuCategory).where(MenuCategory.name == group_name))
            if not group:
                group = MenuCategory(name=group_name, is_menu_category=False, is_option_group=True, selection_type="single", display_order=group_order * 10, is_active=True)
                db.add(group)
                db.flush()
            else:
                group.is_option_group = True
                group.is_active = True
            existing_options = {option.name: option for option in db.scalars(select(ModifierOption).where(ModifierOption.group_id == group.id))}
            for option_order, option_name in enumerate(option_names, start=1):
                option = existing_options.get(option_name)
                if not option:
                    option = ModifierOption(group_id=group.id, name=option_name, price_delta=0, display_order=option_order * 10, is_available=True)
                    db.add(option)
                    db.flush()
                else:
                    option.is_available = True
                topping_snapshot.append({"id": option.id, "group": group.name, "name": option.name, "price_delta": option.price_delta})
            existing_link = existing_links.get(group.id)
            required = existing_link.required if existing_link else "辛さ" in group.name
            links.append(MenuItemModifierGroup(group_id=group.id, required=required, display_order=group_order * 10))
        if "toppings" in headers:
            item.modifier_groups = links
        db.add(MenuVersionItem(menu_version_id=version.id, menu_item_id=item.id, menu_id=menu_code, name=item.name, category_name=category.name, reading=item.reading, aliases_json=json.dumps(aliases, ensure_ascii=False), price=item.price, size_label=item.size_label, set_contents=item.set_contents, toppings_json=json.dumps(topping_snapshot, ensure_ascii=False), sold_out=not item.is_available, localized_names_json=item.localized_names_json, valid_from=start, valid_to=end))
    db.commit()
    return {"store_id": store_id, "menu_version": version_name, "items": len(rows), "valid_from": start.isoformat()}
