import secrets
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    DiningTable,
    MenuAlias,
    MenuCategory,
    MenuItem,
    MenuItemModifierGroup,
    MenuVersion,
    MenuVersionItem,
    ModifierOption,
    TableSession,
)
from app.config import settings
from app.services.menu_catalog import snapshot_current_menu


def seed_database(db: Session) -> None:
    if not db.scalar(select(func.count(DiningTable.id))):
        for number in range(1, 11):
            table = DiningTable(number=str(number), access_token=secrets.token_urlsafe(18))
            db.add(table)
            db.flush()
            db.add(TableSession(table_id=table.id, status="open"))

    if not db.scalar(select(func.count(MenuItem.id))):
        drinks = MenuCategory(name="ドリンク", display_order=1)
        foods = MenuCategory(name="料理", display_order=2)
        db.add_all([drinks, foods])
        db.flush()

        beer_size = MenuCategory(name="ビールサイズ", is_menu_category=False, is_option_group=True, selection_type="single")
        beer_size.options = [
            ModifierOption(name="小", price_delta=-100),
            ModifierOption(name="中", price_delta=0, is_default=True),
            ModifierOption(name="大", price_delta=250),
        ]
        serving = MenuCategory(name="盛り", is_menu_category=False, is_option_group=True, selection_type="single")
        serving.options = [
            ModifierOption(name="普通", price_delta=0, is_default=True),
            ModifierOption(name="大盛", price_delta=150),
        ]
        db.add_all([beer_size, serving])
        db.flush()

        menu = [
            MenuItem(store_id=settings.default_store_id, menu_code="M101", category_id=drinks.id, name="キリン一番搾り 生ビール", short_name="キリン", price=600, display_order=1),
            MenuItem(store_id=settings.default_store_id, menu_code="M102", category_id=drinks.id, name="アサヒスーパードライ 生ビール", short_name="アサヒ", price=600, display_order=2),
            MenuItem(store_id=settings.default_store_id, menu_code="M103", category_id=drinks.id, name="サントリー生ビール", short_name="サントリー", price=580, display_order=3),
            MenuItem(store_id=settings.default_store_id, menu_code="M104", category_id=foods.id, name="塩ゆで枝豆", short_name="枝豆", price=350, display_order=10),
            MenuItem(store_id=settings.default_store_id, menu_code="M105", category_id=foods.id, name="鶏の唐揚げ", short_name="唐揚げ", price=700, display_order=11),
            MenuItem(store_id=settings.default_store_id, menu_code="M106", category_id=foods.id, name="ライス", short_name="ライス", price=250, display_order=12),
        ]
        db.add_all(menu)
        db.flush()

        aliases = {
            0: ["キリン", "一番搾り", "キリンの生"],
            1: ["アサヒ", "朝日", "スーパードライ", "アサヒの生"],
            2: ["サントリー", "サン生", "サントリーの生"],
            3: ["枝豆", "えだまめ"],
            4: ["唐揚げ", "からあげ"],
            5: ["ご飯", "ごはん", "ライス"],
        }
        for index, words in aliases.items():
            menu[index].aliases = [MenuAlias(alias=word) for word in words]
        for item in menu[:3]:
            item.modifier_groups.append(MenuItemModifierGroup(group_id=beer_size.id))
        menu[5].modifier_groups.append(MenuItemModifierGroup(group_id=serving.id))

    # 既存DBにもMVP確認用メニューだけは不足分を追加する。
    foods = db.scalar(select(MenuCategory).where(MenuCategory.name == "料理", MenuCategory.is_menu_category.is_(True)))
    if foods:
        sample_items = [
            ("Aランチ", "Aランチ", 900, ["エーランチ"]),
            ("アジフライ定食", "アジフライ", 850, ["鯵フライ定食", "アジフライ"]),
            ("カレーライス", "カレー", 750, ["カレー"]),
        ]
        serving = db.scalar(select(MenuCategory).where(MenuCategory.name == "盛り", MenuCategory.is_option_group.is_(True)))
        for offset, (name, short_name, price, aliases) in enumerate(sample_items, start=20):
            if db.scalar(select(MenuItem).where(MenuItem.name == name)):
                continue
            item = MenuItem(
                category_id=foods.id,
                store_id=settings.default_store_id,
                menu_code={"Aランチ": "M001", "アジフライ定食": "M012", "カレーライス": "M035"}[name],
                name=name,
                short_name=short_name,
                price=price,
                display_order=offset,
                localized_names_json=f'{{"ja":"{name}"}}',
            )
            item.aliases = [MenuAlias(alias=alias) for alias in aliases]
            if name == "カレーライス" and serving:
                item.modifier_groups.append(MenuItemModifierGroup(group_id=serving.id))
            db.add(item)

    db.commit()

    # 既存DBでは初回だけ外部メニューコードを補う。
    for item in db.scalars(select(MenuItem).where(MenuItem.menu_code.is_(None)).order_by(MenuItem.id)):
        item.store_id = settings.default_store_id
        item.menu_code = f"M{item.id:03d}"
    db.commit()
    stable_codes = {
        "キリン一番搾り 生ビール": "M101",
        "アサヒスーパードライ 生ビール": "M102",
        "サントリー生ビール": "M103",
        "塩ゆで枝豆": "M104",
        "鶏の唐揚げ": "M105",
        "ライス": "M106",
        "Aランチ": "M001",
        "アジフライ定食": "M012",
        "カレーライス": "M035",
    }
    for item in db.scalars(select(MenuItem).where(MenuItem.name.in_(stable_codes))):
        item.menu_code = stable_codes[item.name]
    # 初期版を旧DBへ追加済みの場合も、サンプル商品の外部コードを安定化する。
    version_rows = list(db.scalars(select(MenuVersionItem)))
    for row in version_rows:
        row.menu_id = f"__migrating_{row.id}"
    db.flush()
    for row in version_rows:
        item = db.get(MenuItem, row.menu_item_id)
        row.menu_id = item.menu_code or f"M{item.id:03d}"
    db.commit()
    if not db.scalar(select(func.count(MenuVersion.id))):
        snapshot_current_menu(
            db,
            settings.default_store_id,
            datetime.now(timezone.utc).strftime("%Y-%m-%d-01"),
            datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
