-- 007_core_record_verify.sql
-- core_record の自動検証。001, 002, 005, 006 の適用後に実行する（003/004 とは独立）。
-- 失敗時は例外で終了する。
\set ON_ERROR_STOP on
SET client_min_messages = warning;
SET search_path = platform, public;

CREATE TEMP TABLE core_results (
    test_name text PRIMARY KEY,
    passed boolean NOT NULL,
    detail text NOT NULL
);
CREATE TEMP TABLE ids (name text PRIMARY KEY, id uuid NOT NULL);

CREATE FUNCTION pg_temp.id(p_name text) RETURNS uuid LANGUAGE sql STABLE AS $$
    SELECT id FROM ids WHERE name = p_name
$$;

-- 確定記録を一件追加する。常に実表へINSERTし、トリガーの検査を通す。
CREATE FUNCTION pg_temp.post(
    p_tenant uuid, p_loc uuid, p_type text, p_confirmer uuid, p_method text, p_summary text,
    p_data jsonb DEFAULT '{}', p_product uuid DEFAULT NULL, p_place uuid DEFAULT NULL,
    p_session uuid DEFAULT NULL, p_item uuid DEFAULT NULL, p_supplier uuid DEFAULT NULL,
    p_tmp uuid DEFAULT NULL, p_reversal uuid DEFAULT NULL,
    p_qty numeric DEFAULT NULL, p_price numeric DEFAULT NULL
) RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE v_def uuid; v_id uuid;
BEGIN
    SELECT entity_definition_id INTO v_def
      FROM effective_entity_definition('operation', 'transaction', p_type, p_tenant);
    INSERT INTO core_record (
        tenant_id, location_id, entity_definition_id, record_type, business_date,
        recorded_by, confirmed_by, confirmation_method, summary, data,
        product_id, place_id, session_id, item_id, supplier_id, source_tmp_id,
        reversal_of_record_id, quantity, unit_price, amount
    ) VALUES (
        p_tenant, p_loc, v_def, p_type, current_date,
        p_confirmer, p_confirmer, p_method, p_summary, p_data,
        p_product, p_place, p_session, p_item, p_supplier, p_tmp,
        p_reversal, p_qty, p_price, p_qty * p_price
    ) RETURNING record_id INTO v_id;
    RETURN v_id;
END;
$$;

-- SQLを実行し、期待どおり拒否されたこと（メッセージの一致を含む）を記録する。
CREATE FUNCTION pg_temp.expect_reject(p_name text, p_sql text, p_pattern text)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    BEGIN
        EXECUTE p_sql;
        INSERT INTO core_results VALUES (p_name, false, 'statement unexpectedly succeeded');
    EXCEPTION WHEN OTHERS THEN
        INSERT INTO core_results VALUES (p_name, SQLERRM LIKE p_pattern, left(SQLERRM, 200));
    END;
END;
$$;

-- ---------------------------------------------------------------
-- テストデータ：A社（店舗2、席、商品、品目、仕入先、来店セッション）とB社
-- ---------------------------------------------------------------
DO $$
DECLARE
    ta uuid; tb uuid;
    staff uuid; agent uuid; guest uuid; staff_b uuid;
    d_loc uuid; d_prod uuid; d_item uuid; d_party uuid; d_sess uuid;
    hq uuid; s1 uuid; s2 uuid; t1 uuid; prod uuid; itm uuid; sup uuid; sess uuid;
    sb uuid; prod_b uuid;
