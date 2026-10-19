from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import MenuItem
from app.config import settings
from app.schemas import Candidate, CandidateItem, InterpretRequest, LlmInterpretation
from app.seed import seed_database
from app.services.interpreter import LocalFallbackInterpreter, OpenAIInterpreter, _validate_llm_result, interpret_input
from app.services.menu import load_available_menu


def test_local_fallback_finds_multiple_beer_brands():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_database(db)
        menu = load_available_menu(db)
        result = LocalFallbackInterpreter().interpret(
            InterpretRequest(session_id=1, text="生ビール"), menu
        )
        assert result.intent == "order"
        assert len(result.candidates) == 3


def test_unavailable_menu_id_is_removed_from_llm_output():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_database(db)
        menu = load_available_menu(db)
        result = LocalFallbackInterpreter().interpret(
            InterpretRequest(session_id=1, text="アサヒ"), menu
        )
        result.candidates[0].items[0].menu_item_id = 999999
        cleaned = _validate_llm_result(result, menu)
        assert cleaned.intent == "unknown"
        assert cleaned.candidates == []


def test_local_fallback_parses_multiple_items_and_last_change_quantity():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_database(db)
        menu = load_available_menu(db)
        multiple = LocalFallbackInterpreter().interpret(
            InterpretRequest(session_id=1, text="Aランチを一つ、アジフライ定食を二つ"), menu
        )
        assert len(multiple.candidates) == 1
        assert [item.quantity for item in multiple.candidates[0].items] == [1, 2]

        changed = LocalFallbackInterpreter().interpret(
            InterpretRequest(session_id=1, text="唐揚げを二つから一つに変更"), menu
        )
        assert changed.candidates[0].items[0].operation == "change"
        assert changed.candidates[0].items[0].quantity == 1


def test_primary_model_failure_uses_configured_fallback_model(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_database(db)
        menu_item = db.scalar(select(MenuItem).where(MenuItem.short_name == "唐揚げ"))
        monkeypatch.setattr(settings, "llm_enabled", True)
        monkeypatch.setattr(settings, "openai_api_key", "test-key-not-sent")
        monkeypatch.setattr(settings, "openai_model", "primary-test-model")
        monkeypatch.setattr(settings, "openai_fallback_model", "fallback-test-model")

        def fake_interpret(self, request, menu):
            if self.model_name == "primary-test-model":
                raise TimeoutError("primary timeout")
            return LlmInterpretation(
                intent="order",
                candidates=[
                    Candidate(
                        label="唐揚げ",
                        items=[CandidateItem(menu_item_id=menu_item.id, quantity=1)],
                    )
                ],
            )

        monkeypatch.setattr(OpenAIInterpreter, "interpret", fake_interpret)
        response = interpret_input(db, InterpretRequest(session_id=1, text="唐揚げひとつ"))
        assert response.provider == "openai"
        assert response.model_name == "fallback-test-model"
