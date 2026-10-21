import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import MenuItem, OrderItem, ServiceRequest, TableSession
from app.seed import seed_database


@pytest.fixture()
def customer_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_database(db)

    def override_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            yield client, engine
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)


def current_order(client):
    return client.get("/api/v1/tables/1/shared-order").json()


def available_menu(client):
    return client.get("/api/v1/menu").json()


def add_item(client, order, menu_item_id, *, quantity=1, language="ja", version=None):
    return client.post(
        f"/api/v1/shared-orders/{order['id']}/items",
        json={
            "menu_item_id": menu_item_id,
            "quantity": quantity,
            "modifier_option_ids": [],
            "input_by": "customer",
            "input_language": language,
            "expected_version": version or order["version"],
        },
    )


def confirm(client, order, *, version=None):
    return client.post(
        f"/api/v1/shared-orders/{order['id']}/confirm",
        json={
            "expected_version": version or order["version"],
            "confirmed_by": "customer",
            "confirmation_method": "touch_button",
        },
    )


@pytest.mark.parametrize("mode", ["voice", "menu"])
def test_scenario_skip_entry_pages_direct_mode_url_is_recoverable(customer_client, mode):
    client, _ = customer_client
    response = client.get(f"/table/1/order?lang=ja&mode={mode}")
    assert response.status_code == 200
    assert f'order-mode-{mode}' in response.text
    assert 'data-start-url="/table/1/order?lang=ja"' in response.text
    assert "/staff" not in response.text


def test_scenario_wrong_url_parameters_fall_back_to_safe_customer_choice(customer_client):
    client, _ = customer_client
    response = client.get("/table/1/order?lang=invalid&mode=staff")
    assert response.status_code == 200
    assert 'data-language="ja"' in response.text
    assert 'data-order-mode="choice"' in response.text
    assert 'data-start-url="/table/1/order?lang=ja"' in response.text


def test_scenario_reload_and_mode_change_keep_the_same_draft(customer_client):
    client, _ = customer_client
    order = current_order(client)
    menu_item_id = available_menu(client)[0]["id"]
    added = add_item(client, order, menu_item_id, quantity=2).json()

    assert client.get("/table/1/order?lang=ja&mode=voice").status_code == 200
    assert client.get("/table/1/order?lang=en&mode=menu").status_code == 200
    restored = current_order(client)
    assert restored["id"] == order["id"]
    assert restored["version"] == added["version"]
    assert [(item["menu_item_id"], item["quantity"], item["status"]) for item in restored["items"]] == [
        (menu_item_id, 2, "draft")
    ]


@pytest.mark.parametrize("bad_quantity", [0, 100, -1])
def test_scenario_invalid_quantity_then_valid_retry_succeeds(customer_client, bad_quantity):
    client, _ = customer_client
    order = current_order(client)
    menu_item_id = available_menu(client)[0]["id"]
    rejected = add_item(client, order, menu_item_id, quantity=bad_quantity)
    assert rejected.status_code == 422
    assert current_order(client)["items"] == []

    retried = add_item(client, order, menu_item_id, quantity=1)
    assert retried.status_code == 200
    assert retried.json()["items"][0]["quantity"] == 1


def test_scenario_double_add_is_rejected_without_duplicate_line(customer_client):
    client, engine = customer_client
    order = current_order(client)
    menu_item_id = available_menu(client)[0]["id"]
    first = add_item(client, order, menu_item_id)
    second = add_item(client, order, menu_item_id)
    assert first.status_code == 200
    assert second.status_code == 409
    assert len(current_order(client)["items"]) == 1
    with Session(engine) as db:
        assert db.scalar(select(func.count(OrderItem.id))) == 1


def test_scenario_stale_screen_refresh_then_retry_succeeds(customer_client):
    client, _ = customer_client
    stale = current_order(client)
    first_id, second_id = [item["id"] for item in available_menu(client)[:2]]
    assert add_item(client, stale, first_id).status_code == 200
    conflict = add_item(client, stale, second_id)
    assert conflict.status_code == 409

    refreshed = current_order(client)
    retry = add_item(client, refreshed, second_id)
    assert retry.status_code == 200
    assert [item["menu_item_id"] for item in retry.json()["items"]] == [first_id, second_id]