BEGIN
    INSERT INTO tenants (tenant_code, tenant_name, industry_code)
    VALUES ('core-test-a', 'コアテストA', 'restaurant') RETURNING tenant_id INTO ta;
    INSERT INTO tenants (tenant_code, tenant_name, industry_code)
    VALUES ('core-test-b', 'コアテストB', 'restaurant') RETURNING tenant_id INTO tb;

    INSERT INTO actors (tenant_id, actor_type, actor_code, display_name)
    VALUES (ta, 'user', 'staff1', '店員A') RETURNING actor_id INTO staff;
    INSERT INTO actors (tenant_id, actor_type, actor_code, display_name)
    VALUES (ta, 'agent', 'order-ai', '注文解析AI') RETURNING actor_id INTO agent;
    INSERT INTO actors (tenant_id, actor_type, actor_code, display_name)
    VALUES (ta, 'guest_session', 'table-1-session', '1番テーブル端末') RETURNING actor_id INTO guest;
    INSERT INTO actors (tenant_id, actor_type, actor_code, display_name)
    VALUES (tb, 'user', 'staff1', '店員B') RETURNING actor_id INTO staff_b;

    SELECT entity_definition_id INTO d_loc FROM effective_entity_definition('party', 'record', 'location', ta);
    SELECT entity_definition_id INTO d_prod FROM effective_entity_definition('catalog', 'record', 'product', ta);
    SELECT entity_definition_id INTO d_item FROM effective_entity_definition('catalog', 'record', 'item', ta);
    SELECT entity_definition_id INTO d_party FROM effective_entity_definition('party', 'record', 'party', ta);
    SELECT entity_definition_id INTO d_sess FROM effective_entity_definition('operation', 'record', 'visit_session', ta);

    INSERT INTO business_records (tenant_id, entity_definition_id, business_key, record_status, display_name, data, created_by)
    VALUES (ta, d_loc, 'HQ', 'active', '本部', '{"location_type":"headquarters"}', staff) RETURNING record_id INTO hq;
    INSERT INTO business_records (tenant_id, entity_definition_id, business_key, record_status, display_name, data, created_by)
    VALUES (ta, d_loc, 'S1', 'active', '一号店', '{"location_type":"store"}', staff) RETURNING record_id INTO s1;
    INSERT INTO business_records (tenant_id, entity_definition_id, business_key, record_status, display_name, data, created_by)
    VALUES (ta, d_loc, 'S2', 'active', '二号店', '{"location_type":"store"}', staff) RETURNING record_id INTO s2;
    INSERT INTO business_records (tenant_id, entity_definition_id, business_key, record_status, display_name, data, created_by)
    VALUES (ta, d_loc, 'S1-T1', 'active', '1番テーブル', '{"location_type":"table","seats":4}', staff) RETURNING record_id INTO t1;
    INSERT INTO business_records (tenant_id, entity_definition_id, business_key, record_status, display_name, data, created_by)
    VALUES (ta, d_prod, 'P-001', 'active', '生ビール', '{"price":600,"tax_category":"standard"}', staff) RETURNING record_id INTO prod;
    INSERT INTO business_records (tenant_id, entity_definition_id, business_key, record_status, display_name, data, created_by)
    VALUES (ta, d_item, 'I-001', 'active', 'ビール樽', '{"name":"ビール樽","item_type":"material"}', staff) RETURNING record_id INTO itm;
    INSERT INTO business_records (tenant_id, entity_definition_id, business_key, record_status, display_name, data, created_by)
    VALUES (ta, d_party, 'SUP-001', 'active', '酒類卸', '{"name":"酒類卸","roles":["supplier"]}', staff) RETURNING record_id INTO sup;
    INSERT INTO business_records (tenant_id, entity_definition_id, business_key, record_status, display_name, data, created_by)
    VALUES (ta, d_sess, 'SESS-1', 'active', '来店1', '{"party_size":2}', staff) RETURNING record_id INTO sess;

    INSERT INTO record_relations (tenant_id, from_record_id, to_record_id, relation_type, created_by)
    VALUES (ta, t1, s1, 'located_in', staff), (ta, s1, hq, 'located_in', staff), (ta, s2, hq, 'located_in', staff);

    SELECT entity_definition_id INTO d_loc FROM effective_entity_definition('party', 'record', 'location', tb);
    SELECT entity_definition_id INTO d_prod FROM effective_entity_definition('catalog', 'record', 'product', tb);
    INSERT INTO business_records (tenant_id, entity_definition_id, business_key, record_status, display_name, data, created_by)
    VALUES (tb, d_loc, 'S1', 'active', 'B社店舗', '{"location_type":"store"}', staff_b) RETURNING record_id INTO sb;
    INSERT INTO business_records (tenant_id, entity_definition_id, business_key, record_status, display_name, data, created_by)
    VALUES (tb, d_prod, 'P-001', 'active', 'B社商品', '{"price":500,"tax_category":"reduced"}', staff_b) RETURNING record_id INTO prod_b;

    INSERT INTO ids VALUES
        ('ta', ta), ('tb', tb), ('staff', staff), ('agent', agent), ('guest', guest), ('staff_b', staff_b),
        ('hq', hq), ('s1', s1), ('s2', s2), ('t1', t1), ('prod', prod), ('item', itm),
        ('supplier', sup), ('sess', sess), ('sb', sb), ('prod_b', prod_b);
