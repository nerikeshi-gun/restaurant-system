from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base
from app.models import MenuItem, TableSession
from app.schemas import ResolveOrderRequest, SharedItemCreate
from app.seed import seed_database
from app.services.ai_order import LocalMenuResolver, OpenAiOrderAdapter, RawCandidate, RawItem, RawResolution, menu_payload, resolve_order, validate_resolution
from app.services.menu_catalog import import_menu_csv, load_current_menu_version, snapshot_current_menu
from app.services.shared_orders import add_shared_item, get_or_create_shared_order
from app.default_translations import backfill_default_menu_translations


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_rule_resolver_handles_exact_shortened_misheard_quantity_option_and_multiple():
    with make_db() as db:
        seed_database(db)
        version = load_current_menu_version(db, settings.default_store_id)
        resolver = LocalMenuResolver()

        exact = resolver.resolve(ResolveOrderRequest(store_id=settings.default_store_id, recognized_text="Aランチを一つ"), version)
        assert exact.items[0].candidates[0].menu_id == "M001"

        shortened = resolver.resolve(ResolveOrderRequest(store_id=settings.default_store_id, recognized_text="アジフライ一つ"), version)
        assert shortened.items[0].candidates[0].menu_id == "M012"

        misheard = resolver.resolve(ResolveOrderRequest(store_id=settings.default_store_id, recognized_text="実験定食を一つ"), version)
        assert any(candidate.menu_id == "M012" for candidate in misheard.items[0].candidates)

        quantity = resolver.resolve(ResolveOrderRequest(store_id=settings.default_store_id, recognized_text="Aランチを二つ"), version)
        assert quantity.items[0].quantity == 2

        option = resolver.resolve(ResolveOrderRequest(store_id=settings.default_store_id, recognized_text="カレーを一つ、大盛"), version)
        assert "大盛" in option.items[0].candidates[0].option_candidates

        multiple = resolver.resolve(ResolveOrderRequest(store_id=settings.default_store_id, recognized_text="Aランチを一つ、アジフライ定食を一つ"), version)
        assert [item.candidates[0].menu_id for item in multiple.items] == ["M001", "M012"]

        next(item for item in version.items if item.menu_id == "M001").localized_names_json = '{"en":"Lunch Set A"}'
        english = resolver.resolve(ResolveOrderRequest(store_id=settings.default_store_id, recognized_text="two Lunch Set A", input_language="en"), version)
        assert english.items[0].candidates[0].menu_id == "M001"
        assert english.items[0].quantity == 2


def test_urdu_menu_name_and_quantity_are_resolved_locally():
    with make_db() as db:
        seed_database(db)
        backfill_default_menu_translations(db)
        version = load_current_menu_version(db, settings.default_store_id)
        result = LocalMenuResolver().resolve(
            ResolveOrderRequest(store_id=settings.default_store_id, recognized_text="دو کری چاول", input_language="ur"),
            version,
        )
        assert result.items[0].candidates[0].menu_id == "M035"
        assert result.items[0].quantity == 2


@pytest.mark.parametrize(
    ("language", "utterance"),
    [
        ("ja", "カレーライスを二つ"),
        ("en", "two Curry Rice"),
        ("zh", "两个咖喱饭"),
        ("ko", "카레라이스 둘"),
        ("vi", "hai Cơm cà ri"),
        ("ur", "دو کری چاول"),
    ],
)
def test_all_supported_languages_resolve_the_same_item_and_quantity(language, utterance):
    with make_db() as db:
        seed_database(db)
        backfill_default_menu_translations(db)
        version = load_current_menu_version(db, settings.default_store_id)
        result = LocalMenuResolver().resolve(
            ResolveOrderRequest(store_id=settings.default_store_id, recognized_text=utterance, input_language=language),
            version,
        )
        assert result.items[0].candidates[0].menu_id == "M035"
        assert result.items[0].quantity == 2


def test_not_found_sold_out_and_unknown_llm_menu_id_are_not_adopted():
    with make_db() as db:
        seed_database(db)
        version = load_current_menu_version(db, settings.default_store_id)
        request = ResolveOrderRequest(store_id=settings.default_store_id, recognized_text="宇宙丼を一つ")
        assert LocalMenuResolver().resolve(request, version).items == []

        hallucinated = RawResolution(items=[RawItem(source_phrase="宇宙丼", quantity=1, candidates=[RawCandidate(menu_id="M999")])])
        assert validate_resolution(hallucinated, request, version, "mock", None).items == []

        sold_out = next(item for item in version.items if item.menu_id == "M001")
        sold_out.sold_out = True
        db.commit()
        raw = RawResolution(items=[RawItem(source_phrase="Aランチ", quantity=1, candidates=[RawCandidate(menu_id="M001")])])
        assert validate_resolution(raw, request, version, "mock", None).items == []


def test_external_timeout_falls_back_without_stopping_orders(monkeypatch):
    with make_db() as db:
        seed_database(db)
        monkeypatch.setattr(settings, "llm_enabled", True)
        monkeypatch.setattr(settings, "openai_api_key", "not-sent")
        monkeypatch.setattr(settings, "llm_provider", "openai")
        monkeypatch.setattr(OpenAiOrderAdapter, "resolve", lambda *_: (_ for _ in ()).throw(TimeoutError("timeout")))
        result = resolve_order(db, ResolveOrderRequest(store_id=settings.default_store_id, recognized_text="Aランチを一つ"))
        assert result.provider == "local_fallback"
        assert result.items[0].candidates[0].menu_id == "M001"


