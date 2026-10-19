import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import MenuItem, ModifierOption, TableSession
from app.schemas import OrderCreate, OrderItemCreate
from app.seed import seed_database
from app.services.orders import OrderValidationError, calculate_bill, create_order


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_database(session)
        yield session


def make_payload(db: Session, **changes) -> OrderCreate:
    session_id = db.scalar(select(TableSession.id))
    beer = db.scalar(select(MenuItem).where(MenuItem.short_name == "アサヒ"))
    values = {
        "session_id": session_id,
        "client_request_id": "test-request-0001",
        "confirmation_method": "touch_button",
        "items": [OrderItemCreate(menu_item_id=beer.id, quantity=2)],
    }
    values.update(changes)
    return OrderCreate(**values)


def test_submitted_order_is_not_billed_until_kitchen_confirms(db: Session):
    order = create_order(db, make_payload(db))
    assert calculate_bill(db, order.session_id)["total"] == 0

    order.status = "confirmed"
    db.commit()
    assert calculate_bill(db, order.session_id)["total"] == 1200


def test_price_is_calculated_from_database_and_modifier(db: Session):
    beer = db.scalar(select(MenuItem).where(MenuItem.short_name == "アサヒ"))
    large = db.scalar(select(ModifierOption).where(ModifierOption.name == "大"))
    payload = make_payload(
        db,
        items=[OrderItemCreate(menu_item_id=beer.id, quantity=2, modifier_option_ids=[large.id])],
    )
    order = create_order(db, payload)
    assert order.items[0].unit_price_snapshot == 850
    assert order.items[0].line_total == 1700


def test_option_from_another_product_is_rejected(db: Session):
    beer = db.scalar(select(MenuItem).where(MenuItem.short_name == "アサヒ"))
    large_serving = db.scalar(select(ModifierOption).where(ModifierOption.name == "大盛"))
    payload = make_payload(
        db,
        items=[OrderItemCreate(menu_item_id=beer.id, quantity=1, modifier_option_ids=[large_serving.id])],
    )
    with pytest.raises(OrderValidationError):
        create_order(db, payload)


def test_client_request_id_prevents_duplicate_orders(db: Session):
    payload = make_payload(db)
    first = create_order(db, payload)
    second = create_order(db, payload)
    assert first.id == second.id

