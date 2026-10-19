from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import MenuCategory, MenuItem, MenuItemModifierGroup, ModifierOption, Order, OrderItem, OrderItemModifier, TableSession
from app.schemas import OrderCreate


BILLABLE_STATUSES = {"confirmed", "preparing", "ready", "served"}


class OrderValidationError(ValueError):
    pass


def create_order(db: Session, payload: OrderCreate) -> Order:
    existing = db.scalar(select(Order).where(Order.client_request_id == payload.client_request_id))
    if existing:
        return existing

    session = db.get(TableSession, payload.session_id)
    if not session or session.status not in {"open", "checkout_requested"}:
        raise OrderValidationError("利用中のテーブルではありません")

    order = Order(
        session_id=payload.session_id,
        interpretation_id=payload.interpretation_id,
        client_request_id=payload.client_request_id,
        original_text=payload.original_text,
        status="submitted",
    )
    db.add(order)

    for requested in payload.items:
        menu_item = db.scalar(
            select(MenuItem)
            .where(MenuItem.id == requested.menu_item_id)
            .options(
                selectinload(MenuItem.modifier_groups)
                .selectinload(MenuItemModifierGroup.group)
                .selectinload(MenuCategory.options)
            )
        )
        if not menu_item or not menu_item.is_available:
            raise OrderValidationError("販売できない商品が含まれています")

        allowed_options = {
            option.id: option
            for link in menu_item.modifier_groups
            for option in link.group.options
        }
        selected_options: list[ModifierOption] = []
        for option_id in dict.fromkeys(requested.modifier_option_ids):
            option = allowed_options.get(option_id)
            if not option:
                raise OrderValidationError("商品に設定されていない調整項目です")
            selected_options.append(option)

        unit_price = menu_item.price + sum(option.price_delta for option in selected_options)
        line_total = unit_price * requested.quantity
        order_item = OrderItem(
            menu_item_id=menu_item.id,
            menu_name_snapshot=menu_item.name,
            unit_price_snapshot=unit_price,
            quantity=requested.quantity,
            line_total=line_total,
        )
        order_item.modifiers = [
            OrderItemModifier(
                modifier_option_id=option.id,
                group_name_snapshot=option.group.name,
                name_snapshot=option.name,
                price_delta_snapshot=option.price_delta,
            )
            for option in selected_options
        ]
        order.items.append(order_item)

    db.commit()
    db.refresh(order)
    return order


def calculate_bill(db: Session, session_id: int) -> dict:
    orders = list(
        db.scalars(
            select(Order)
            .where(Order.session_id == session_id, Order.status.in_(BILLABLE_STATUSES))
            .options(selectinload(Order.items).selectinload(OrderItem.modifiers))
            .order_by(Order.created_at)
        )
    )
    lines = [
        {
            "order_id": order.id,
            "name": item.menu_name_snapshot,
            "quantity": item.quantity,
            "unit_price": item.unit_price_snapshot,
            "line_total": item.line_total,
            "modifiers": [modifier.display_name for modifier in item.modifiers],
        }
        for order in orders
        for item in order.items
    ]
    shared_orders = list(
        db.scalars(
            select(Order)
            .where(Order.session_id == session_id, Order.transaction_id.is_not(None), Order.status == "open")
            .options(selectinload(Order.items).selectinload(OrderItem.modifiers))
        )
    )
    lines.extend(
        {
            "order_id": order.id,
            "name": item.menu_name_snapshot,
            "quantity": item.quantity,
            "unit_price": item.unit_price_snapshot,
            "line_total": item.line_total,
            "modifiers": [modifier.display_name for modifier in item.modifiers],
        }
        for order in shared_orders
        for item in order.items
        if item.status in {"confirmed", "cancel_requested"}
    )
    return {"session_id": session_id, "lines": lines, "total": sum(line["line_total"] for line in lines)}