def test_scenario_empty_confirm_then_add_and_confirm_recovers(customer_client):
    client, _ = customer_client
    order = current_order(client)
    assert confirm(client, order).status_code == 422
    assert current_order(client)["items"] == []

    added = add_item(client, order, available_menu(client)[0]["id"]).json()
    confirmed = confirm(client, added)
    assert confirmed.status_code == 200
    assert confirmed.json()["items"][0]["status"] == "confirmed"


def test_scenario_double_confirm_does_not_send_twice(customer_client):
    client, engine = customer_client
    order = current_order(client)
    added = add_item(client, order, available_menu(client)[0]["id"]).json()
    first = confirm(client, added)
    second = confirm(client, added)
    assert first.status_code == 200
    assert second.status_code in {409, 422}
    restored = current_order(client)
    assert len([item for item in restored["items"] if item["status"] == "confirmed"]) == 1
    with Session(engine) as db:
        assert db.scalar(select(func.count(OrderItem.id))) == 1


def test_scenario_accidental_draft_cancel_then_reselect_and_confirm(customer_client):
    client, _ = customer_client
    order = current_order(client)
    menu_item_id = available_menu(client)[0]["id"]
    added = add_item(client, order, menu_item_id).json()
    item_id = added["items"][0]["id"]
    cancelled = client.post(
        f"/api/v1/shared-orders/{order['id']}/items/{item_id}/cancel",
        json={"expected_version": added["version"], "input_by": "customer"},
    ).json()
    assert cancelled["items"][0]["status"] == "cancelled"

    reselected = add_item(client, cancelled, menu_item_id).json()
    confirmed = confirm(client, reselected)
    assert confirmed.status_code == 200
    assert [item["status"] for item in confirmed.json()["items"]] == ["cancelled", "confirmed"]


def customer_cancel(client, order, item_id, version):
    return client.post(
        f"/api/v1/shared-orders/{order['id']}/items/{item_id}/cancel",
        json={"expected_version": version, "input_by": "customer"},
    )


def test_scenario_confirmed_cancel_before_cooking_then_order_again(customer_client):
    client, _ = customer_client
    order = current_order(client)
    menu_item_id = available_menu(client)[0]["id"]
    added = add_item(client, order, menu_item_id).json()
    confirmed = confirm(client, added).json()
    item_id = confirmed["items"][0]["id"]

    # 確定後の取消は依頼になり、厨房が承認するまでは金額も残る
    requested = customer_cancel(client, order, item_id, confirmed["version"])
    assert requested.status_code == 200
    assert requested.json()["items"][0]["status"] == "cancel_requested"
    assert requested.json()["current_total"] > 0

    approved = client.post(f"/api/v1/kitchen/items/{item_id}/cancel-request/approve")
    assert approved.status_code == 200
    assert approved.json()["items"][0]["status"] == "cancelled"
    assert approved.json()["current_total"] == 0

    reordered = add_item(client, approved.json(), menu_item_id).json()
    assert confirm(client, reordered).status_code == 200


def test_scenario_cancel_request_during_cooking_rejected_by_kitchen_and_state_survives(customer_client):
    client, _ = customer_client
    order = current_order(client)
    added = add_item(client, order, available_menu(client)[0]["id"]).json()
    confirmed = confirm(client, added).json()
    item_id = confirmed["items"][0]["id"]
    cooking = client.patch(f"/api/v1/kitchen/items/{item_id}/status", json={"status": "preparing"}).json()

    # 調理中でも依頼は出せるが、厨房が断れば確定・調理中の状態へ戻る
    requested = customer_cancel(client, order, item_id, cooking["version"])
    assert requested.status_code == 200
    assert requested.json()["items"][0]["status"] == "cancel_requested"
    rejected = client.post(f"/api/v1/kitchen/items/{item_id}/cancel-request/reject")
    assert rejected.status_code == 200

    restored = current_order(client)
    assert restored["items"][0]["status"] == "confirmed"
    assert restored["items"][0]["kitchen_status"] == "preparing"