def test_order_keeps_name_price_and_menu_version_after_menu_update():
    with make_db() as db:
        seed_database(db)
        session_id = db.scalar(select(TableSession.id).order_by(TableSession.id))
        menu_item = db.scalar(select(MenuItem).where(MenuItem.menu_code == "M001"))
        current = load_current_menu_version(db, settings.default_store_id)
        order = get_or_create_shared_order(db, session_id)
        order = add_shared_item(db, order.id, SharedItemCreate(menu_item_id=menu_item.id, quantity=1, modifier_option_ids=[], input_by="staff", expected_version=order.version, menu_version=current.version, llm_candidates=[{"menu_id": "M001"}], selected_candidate={"menu_item_id": menu_item.id, "menu_id": "M001"}))
        old_name = order.items[0].menu_name_snapshot
        old_price = order.items[0].unit_price_snapshot
        old_version = order.items[0].menu_version_snapshot

        menu_item.name = "新Aランチ"
        menu_item.price = 1200
        db.commit()
        snapshot_current_menu(db, settings.default_store_id, "next-version", datetime.now(timezone.utc) + timedelta(seconds=1))
        db.refresh(order.items[0])
        assert order.items[0].menu_name_snapshot == old_name
        assert order.items[0].unit_price_snapshot == old_price
        assert order.items[0].menu_version_snapshot == old_version


def test_full_menu_payload_and_csv_version_import():
    with make_db() as db:
        seed_database(db)
        current = load_current_menu_version(db, settings.default_store_id)
        current.items[0].sold_out = True
        db.commit()
        payload = menu_payload(current)
        assert len(payload) == len(current.items)
        assert any(item["sold_out"] for item in payload)

        csv_data = (
            "store_id,store_name,menu_version,menu_id,name,short_name,reading,aliases,price,size,set_contents,toppings,sold_out,localized_names,valid_from,valid_to\n"
            "STORE001,サンプル食堂,csv-version,M500,テスト定食,テスト,てすとていしょく,試験定食|テスト,980,,,大盛,false,{},2026-08-16T00:00:00+09:00,\n"
        ).encode("utf-8")
        result = import_menu_csv(db, csv_data)
        imported = load_current_menu_version(db, settings.default_store_id, datetime(2026, 8, 16, 1, tzinfo=timezone.utc))
        assert result["items"] == 1
        assert imported.version == "csv-version"
        assert imported.items[0].menu_id == "M500"


def test_category_exact_match_takes_priority_over_similar_menu_names():
    with make_db() as db:
        seed_database(db)
        csv_data = (
            "menu_id,name_ja,price,category,available,alias\n"
            "S001,グリーンサラダ,500,サラダ,1,野菜サラダ\n"
            "S002,バーベキューサラダ,600,サラダ,1,BBQサラダ\n"
            "C001,マトンマサラ,1000,カレー,1,マトンマサラカレー\n"
        ).encode("utf-8")
        import_menu_csv(db, csv_data)
        version = load_current_menu_version(db, settings.default_store_id)
        result = LocalMenuResolver().resolve(
            ResolveOrderRequest(store_id=settings.default_store_id, recognized_text="サラダ"),
            version,
        )
        assert [candidate.menu_id for candidate in result.items[0].candidates] == ["S001", "S002"]


def test_partial_keyword_plus_generic_food_word_returns_candidates():
    with make_db() as db:
        seed_database(db)
        csv_data = (
            "menu_id,name_ja,price,category,available,alias\n"
            "C000,カレーライス,750,カレー,1,カレー\n"
            "C001,マトンマサラ,1000,カレー,1,\n"
            "C002,マトン・ドリッパー,1100,カレー,1,\n"
            "C003,チキンマサラ,1000,カレー,1,\n"
        ).encode("utf-8")
        import_menu_csv(db, csv_data)
        version = load_current_menu_version(db, settings.default_store_id)
        result = LocalMenuResolver().resolve(
            ResolveOrderRequest(store_id=settings.default_store_id, recognized_text="マトンカレー"),
            version,
        )
        candidate_ids = [candidate.menu_id for candidate in result.items[0].candidates]
        assert candidate_ids == ["C001", "C002"]


def test_longer_overlapping_menu_name_wins():
    with make_db() as db:
        seed_database(db)
        csv_data = (
            "menu_id,name_ja,price,category,available,alias\n"
            "C001,海老カレー,1100,カレー,1,エビカレー\n"
            "T001,海老カレーセット,1850,セット,1,エビカレーセット\n"
        ).encode("utf-8")
        import_menu_csv(db, csv_data)
        version = load_current_menu_version(db, settings.default_store_id)
        result = LocalMenuResolver().resolve(
            ResolveOrderRequest(store_id=settings.default_store_id, recognized_text="エビカレーセット"),
            version,
        )
        assert [candidate.menu_id for candidate in result.items[0].candidates] == ["T001"]
