import json

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import MenuCategory, MenuItem, MenuItemModifierGroup
from app.schemas import MenuItemView, ModifierGroupView, ModifierOptionView


def load_available_menu(db: Session, store_id: str | None = None) -> list[MenuItem]:
    statement = select(MenuItem).where(MenuItem.is_available.is_(True), MenuItem.is_archived.is_(False))
    if store_id:
        statement = statement.where(MenuItem.store_id == store_id)
    return list(
        db.scalars(
            statement.join(MenuCategory)
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


def to_menu_view(item: MenuItem) -> MenuItemView:
    try:
        localized_names = json.loads(item.localized_names_json or "{}")
        if not isinstance(localized_names, dict):
            localized_names = {}
    except (TypeError, ValueError):
        localized_names = {}
    return MenuItemView(
        id=item.id,
        category=item.category.name,
        name=item.name,
        short_name=item.short_name,
        localized_names={str(key): str(value) for key, value in localized_names.items() if isinstance(value, str)},
        price=item.price,
        modifiers=[
            ModifierGroupView(
                id=link.group.id,
                name=link.group.name,
                selection_type=link.group.selection_type,
                required=link.required,
                options=[
                    ModifierOptionView(
                        id=option.id,
                        name=option.name,
                        price_delta=option.price_delta,
                        is_default=option.is_default,
                    )
                    for option in sorted(link.group.options, key=lambda value: (value.display_order, value.id))
                    if option.is_available
                ],
            )
            for link in sorted(item.modifier_groups, key=lambda value: (value.display_order, value.id))
            if link.group.is_active
        ],
    )