END $$;

-- ---------------------------------------------------------------
-- 1. 正常系：確定、採番、チェーン
-- ---------------------------------------------------------------
INSERT INTO core_results
SELECT '01_objects_present',
       count(*) = 4,
       'tables=' || string_agg(table_name, ',' ORDER BY table_name)
FROM information_schema.tables
WHERE table_schema = 'platform'
  AND table_name IN ('core_record', 'core_record_tmp', 'core_chain_heads', 'audit_log');

-- 店員が確定（1件目）、来店客が卓上で確定（2件目）、候補経由で確定（3件目）
DO $$
DECLARE
    v_tmp uuid;
    v_line1 uuid;
BEGIN
    v_line1 := pg_temp.post(pg_temp.id('ta'), pg_temp.id('s1'), 'order_line', pg_temp.id('staff'),
        'staff_handheld', 'line-1', '{"original_text":"生ビールを二つ","input_language":"ja"}',
        p_product => pg_temp.id('prod'), p_place => pg_temp.id('t1'), p_session => pg_temp.id('sess'),
        p_qty => 2, p_price => 600);
    INSERT INTO ids VALUES ('line1', v_line1);

    INSERT INTO ids VALUES ('line2', pg_temp.post(pg_temp.id('ta'), pg_temp.id('s1'), 'order_line',
        pg_temp.id('guest'), 'guest_table', 'line-2', '{"notes":"氷なし"}',
        p_product => pg_temp.id('prod'), p_place => pg_temp.id('t1'), p_session => pg_temp.id('sess'),
        p_qty => 1, p_price => 600));

    INSERT INTO core_record_tmp (tenant_id, location_id, source_type, input_text, input_language,
                                 candidate_payload, field_confidences, model_id, prompt_version, created_by)
    VALUES (pg_temp.id('ta'), pg_temp.id('s1'), 'voice', '生ビール一つ', 'ja',
            '{"product":"生ビール","quantity":1}', '{"product":0.93}', 'test-model', 'p1', pg_temp.id('agent'))
    RETURNING tmp_id INTO v_tmp;
    INSERT INTO ids VALUES ('tmp1', v_tmp);

    INSERT INTO ids VALUES ('line3', pg_temp.post(pg_temp.id('ta'), pg_temp.id('s1'), 'order_line',
        pg_temp.id('staff'), 'staff_handheld', 'line-3', '{}',
        p_product => pg_temp.id('prod'), p_tmp => v_tmp, p_qty => 1, p_price => 600));
END $$;

INSERT INTO core_results
SELECT '02_sequence_and_hash_link',
       array_agg(sequence_no ORDER BY sequence_no) = ARRAY[1, 2, 3]::bigint[]
       AND (SELECT prev_hash FROM core_record WHERE summary = 'line-1') = repeat('0', 64)
       AND (SELECT prev_hash FROM core_record WHERE summary = 'line-2') = (SELECT hash FROM core_record WHERE summary = 'line-1')
       AND (SELECT prev_hash FROM core_record WHERE summary = 'line-3') = (SELECT hash FROM core_record WHERE summary = 'line-2'),
       'sequences=' || array_agg(sequence_no ORDER BY sequence_no)::text
FROM core_record WHERE tenant_id = pg_temp.id('ta') AND location_id = pg_temp.id('s1');

INSERT INTO core_results
SELECT '03_verify_chain_ok', reason = 'ok' AND checked_count = 3,
       format('checked=%s reason=%s', checked_count, reason)
FROM verify_core_chain(pg_temp.id('ta'), pg_temp.id('s1'));

INSERT INTO core_results
SELECT '04_tmp_promoted_by_human',
       t.status = 'approved' AND t.reviewer_id = pg_temp.id('staff') AND t.reviewed_at IS NOT NULL,
       format('status=%s', t.status)
FROM core_record_tmp t WHERE t.tmp_id = pg_temp.id('tmp1');

