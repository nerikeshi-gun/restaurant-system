from sqlalchemy import Engine, inspect, text


SQLITE_COLUMNS: dict[str, dict[str, str]] = {
    "stores": {
        "theme_color": "VARCHAR(7) NOT NULL DEFAULT '#b74328'",
        "ui_layout_json": "TEXT NOT NULL DEFAULT '{\"desktop\":{\"block_order\":[\"input\",\"menu\",\"service\"],\"order_position\":\"right\"},\"tablet\":{\"block_order\":[\"input\",\"menu\",\"service\"],\"order_position\":\"right\"}}'",
    },
    "dining_tables": {
        "usage_status": "VARCHAR(30) NOT NULL DEFAULT 'available'",
        "current_order_id": "INTEGER",
    },
    "menu_items": {
        "store_id": "VARCHAR(40) NOT NULL DEFAULT 'STORE001'",
        "menu_code": "VARCHAR(80)",
        "reading": "VARCHAR(200) NOT NULL DEFAULT ''",
        "size_label": "VARCHAR(100) NOT NULL DEFAULT ''",
        "set_contents": "TEXT NOT NULL DEFAULT ''",
        "localized_names_json": "TEXT NOT NULL DEFAULT '{}'",
        "is_archived": "BOOLEAN NOT NULL DEFAULT 0",
    },
    "menu_categories": {
        "is_menu_category": "BOOLEAN NOT NULL DEFAULT 1",
        "is_option_group": "BOOLEAN NOT NULL DEFAULT 0",
        "selection_type": "VARCHAR(20) NOT NULL DEFAULT 'single'",
        "is_active": "BOOLEAN NOT NULL DEFAULT 1",
    },
    "menu_version_items": {
        "category_name": "VARCHAR(100) NOT NULL DEFAULT ''",
    },
    "modifier_groups": {
        "display_order": "INTEGER NOT NULL DEFAULT 0",
        "is_active": "BOOLEAN NOT NULL DEFAULT 1",
    },
    "modifier_options": {
        "display_order": "INTEGER NOT NULL DEFAULT 0",
        "is_available": "BOOLEAN NOT NULL DEFAULT 1",
    },
    "menu_item_modifier_groups": {
        "display_order": "INTEGER NOT NULL DEFAULT 0",
    },
    "orders": {
        "transaction_id": "VARCHAR(36)",
        "business_date": "VARCHAR(10)",
        "display_number": "INTEGER",
        "updated_at": "DATETIME",
        "version": "INTEGER NOT NULL DEFAULT 1",
        "confirmation_batches": "INTEGER NOT NULL DEFAULT 0",
        "confirmed_by": "VARCHAR(20)",
        "confirmation_method": "VARCHAR(30)",
    },
    "order_items": {
        "menu_version_snapshot": "VARCHAR(80)",
        "llm_candidates_json": "TEXT NOT NULL DEFAULT '[]'",
        "selected_candidate_json": "TEXT NOT NULL DEFAULT '{}'",
        "status": "VARCHAR(30) NOT NULL DEFAULT 'draft'",
        "kitchen_status": "VARCHAR(30) NOT NULL DEFAULT 'not_started'",
        "input_by": "VARCHAR(20) NOT NULL DEFAULT 'customer'",
        "input_language": "VARCHAR(20) NOT NULL DEFAULT 'ja'",
        "input_at": "DATETIME",
        "original_text": "TEXT",
        "notes": "TEXT NOT NULL DEFAULT ''",
        "change_type": "VARCHAR(20) NOT NULL DEFAULT 'added'",
        "previous_quantity": "INTEGER",
        "submission_batch": "INTEGER NOT NULL DEFAULT 0",
        "confirmed_at": "DATETIME",
    },
    "order_item_modifiers": {
        "group_name_snapshot": "VARCHAR(100) NOT NULL DEFAULT ''",
    },
    "interpretations": {
        "store_id": "VARCHAR(40)",
        "menu_version": "VARCHAR(80)",
    },
    "messages": {
        "dismissed_at": "DATETIME",
    },
}


