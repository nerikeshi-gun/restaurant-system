from sqlalchemy import create_engine, inspect, text

from app import models  # noqa: F401
from app.database import Base
from app.migrations import ensure_sqlite_schema


def test_existing_kitchen_messages_are_dismissed_when_column_is_added(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE messages"))
        connection.execute(text(
            "CREATE TABLE messages ("
            "id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL, "
            "sender_type VARCHAR(20) NOT NULL, text TEXT NOT NULL, created_at DATETIME)"
        ))
        connection.execute(text(
            "INSERT INTO messages (id, session_id, sender_type, text) "
            "VALUES (1, 1, 'kitchen', 'old reply'), (2, 1, 'customer', 'question')"
        ))

    ensure_sqlite_schema(engine)

    assert "dismissed_at" in {column["name"] for column in inspect(engine).get_columns("messages")}
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT id, dismissed_at FROM messages ORDER BY id")
        ).all()
        migration = connection.execute(text(
            "SELECT name FROM schema_migrations "
            "WHERE name = 'dismiss_existing_kitchen_messages'"
        )).scalar_one()

    assert rows[0].dismissed_at is not None
    assert rows[1].dismissed_at is None
    assert migration == "dismiss_existing_kitchen_messages"

    ensure_sqlite_schema(engine)
