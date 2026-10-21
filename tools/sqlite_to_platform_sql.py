"""現行SQLite(MVP)のマスタを、共通基盤DB(PostgreSQL, platformスキーマ)の投入SQLへ変換する。

標準ライブラリだけで動き、SQLiteは読み取り専用で開く。出力されたSQLをpsqlで適用する。

    python tools/sqlite_to_platform_sql.py --db data/restaurant.db --out tmp/migration.sql
    psql -v ON_ERROR_STOP=1 -d <db> -f tmp/migration.sql

移行する範囲（マスタのみ）：店舗、席、商品、調整分類・選択肢、それらの関係。
移行しない範囲：注文履歴、来店セッション、販売可否（売り切れ）、店舗の画面設定。
何度適用しても同じ結果になる（business_key で upsert）。

出力には席のQRトークンが含まれるため、リポジトリへコミットしない（tmp/ は除外済み）。
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ENTITY_MODULE = {
    "location": "party",
    "product": "catalog",
    "modifier_group": "catalog",
    "modifier_option": "catalog",
}


def q(value: str) -> str:
    """SQLの文字列リテラル。"""
    return "'" + str(value).replace("'", "''") + "'"


def qj(value) -> str:
    """JSONBリテラル。"""
    return q(json.dumps(value, ensure_ascii=False, separators=(",", ":"))) + "::jsonb"


def compact(data: dict) -> dict:
    """空文字・Noneの項目は定義済みでも入れない（必須項目は呼び出し側で保証する）。"""
    return {k: v for k, v in data.items() if v not in (None, "")}


def status_of(active: bool, archived: bool = False) -> str:
    if archived:
        return "archived"
    return "active" if active else "inactive"


def build_sql(
    conn: sqlite3.Connection,
    *,
    tenant_code: str,
    tenant_name: str | None = None,
    default_tax_category: str = "standard",
) -> tuple[str, dict]:
    conn.row_factory = sqlite3.Row
    store = conn.execute("SELECT * FROM stores ORDER BY id LIMIT 1").fetchone()
    if store is None:
        raise SystemExit("stores が空です。移行元のDBを確認してください。")
    store_key = store["id"]
    tenant_name = tenant_name or store["name"]

    categories = {r["id"]: r for r in conn.execute("SELECT * FROM menu_categories")}
    groups = [r for r in categories.values() if r["is_option_group"]]
    options = conn.execute("SELECT * FROM modifier_options ORDER BY group_id, display_order, id").fetchall()
    aliases: dict[int, list[str]] = {}
    for r in conn.execute("SELECT menu_item_id, alias FROM menu_aliases ORDER BY id"):
        aliases.setdefault(r["menu_item_id"], []).append(r["alias"])
    items = conn.execute("SELECT * FROM menu_items ORDER BY id").fetchall()
    item_key = {r["id"]: (r["menu_code"] or f"ITEM-{r['id']}") for r in items}
    links = conn.execute(
        "SELECT * FROM menu_item_modifier_groups ORDER BY menu_item_id, display_order, id"
    ).fetchall()
    tables = conn.execute("SELECT * FROM dining_tables ORDER BY number").fetchall()

    out: list[str] = []
    counts = {"location": 0, "product": 0, "modifier_group": 0, "modifier_option": 0, "relation": 0}

    def source(table: str, row_id) -> dict:
        return {"source": "sqlite", "table": table, "id": row_id}

    out.append("-- sqlite_to_platform_sql.py が生成。手で編集せず、移行元から再生成すること。")
    out.append("BEGIN;")
    out.append("SET search_path = platform, public;")
    out.append("SELECT set_config('app.change_reason', 'MVP SQLiteからのマスタ移行', true);")
    out.append(f"""
INSERT INTO tenants (tenant_code, tenant_name, industry_code)
VALUES ({q(tenant_code)}, {q(tenant_name)}, 'restaurant')
ON CONFLICT (tenant_code) DO UPDATE SET tenant_name = EXCLUDED.tenant_name;

INSERT INTO actors (tenant_id, actor_type, actor_code, display_name)
SELECT tenant_id, 'system', 'migration', 'SQLite移行' FROM tenants WHERE tenant_code = {q(tenant_code)}
ON CONFLICT ON CONSTRAINT uq_actors_tenant_code DO NOTHING;