INSERT INTO core_results
SELECT '05_guest_may_confirm_order_line', confirmation_method = 'guest_table',
       'confirmed_by_type=' || (SELECT actor_type FROM actors WHERE actor_id = confirmed_by)
FROM core_record WHERE summary = 'line-2';

-- 別店舗は別チェーン
DO $$
BEGIN
    PERFORM pg_temp.post(pg_temp.id('ta'), pg_temp.id('s2'), 'order_line', pg_temp.id('staff'),
        'staff_handheld', 's2-line-1', '{}', p_qty => 1, p_price => 100);
    PERFORM pg_temp.post(pg_temp.id('ta'), pg_temp.id('s2'), 'order_line', pg_temp.id('staff'),
        'staff_handheld', 's2-line-2', '{}', p_qty => 1, p_price => 100);
END $$;

INSERT INTO core_results
SELECT '06_chain_is_per_location',
       min(sequence_no) = 1 AND max(sequence_no) = 2,
       'store2 sequences=' || min(sequence_no) || '..' || max(sequence_no)
FROM core_record WHERE tenant_id = pg_temp.id('ta') AND location_id = pg_temp.id('s2');

-- ---------------------------------------------------------------
-- 2. 拒否されるべき操作
-- ---------------------------------------------------------------
SELECT pg_temp.expect_reject('07_update_rejected',
    format('UPDATE core_record SET summary = %L WHERE summary = %L', 'x', 'line-1'),
    '%append-only%');
SELECT pg_temp.expect_reject('08_delete_rejected',
    format('DELETE FROM core_record WHERE summary = %L', 'line-1'),
    '%append-only%');
SELECT pg_temp.expect_reject('09_truncate_rejected', 'TRUNCATE core_record', '%append-only%');

SELECT pg_temp.expect_reject('10_agent_cannot_confirm',
    format('SELECT pg_temp.post(%L, %L, %L, %L, %L, %L)', pg_temp.id('ta'), pg_temp.id('s1'),
           'order_line', pg_temp.id('agent'), 'staff_handheld', 'agent-confirm'),
    '%human actor%');

SELECT pg_temp.expect_reject('11_guest_cannot_confirm_payment',
    format('SELECT pg_temp.post(%L, %L, %L, %L, %L, %L, %L)', pg_temp.id('ta'), pg_temp.id('s1'),
           'payment_received', pg_temp.id('guest'), 'guest_table', 'guest-payment',
           '{"payment_method":"cash"}'),
    '%must be confirmed by staff%');

SELECT pg_temp.expect_reject('12_guest_method_requires_guest_actor',
    format('SELECT pg_temp.post(%L, %L, %L, %L, %L, %L)', pg_temp.id('ta'), pg_temp.id('s1'),
           'order_line', pg_temp.id('staff'), 'guest_table', 'staff-as-guest'),
    '%requires a guest_session actor%');

SELECT pg_temp.expect_reject('13_cross_tenant_product_rejected',
    format('SELECT pg_temp.post(%L, %L, %L, %L, %L, %L, %L, %L)', pg_temp.id('ta'), pg_temp.id('s1'),
           'order_line', pg_temp.id('staff'), 'staff_handheld', 'cross-tenant', '{}', pg_temp.id('prod_b')),
    '%was not found in tenant%');

SELECT pg_temp.expect_reject('14_cross_tenant_location_rejected',
    format('SELECT pg_temp.post(%L, %L, %L, %L, %L, %L)', pg_temp.id('ta'), pg_temp.id('sb'),
           'order_line', pg_temp.id('staff'), 'staff_handheld', 'cross-tenant-loc'),
    '%was not found in tenant%');

SELECT pg_temp.expect_reject('15_wrong_entity_for_product_rejected',
    format('SELECT pg_temp.post(%L, %L, %L, %L, %L, %L, %L, %L)', pg_temp.id('ta'), pg_temp.id('s1'),
           'order_line', pg_temp.id('staff'), 'staff_handheld', 'wrong-entity', '{}', pg_temp.id('t1')),
    '%must be a "product" record%');

