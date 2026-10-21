import sqlite3

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.seed import seed_database
from tools.sqlite_to_platform_sql import build_sql, q, qj


@pytest.fixture()
def seeded_sqlite(tmp_path):
    path = tmp_path / "restaurant.db"
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_database(db)
    engine.dispose()
    conn = sqlite3.connect(path)
    yield conn
    conn.close()


def test_quote_helpers_escape_sql_and_keep_japanese():
    assert q("O'Brien") == "'O''Brien'"
    assert qj({"name": "生ビール", "note": "it's"}) == "'{\"name\":\"生ビール\",\"note\":\"it''s\"}'::jsonb"


def test_every_master_row_is_exported_once(seeded_sqlite):
    conn = seeded_sqlite
    sql, counts = build_sql(conn, tenant_code="test-tenant")

    assert counts["product"] == conn.execute("SELECT count(*) FROM menu_items").fetchone()[0]
    assert counts["location"] == 1 + conn.execute("SELECT count(*) FROM dining_tables").fetchone()[0]
    assert counts["modifier_group"] == conn.execute(
        "SELECT count(*) FROM menu_categories WHERE is_option_group = 1"
    ).fetchone()[0]
    assert sql.count("SELECT pg_temp.upsert_record(") == sum(
        counts[k] for k in ("product", "location", "modifier_group", "modifier_option")
    )
    assert sql.startswith("-- sqlite_to_platform_sql.py")
    assert "BEGIN;" in sql and sql.rstrip().endswith("COMMIT;")
    assert "'test-tenant'" in sql


def test_special_characters_and_status_mapping(seeded_sqlite):
    conn = seeded_sqlite
    conn.execute("UPDATE menu_items SET name = ? WHERE id = 1", ("Chef's \"Special\" 定食",))
    conn.execute("UPDATE menu_items SET is_archived = 1 WHERE id = 2")
    conn.commit()
    sql, _ = build_sql(conn, tenant_code="t")

    assert "'Chef''s \"Special\" 定食'" in sql
    archived_code = conn.execute("SELECT menu_code FROM menu_items WHERE id = 2").fetchone()[0]
    assert f"'{archived_code}', 'archived'" in sql


def test_sold_out_and_sqlite_runtime_state_are_not_exported(seeded_sqlite):
    sql, _ = build_sql(seeded_sqlite, tenant_code="t")
    # 販売可否・テーブルの利用状態・現在の注文はマスタではないため含めない
    assert "is_available" not in sql
    assert "usage_status" not in sql
    assert "current_order_id" not in sql


def test_tax_category_default_is_configurable(seeded_sqlite):
    sql, _ = build_sql(seeded_sqlite, tenant_code="t", default_tax_category="reduced")
    assert '"tax_category":"reduced"' in sql
    assert '"tax_category":"standard"' not in sql