-- 補助関数：セッション内でのみ有効
CREATE FUNCTION pg_temp.upsert_record(
    p_tenant text, p_entity text, p_module text, p_key text, p_status text,
    p_name text, p_data jsonb, p_source jsonb
) RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE v_tenant uuid; v_actor uuid; v_def uuid;
BEGIN
    SELECT tenant_id INTO v_tenant FROM tenants WHERE tenant_code = p_tenant;
    SELECT actor_id INTO v_actor FROM actors WHERE tenant_id = v_tenant AND actor_code = 'migration';
    SELECT entity_definition_id INTO v_def FROM effective_entity_definition(p_module, 'record', p_entity, v_tenant);
    IF v_def IS NULL THEN RAISE EXCEPTION 'entity definition % not found', p_entity; END IF;
    INSERT INTO business_records
        (tenant_id, entity_definition_id, business_key, record_status, display_name, data, source_ref, created_by, updated_by)
    VALUES (v_tenant, v_def, p_key, p_status::record_status, p_name, p_data, p_source, v_actor, v_actor)
    ON CONFLICT (tenant_id, entity_definition_id, business_key) DO UPDATE
        SET record_status = EXCLUDED.record_status, display_name = EXCLUDED.display_name,
            data = EXCLUDED.data, source_ref = EXCLUDED.source_ref, updated_by = EXCLUDED.updated_by
        WHERE (business_records.record_status, business_records.display_name, business_records.data, business_records.source_ref)
              IS DISTINCT FROM (EXCLUDED.record_status, EXCLUDED.display_name, EXCLUDED.data, EXCLUDED.source_ref);
END $fn$;

CREATE FUNCTION pg_temp.relate(
    p_tenant text, p_from_entity text, p_from_module text, p_from_key text,
    p_to_entity text, p_to_module text, p_to_key text, p_type text, p_attrs jsonb
) RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE v_tenant uuid; v_actor uuid; v_from uuid; v_to uuid;
BEGIN
    SELECT tenant_id INTO v_tenant FROM tenants WHERE tenant_code = p_tenant;
    SELECT actor_id INTO v_actor FROM actors WHERE tenant_id = v_tenant AND actor_code = 'migration';
    SELECT r.record_id INTO v_from FROM business_records r
      JOIN effective_entity_definition(p_from_module, 'record', p_from_entity, v_tenant) d ON d.entity_definition_id = r.entity_definition_id
     WHERE r.tenant_id = v_tenant AND r.business_key = p_from_key;
    SELECT r.record_id INTO v_to FROM business_records r
      JOIN effective_entity_definition(p_to_module, 'record', p_to_entity, v_tenant) d ON d.entity_definition_id = r.entity_definition_id
     WHERE r.tenant_id = v_tenant AND r.business_key = p_to_key;
    IF v_from IS NULL OR v_to IS NULL THEN
        RAISE EXCEPTION 'relation endpoint not found: % %/% -> %/%', p_type, p_from_entity, p_from_key, p_to_entity, p_to_key;
    END IF;
    INSERT INTO record_relations (tenant_id, from_record_id, to_record_id, relation_type, attributes, created_by)
    VALUES (v_tenant, v_from, v_to, p_type, p_attrs, v_actor)
    ON CONFLICT (tenant_id, from_record_id, to_record_id, relation_type)
    DO UPDATE SET attributes = EXCLUDED.attributes
        WHERE record_relations.attributes IS DISTINCT FROM EXCLUDED.attributes;