SELECT pg_temp.expect_reject('16_table_is_not_a_chain_location',
    format('SELECT pg_temp.post(%L, %L, %L, %L, %L, %L)', pg_temp.id('ta'), pg_temp.id('t1'),
           'order_line', pg_temp.id('staff'), 'staff_handheld', 'table-as-store'),
    '%location_type%');

SELECT pg_temp.expect_reject('17_undefined_data_key_rejected',
    format('SELECT pg_temp.post(%L, %L, %L, %L, %L, %L, %L)', pg_temp.id('ta'), pg_temp.id('s1'),
           'order_line', pg_temp.id('staff'), 'staff_handheld', 'unknown-key', '{"unknown_key":"x"}'),
    '%undefined JSONB field%');

SELECT pg_temp.expect_reject('18_required_data_missing_rejected',
    format('SELECT pg_temp.post(%L, %L, %L, %L, %L, %L, %L)', pg_temp.id('ta'), pg_temp.id('s1'),
           'order_cancel', pg_temp.id('staff'), 'staff_handheld', 'cancel-no-reason', '{}'),
    '%required JSONB field%');

SELECT pg_temp.expect_reject('19_approved_tmp_other_location_rejected',
    format('SELECT pg_temp.post(%L, %L, %L, %L, %L, %L, %L, %L, %L, %L, %L, %L, %L)', pg_temp.id('ta'),
           pg_temp.id('s2'), 'order_line', pg_temp.id('staff'), 'staff_handheld', 'tmp-wrong-store', '{}',
           NULL, NULL, NULL, NULL, NULL, (SELECT tmp_id FROM core_record_tmp LIMIT 1)),
    '%belongs to another location%');

-- 取消は反対記録で表し、同じ記録を二重に取り消せない
DO $$
BEGIN
    INSERT INTO ids VALUES ('cancel1', pg_temp.post(pg_temp.id('ta'), pg_temp.id('s1'), 'order_cancel',
        pg_temp.id('staff'), 'staff_handheld', 'cancel-line-1', '{"reason":"注文間違い"}',
        p_product => pg_temp.id('prod'), p_reversal => pg_temp.id('line1'), p_qty => -2, p_price => 600));
END $$;

INSERT INTO core_results
SELECT '20_reversal_recorded',
       c.reversal_of_record_id = pg_temp.id('line1') AND c.quantity = -2 AND o.summary = 'line-1',
       format('reversal seq=%s original seq=%s', c.sequence_no, o.sequence_no)
FROM core_record c JOIN core_record o ON o.tenant_id = c.tenant_id AND o.record_id = c.reversal_of_record_id
WHERE c.record_id = pg_temp.id('cancel1');

SELECT pg_temp.expect_reject('21_double_reversal_rejected',
    format('SELECT pg_temp.post(%L, %L, %L, %L, %L, %L, %L, p_reversal => %L)', pg_temp.id('ta'), pg_temp.id('s1'),
           'order_cancel', pg_temp.id('staff'), 'staff_handheld', 'cancel-again',
           '{"reason":"二重"}', pg_temp.id('line1')),
    '%uq_core_record_reversal%');

-- 拒否された試行が採番を消費していない（欠番なし）
INSERT INTO core_results
SELECT '22_no_sequence_gap_after_rejections',
       reason = 'ok' AND checked_count = 4,
       format('checked=%s reason=%s', checked_count, reason)
FROM verify_core_chain(pg_temp.id('ta'), pg_temp.id('s1'));

