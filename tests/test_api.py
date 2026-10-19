import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import DiningTable, TableSession
from app.seed import seed_database


@pytest.fixture()
def api_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
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


def test_pages_and_interpretation_smoke(api_client):
    client, engine = api_client
    assert client.get("/").status_code == 200
    assert client.get("/kitchen").status_code == 200
    assert client.get("/admin").status_code == 200
    menu = client.get("/api/v1/menu")
    assert menu.status_code == 200
    assert len(menu.json()) >= 6

    with Session(engine) as db:
        table = db.scalar(select(DiningTable).order_by(DiningTable.id))
        session = db.scalar(select(TableSession).where(TableSession.table_id == table.id))
        token = table.access_token
        session_id = session.id

    assert client.get(f"/t/{token}").status_code == 200
    response = client.post(
        "/api/v1/input/interpret",
        json={"session_id": session_id, "text": "生ビール", "stt_alternatives": []},
    )
    assert response.status_code == 200
    assert response.json()["state"] == "needs_item_choice"
    assert len(response.json()["candidates"]) == 3

    resolved = client.post(
        "/api/ai/resolve-order",
        json={"store_id": "STORE001", "recognized_text": "実験定食を一つ", "input_language": "ja"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] in {"needs_confirmation", "ambiguous"}
    assert resolved.json()["items"][0]["candidates"][0]["menu_id"] == "M012"