def test_scenario_cancel_after_served_rejected_and_order_state_survives(customer_client):
    client, _ = customer_client
    order = current_order(client)
    added = add_item(client, order, available_menu(client)[0]["id"]).json()
    confirmed = confirm(client, added).json()
    item_id = confirmed["items"][0]["id"]
    client.patch(f"/api/v1/kitchen/items/{item_id}/status", json={"status": "preparing"})
    served = client.patch(f"/api/v1/kitchen/items/{item_id}/status", json={"status": "served"}).json()

    rejected = customer_cancel(client, order, item_id, served["version"])
    assert rejected.status_code == 422
    restored = current_order(client)
    assert restored["items"][0]["status"] == "confirmed"
    assert restored["items"][0]["kitchen_status"] == "served"


def test_scenario_wrong_table_item_rejected_then_own_item_still_operable(customer_client):
    client, _ = customer_client
    first = current_order(client)
    second = client.get("/api/v1/tables/2/shared-order").json()
    item_id = add_item(client, first, available_menu(client)[0]["id"]).json()["items"][0]["id"]
    wrong = client.patch(
        f"/api/v1/shared-orders/{second['id']}/items/{item_id}",
        json={"quantity": 2, "expected_version": second["version"]},
    )
    assert wrong.status_code == 422
    own = current_order(client)
    corrected = client.patch(
        f"/api/v1/shared-orders/{first['id']}/items/{item_id}",
        json={"quantity": 2, "expected_version": own["version"]},
    )
    assert corrected.status_code == 200
    assert corrected.json()["items"][0]["quantity"] == 2


def test_scenario_sold_out_after_menu_display_then_reselect_available_item(customer_client):
    client, engine = customer_client
    order = current_order(client)
    menu = available_menu(client)
    sold_out_id, fallback_id = menu[0]["id"], menu[1]["id"]
    with Session(engine) as db:
        db.get(MenuItem, sold_out_id).is_available = False
        db.commit()
    rejected = add_item(client, order, sold_out_id)
    assert rejected.status_code == 422
    assert "売り切れ" in rejected.json()["detail"]
    assert all(item["id"] != sold_out_id for item in available_menu(client))
    assert add_item(client, order, fallback_id).status_code == 200


def test_scenario_checkout_double_tap_is_idempotent_and_order_can_reload(customer_client):
    client, engine = customer_client
    with Session(engine) as db:
        session_id = db.scalar(select(TableSession.id).order_by(TableSession.id))
    payload = {"session_id": session_id, "request_type": "checkout", "message": ""}
    first = client.post("/api/v1/service-requests", json=payload)
    second = client.post("/api/v1/service-requests", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert client.get(f"/api/v1/sessions/{session_id}/shared-order").status_code == 200
    with Session(engine) as db:
        assert db.scalar(select(func.count(ServiceRequest.id))) == 1


def test_scenario_empty_inquiry_rejected_then_text_retry_succeeds(customer_client):
    client, engine = customer_client
    with Session(engine) as db:
        session_id = db.scalar(select(TableSession.id).order_by(TableSession.id))
    empty = client.post(
        "/api/v1/service-requests",
        json={"session_id": session_id, "request_type": "other", "message": "   "},
    )
    assert empty.status_code == 422
    retry = client.post(
        "/api/v1/service-requests",
        json={"session_id": session_id, "request_type": "other", "message": "子ども用のスプーン"},
    )
    assert retry.status_code == 200


def test_scenario_closed_session_rejects_page_order_and_requests(customer_client):
    client, engine = customer_client
    with Session(engine) as db:
        session = db.scalar(select(TableSession).order_by(TableSession.id))
        session_id = session.id
        session.status = "closed"
        db.commit()
    assert client.get("/table/1/order?lang=ja&mode=menu").status_code == 409
    assert client.get(f"/api/v1/sessions/{session_id}/shared-order").status_code == 409
    request = client.post(
        "/api/v1/service-requests",
        json={"session_id": session_id, "request_type": "other", "message": "呼び出し"},
    )
    assert request.status_code == 409