def ensure_sqlite_schema(engine: Engine) -> None:
    """create_allでは追加されない既存SQLiteの列だけを安全に補う。"""
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table_name, definitions in SQLITE_COLUMNS.items():
            if not inspector.has_table(table_name):
                continue
            existing = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, definition in definitions.items():
                if column_name not in existing:
                    connection.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {definition}'))
        connection.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations (name VARCHAR(100) PRIMARY KEY)"))
        dismissed_existing_messages = connection.execute(
            text("SELECT 1 FROM schema_migrations WHERE name = 'dismiss_existing_kitchen_messages'")
        ).scalar()
        if not dismissed_existing_messages and inspector.has_table("messages"):
            connection.execute(text(
                "UPDATE messages SET dismissed_at = CURRENT_TIMESTAMP "
                "WHERE sender_type = 'kitchen' AND dismissed_at IS NULL"
            ))
            connection.execute(text(
                "INSERT INTO schema_migrations (name) VALUES ('dismiss_existing_kitchen_messages')"
            ))
        unified = connection.execute(text("SELECT 1 FROM schema_migrations WHERE name = 'unify_menu_and_option_groups'" )).scalar()
        if not unified and inspector.has_table("modifier_groups"):
            connection.execute(text(
                "INSERT INTO menu_categories (name, display_order, is_menu_category, is_option_group, selection_type, is_active) "
                "SELECT name, display_order, 0, 1, selection_type, is_active FROM modifier_groups "
                "WHERE NOT EXISTS (SELECT 1 FROM menu_categories WHERE menu_categories.name = modifier_groups.name)"
            ))
            connection.execute(text(
                "UPDATE menu_categories SET is_option_group = 1, "
                "selection_type = COALESCE((SELECT selection_type FROM modifier_groups WHERE modifier_groups.name = menu_categories.name), selection_type), "
                "is_active = COALESCE((SELECT is_active FROM modifier_groups WHERE modifier_groups.name = menu_categories.name), is_active) "
                "WHERE name IN (SELECT name FROM modifier_groups)"
            ))
            connection.execute(text(
                "UPDATE modifier_options SET group_id = COALESCE((SELECT menu_categories.id FROM modifier_groups "
                "JOIN menu_categories ON menu_categories.name = modifier_groups.name "
                "WHERE modifier_groups.id = modifier_options.group_id), group_id)"
            ))
            connection.execute(text(
                "UPDATE menu_item_modifier_groups SET group_id = COALESCE((SELECT menu_categories.id FROM modifier_groups "
                "JOIN menu_categories ON menu_categories.name = modifier_groups.name "
                "WHERE modifier_groups.id = menu_item_modifier_groups.group_id), group_id)"
            ))
        if not unified:
            connection.execute(text("INSERT INTO schema_migrations (name) VALUES ('unify_menu_and_option_groups')"))
        required_spiciness = connection.execute(text("SELECT 1 FROM schema_migrations WHERE name = 'require_spiciness_options'" )).scalar()
        if not required_spiciness and inspector.has_table("menu_item_modifier_groups"):
            connection.execute(text(
                "UPDATE menu_item_modifier_groups SET required = 1 WHERE group_id IN ("
                "SELECT id FROM menu_categories WHERE is_option_group = 1 AND name LIKE '%辛さ%'"
                ")"
            ))
            connection.execute(text("INSERT INTO schema_migrations (name) VALUES ('require_spiciness_options')"))
        connection.execute(text("UPDATE orders SET updated_at = created_at WHERE updated_at IS NULL"))
        connection.execute(text("UPDATE order_items SET input_at = CURRENT_TIMESTAMP WHERE input_at IS NULL"))
        connection.execute(text(
            "UPDATE menu_version_items SET category_name = COALESCE(("
            "SELECT menu_categories.name FROM menu_items "
            "JOIN menu_categories ON menu_categories.id = menu_items.category_id "
            "WHERE menu_items.id = menu_version_items.menu_item_id"
            "), '') WHERE category_name = ''"
        ))
        connection.execute(text(
            "UPDATE order_item_modifiers SET group_name_snapshot = COALESCE(("
            "SELECT menu_categories.name FROM modifier_options "
            "JOIN menu_categories ON menu_categories.id = modifier_options.group_id "
            "WHERE modifier_options.id = order_item_modifiers.modifier_option_id"
            "), '') WHERE group_name_snapshot = ''"
        ))