END $fn$;
""")

    def rec(entity: str, key: str, status: str, name: str, data: dict, src: dict) -> None:
        counts[entity] += 1
        out.append(
            f"SELECT pg_temp.upsert_record({q(tenant_code)}, {q(entity)}, {q(ENTITY_MODULE[entity])}, "
            f"{q(key)}, {q(status)}, {q(name)}, {qj(data)}, {qj(src)});"
        )

    def rel(from_entity: str, from_key: str, to_entity: str, to_key: str, rtype: str, attrs: dict | None = None) -> None:
        counts["relation"] += 1
        out.append(
            f"SELECT pg_temp.relate({q(tenant_code)}, {q(from_entity)}, {q(ENTITY_MODULE[from_entity])}, "
            f"{q(from_key)}, {q(to_entity)}, {q(ENTITY_MODULE[to_entity])}, {q(to_key)}, "
            f"{q(rtype)}, {qj(attrs or {})});"
        )

    out.append("-- 店舗")
    rec("location", store_key, status_of(bool(store["is_active"])), store["name"],
        {"location_type": "store"}, source("stores", store_key))

    out.append("-- 席")
    for t in tables:
        key = f"{store_key}-T{t['number']}"
        rec("location", key, status_of(bool(t["is_active"])), f"{t['number']}番テーブル",
            compact({"location_type": "table", "qr_token": t["access_token"]}),
            source("dining_tables", t["id"]))
        rel("location", key, "location", store_key, "located_in")

    out.append("-- 調整分類")
    group_key = {}
    for g in groups:
        key = f"MG{g['id']}"
        group_key[g["id"]] = key
        rec("modifier_group", key, status_of(bool(g["is_active"])), g["name"],
            {"selection_type": g["selection_type"] or "single"}, source("menu_categories", g["id"]))

    out.append("-- 調整選択肢")
    for o in options:
        if o["group_id"] not in group_key:
            continue  # 参照先の分類がないものは移行しない
        key = f"{group_key[o['group_id']]}-O{o['id']}"
        rec("modifier_option", key, status_of(bool(o["is_available"])), o["name"],
            {"price_delta": o["price_delta"], "is_default": bool(o["is_default"])},
            source("modifier_options", o["id"]))
        rel("modifier_option", key, "modifier_group", group_key[o["group_id"]], "option_of")

    out.append("-- 商品")
    for it in items:
        key = item_key[it["id"]]
        category = categories.get(it["category_id"])
        try:
            localized = json.loads(it["localized_names_json"]) if it["localized_names_json"] else {}
        except json.JSONDecodeError:
            localized = {}
        data = compact({
            "kitchen_name": it["short_name"],
            "price": it["price"],
            "tax_category": default_tax_category,
            "category": category["name"] if category else None,
            "aliases": aliases.get(it["id"]) or None,
            "reading": it["reading"],
            "size_label": it["size_label"],
            "set_contents": it["set_contents"],
            "localized_names": localized or None,
        })
        # 販売可否(売り切れ)はマスタではなく活動から投影するため、ここでは移行しない
        rec("product", key, status_of(True, archived=bool(it["is_archived"])), it["name"],
            data, source("menu_items", it["id"]))

    out.append("-- 商品と調整分類の関係")
    for lk in links:
        if lk["group_id"] not in group_key or lk["menu_item_id"] not in item_key:
            continue
        rel("product", item_key[lk["menu_item_id"]], "modifier_group", group_key[lk["group_id"]],
            "permits_modifier", {"required": bool(lk["required"]), "display_order": lk["display_order"]})

    out.append("COMMIT;")
    return "\n".join(out) + "\n", counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="data/restaurant.db", help="移行元のSQLite(読み取り専用で開く)")
    ap.add_argument("--out", default="tmp/migration.sql", help="出力するSQLファイル")
    ap.add_argument("--tenant-code", default=None, help="tenant_code。省略時は店舗IDを小文字にしたもの")
    ap.add_argument("--tenant-name", default=None, help="法人名。省略時は店舗名")
    ap.add_argument("--default-tax-category", default="standard", choices=["standard", "reduced", "exempt"],
                    help="移行元に税区分がないため全商品へ入れる値")
    args = ap.parse_args(argv)

    db_path = Path(args.db).resolve()
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        store_id = conn.execute("SELECT id FROM stores ORDER BY id LIMIT 1").fetchone()
        tenant_code = args.tenant_code or (store_id[0].lower() if store_id else "tenant")
        sql, counts = build_sql(
            conn, tenant_code=tenant_code, tenant_name=args.tenant_name,
            default_tax_category=args.default_tax_category,
        )
    finally:
        conn.close()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(sql, encoding="utf-8", newline="\n")
    print(f"wrote {out_path} tenant={tenant_code} " + " ".join(f"{k}={v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