-- ---------------------------------------------------------------
-- 3. 改ざん検出（所有者がトリガーを外して直接変更した場合）
-- ---------------------------------------------------------------
DO $$
DECLARE r record;
BEGIN
    ALTER TABLE core_record DISABLE TRIGGER trg_core_record_immutable;
    UPDATE core_record SET summary = 'tampered' WHERE summary = 'line-2';
    ALTER TABLE core_record ENABLE TRIGGER trg_core_record_immutable;

    SELECT * INTO r FROM verify_core_chain(pg_temp.id('ta'), pg_temp.id('s1'));
    INSERT INTO core_results VALUES ('23_tamper_detected',
        r.first_bad_sequence = 2 AND r.reason LIKE 'hash mismatch%',
        format('first_bad=%s reason=%s', r.first_bad_sequence, r.reason));

    ALTER TABLE core_record DISABLE TRIGGER trg_core_record_immutable;
    UPDATE core_record SET summary = 'line-2' WHERE summary = 'tampered';
    ALTER TABLE core_record ENABLE TRIGGER trg_core_record_immutable;

    SELECT * INTO r FROM verify_core_chain(pg_temp.id('ta'), pg_temp.id('s1'));
    INSERT INTO core_results VALUES ('24_restored_chain_verifies', r.reason = 'ok',
        format('reason=%s', r.reason));

    -- 末尾の削除（二号店のチェーンで確認）
    ALTER TABLE core_record DISABLE TRIGGER trg_core_record_immutable;
    DELETE FROM core_record WHERE summary = 's2-line-2';
    ALTER TABLE core_record ENABLE TRIGGER trg_core_record_immutable;

    SELECT * INTO r FROM verify_core_chain(pg_temp.id('ta'), pg_temp.id('s2'));
    INSERT INTO core_results VALUES ('25_tail_deletion_detected',
        r.reason LIKE 'chain head mismatch%', format('reason=%s', r.reason));
END $$;

-- ---------------------------------------------------------------
-- 4. 追記専用の監査ログ
-- ---------------------------------------------------------------
INSERT INTO audit_log (tenant_id, actor_id, action, target_type, target_id, detail)
VALUES (pg_temp.id('ta'), pg_temp.id('staff'), 'confirm_order', 'core_record', pg_temp.id('line1'), '{}');
SELECT pg_temp.expect_reject('26_audit_log_update_rejected',
    'UPDATE audit_log SET action = ''x''', '%append-only%');

-- ---------------------------------------------------------------
-- 5. RLS：アプリ用ロールからは自社の記録だけが見え、挿入もできる
-- ---------------------------------------------------------------
DO $$
BEGIN
    PERFORM pg_temp.post(pg_temp.id('tb'), pg_temp.id('sb'), 'order_line', pg_temp.id('staff_b'),
        'staff_handheld', 'b-line-1', '{}', p_qty => 1, p_price => 500);
END $$;

SELECT pg_temp.id('ta') AS ta_id, pg_temp.id('s1') AS s1_id, pg_temp.id('staff') AS staff_id,
       (SELECT entity_definition_id FROM effective_entity_definition('operation', 'transaction', 'order_line', pg_temp.id('ta'))) AS def_id
\gset

GRANT SELECT, INSERT ON core_results TO platform_app;
SET ROLE platform_app;
SELECT set_config('app.tenant_id', :'ta_id', false);

INSERT INTO core_results
SELECT '27_rls_hides_other_tenant_records',
       count(*) > 0 AND count(DISTINCT tenant_id) = 1 AND bool_and(tenant_id = :'ta_id'::uuid),
       'visible_records=' || count(*)
FROM core_record;

INSERT INTO core_record (tenant_id, location_id, entity_definition_id, record_type, business_date,
                         recorded_by, confirmed_by, confirmation_method, summary, data)
VALUES (:'ta_id', :'s1_id', :'def_id', 'order_line', current_date,
        :'staff_id', :'staff_id', 'staff_handheld', 'app-role-insert', '{}');

INSERT INTO core_results
SELECT '28_app_role_insert_extends_chain', reason = 'ok' AND checked_count = 5,
       format('checked=%s reason=%s', checked_count, reason)
FROM verify_core_chain(:'ta_id', :'s1_id');

RESET ROLE;
SELECT set_config('app.tenant_id', '', false);

-- ---------------------------------------------------------------
-- 6. ハッシュはセッションの時刻・日付設定に依存しない
-- ---------------------------------------------------------------
SET timezone = 'America/New_York';
SET datestyle = 'SQL, DMY';
INSERT INTO core_results
SELECT '29_hash_independent_of_session_settings', reason = 'ok' AND checked_count = 5,
       format('checked=%s reason=%s', checked_count, reason)
FROM verify_core_chain(pg_temp.id('ta'), pg_temp.id('s1'));
RESET timezone;
RESET datestyle;

TABLE core_results ORDER BY test_name;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM core_results WHERE NOT passed) THEN
        RAISE EXCEPTION 'core_record verification failed: %',
            (SELECT string_agg(test_name, ', ' ORDER BY test_name) FROM core_results WHERE NOT passed);
    END IF;
END $$;
