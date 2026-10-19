-- 005_core_record.sql
-- core_record 統合設計（docs/core-record-integrated-design.md）の基盤部分。
-- 001_schema.sql の後に適用する（PostgreSQL 18.4 で 007 の29項目を確認済み）。
BEGIN;
SET search_path = platform, public;

-- ---------------------------------------------------------------
-- 1. 既存テーブルの拡張
-- ---------------------------------------------------------------

-- 来店客が卓上端末で確定する場合の主体（社員マスタ登録なしで人の操作を追跡する）
ALTER TABLE actors DROP CONSTRAINT IF EXISTS actors_actor_type_check;
ALTER TABLE actors ADD CONSTRAINT ck_actors_actor_type
    CHECK (actor_type IN ('user', 'agent', 'system', 'service', 'guest_session'));
ALTER TABLE actors ADD CONSTRAINT ck_actors_guest_tenant
    CHECK (actor_type <> 'guest_session' OR tenant_id IS NOT NULL);

-- 全マスタに共通の表示名。検索・並び替えに使うため固定列にする。
ALTER TABLE business_records ADD COLUMN display_name varchar(200);
CREATE INDEX ix_records_display_name ON business_records (tenant_id, entity_definition_id, display_name);

COMMENT ON TABLE business_transactions IS
    'DEPRECATED: core_record に置き換える。既存データ移行が済むまで残す。';
COMMENT ON TABLE transaction_lines IS
    'DEPRECATED: core_record に置き換える。既存データ移行が済むまで残す。';

-- ---------------------------------------------------------------
-- 2. 共通関数
-- ---------------------------------------------------------------

CREATE OR REPLACE FUNCTION prevent_append_only_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only (% prohibited); post a reversal or correcting record',
        TG_TABLE_NAME, TG_OP;
END;
$$;

-- マスタ参照の種別・状態・場所区分を検証する。
CREATE OR REPLACE FUNCTION assert_record_entity(
    p_tenant_id uuid,
    p_record_id uuid,
    p_entity_code text,
    p_label text,
    p_location_types text[] DEFAULT NULL
) RETURNS void LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_code varchar;
    v_status record_status;
    v_data jsonb;
BEGIN
    IF p_record_id IS NULL THEN RETURN; END IF;
    SELECT e.entity_code, r.record_status, r.data
      INTO v_code, v_status, v_data
      FROM business_records r
      JOIN entity_definitions e ON e.entity_definition_id = r.entity_definition_id
     WHERE r.tenant_id = p_tenant_id AND r.record_id = p_record_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION '% % was not found in tenant %', p_label, p_record_id, p_tenant_id;
    END IF;
    IF v_code <> p_entity_code THEN
        RAISE EXCEPTION '% must be a "%" record but is "%"', p_label, p_entity_code, v_code;
    END IF;
    IF v_status NOT IN ('active', 'inactive', 'archived') THEN
        RAISE EXCEPTION '% % is not usable (status %)', p_label, p_record_id, v_status;
    END IF;
    IF p_location_types IS NOT NULL
       AND NOT ((v_data ->> 'location_type') = ANY (p_location_types)) THEN
        RAISE EXCEPTION '% % has location_type "%" (allowed: %)',
            p_label, p_record_id, v_data ->> 'location_type', p_location_types;
    END IF;
END;
$$;

-- ---------------------------------------------------------------
-- 3. テーブル
-- ---------------------------------------------------------------

-- ハッシュチェーンの先頭。チェーンの単位は (tenant_id, location_id)。
-- location_id は店舗（または本部）の場所レコード。行ロックで確定を直列化する。
CREATE TABLE core_chain_heads (
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    location_id uuid NOT NULL,
    last_sequence_no bigint NOT NULL DEFAULT 0 CHECK (last_sequence_no >= 0),
    last_hash char(64) NOT NULL DEFAULT repeat('0', 64),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, location_id),
    CONSTRAINT fk_core_chain_heads_location FOREIGN KEY (tenant_id, location_id)
        REFERENCES business_records(tenant_id, record_id)
);

-- AI・音声・OCR・外部連携・手入力による未確定候補。正本ではない。
CREATE TABLE core_record_tmp (
    tmp_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    location_id uuid NOT NULL,
    source_type varchar(20) NOT NULL CHECK (source_type IN ('voice', 'text', 'file', 'api', 'manual')),
    source_ref jsonb NOT NULL DEFAULT '{}'::jsonb,
    input_text text,
    input_language varchar(10),
    candidate_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    field_confidences jsonb NOT NULL DEFAULT '{}'::jsonb,
    model_id varchar(100),
    prompt_version varchar(50),
    status varchar(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected', 'failed')),
    created_by uuid REFERENCES actors(actor_id),
    reviewer_id uuid REFERENCES actors(actor_id),
    reviewed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_core_record_tmp_tenant UNIQUE (tenant_id, tmp_id),
    CONSTRAINT fk_core_record_tmp_location FOREIGN KEY (tenant_id, location_id)
        REFERENCES business_records(tenant_id, record_id),
    CONSTRAINT ck_core_record_tmp_review CHECK (
        status NOT IN ('approved', 'rejected') OR (reviewer_id IS NOT NULL AND reviewed_at IS NOT NULL)
    ),
    CONSTRAINT ck_core_record_tmp_objects CHECK (
        jsonb_typeof(source_ref) = 'object'
        AND jsonb_typeof(candidate_payload) = 'object'
        AND jsonb_typeof(field_confidences) = 'object'
    )
);

-- 人が確認した業務事実の確定済みジャーナル。追記専用。
-- 取消・訂正は reversal_of_record_id / source_record_id を持つ新しい記録で表す。
CREATE TABLE core_record (
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    record_id uuid NOT NULL DEFAULT gen_random_uuid(),
    -- 識別・順序（sequence_no / prev_hash / hash はトリガーが設定する）
    location_id uuid NOT NULL,                -- 店舗または本部。ハッシュチェーンの単位
    sequence_no bigint NOT NULL,
    activity_id uuid NOT NULL DEFAULT gen_random_uuid(),
    document_type varchar(80),
    document_id uuid,
    line_no integer CHECK (line_no IS NULL OR line_no > 0),
    entity_definition_id uuid NOT NULL REFERENCES entity_definitions(entity_definition_id),
    record_type varchar(80) NOT NULL,         -- 取引定義の entity_code と一致
    -- 日時・操作者
    business_date date NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    recorded_by uuid NOT NULL REFERENCES actors(actor_id),
    confirmed_at timestamptz NOT NULL DEFAULT now(),
    confirmed_by uuid NOT NULL REFERENCES actors(actor_id),
    confirmation_method varchar(30) NOT NULL
        CHECK (confirmation_method IN ('staff_handheld', 'guest_table', 'kitchen', 'admin', 'import')),
    -- 分析軸
    place_id uuid,
    product_id uuid,
    item_id uuid,
    supplier_id uuid,
    session_id uuid,
    cost_center varchar(50),
    internal_order varchar(50),
    activity_type varchar(50),
    -- 数量・金額
    quantity numeric(20,6),
    unit_code varchar(30),
    unit_price numeric(20,6),
    amount numeric(20,4),
    tax_amount numeric(20,4),
    currency_code char(3),
    -- 関係・証跡
    parent_record_id uuid,
    source_record_id uuid,
    reversal_of_record_id uuid,
    source_tmp_id uuid,
    summary text,
    data jsonb NOT NULL DEFAULT '{}'::jsonb,
    schema_version integer NOT NULL DEFAULT 1 CHECK (schema_version > 0),
    -- ハッシュ
    canonical_version smallint NOT NULL DEFAULT 1,
    prev_hash char(64) NOT NULL,
    hash char(64) NOT NULL,
    hash_algorithm varchar(20) NOT NULL DEFAULT 'sha256' CHECK (hash_algorithm = 'sha256'),
    PRIMARY KEY (tenant_id, record_id),
    CONSTRAINT uq_core_record_sequence UNIQUE (tenant_id, location_id, sequence_no),
    CONSTRAINT fk_core_record_location FOREIGN KEY (tenant_id, location_id) REFERENCES business_records(tenant_id, record_id),
    CONSTRAINT fk_core_record_place FOREIGN KEY (tenant_id, place_id) REFERENCES business_records(tenant_id, record_id),
    CONSTRAINT fk_core_record_product FOREIGN KEY (tenant_id, product_id) REFERENCES business_records(tenant_id, record_id),
    CONSTRAINT fk_core_record_item FOREIGN KEY (tenant_id, item_id) REFERENCES business_records(tenant_id, record_id),
    CONSTRAINT fk_core_record_supplier FOREIGN KEY (tenant_id, supplier_id) REFERENCES business_records(tenant_id, record_id),
    CONSTRAINT fk_core_record_session FOREIGN KEY (tenant_id, session_id) REFERENCES business_records(tenant_id, record_id),
    CONSTRAINT fk_core_record_parent FOREIGN KEY (tenant_id, parent_record_id) REFERENCES core_record(tenant_id, record_id),
    CONSTRAINT fk_core_record_source FOREIGN KEY (tenant_id, source_record_id) REFERENCES core_record(tenant_id, record_id),
    CONSTRAINT fk_core_record_reversal FOREIGN KEY (tenant_id, reversal_of_record_id) REFERENCES core_record(tenant_id, record_id),
    CONSTRAINT fk_core_record_tmp FOREIGN KEY (tenant_id, source_tmp_id) REFERENCES core_record_tmp(tenant_id, tmp_id),
    CONSTRAINT ck_core_record_currency CHECK (currency_code IS NULL OR currency_code ~ '^[A-Z]{3}$'),
    CONSTRAINT ck_core_record_data_object CHECK (jsonb_typeof(data) = 'object')
);

CREATE UNIQUE INDEX uq_core_record_reversal ON core_record (tenant_id, reversal_of_record_id)
    WHERE reversal_of_record_id IS NOT NULL;
CREATE INDEX ix_core_record_location_date ON core_record (tenant_id, location_id, business_date, record_type);
CREATE INDEX ix_core_record_document ON core_record (tenant_id, document_id, line_no);
CREATE INDEX ix_core_record_activity ON core_record (tenant_id, activity_id);
CREATE INDEX ix_core_record_session ON core_record (tenant_id, session_id, occurred_at);
CREATE INDEX ix_core_record_product ON core_record (tenant_id, product_id, occurred_at) WHERE product_id IS NOT NULL;
CREATE INDEX ix_core_record_item ON core_record (tenant_id, item_id, occurred_at) WHERE item_id IS NOT NULL;
CREATE INDEX ix_core_record_data_gin ON core_record USING gin (data jsonb_path_ops);
CREATE INDEX ix_core_record_tmp_status ON core_record_tmp (tenant_id, location_id, status, created_at);

-- 閲覧・ログイン・設定変更・確定操作などの操作監査。追記専用。
CREATE TABLE audit_log (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    occurred_at timestamptz NOT NULL DEFAULT now(),
    actor_id uuid REFERENCES actors(actor_id),
    action varchar(80) NOT NULL,
    target_type varchar(80),
    target_id uuid,
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    client_info jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT ck_audit_log_objects CHECK (jsonb_typeof(detail) = 'object' AND jsonb_typeof(client_info) = 'object')
);
CREATE INDEX ix_audit_log_tenant_time ON audit_log (tenant_id, occurred_at DESC);
CREATE INDEX ix_audit_log_target ON audit_log (tenant_id, target_type, target_id);

-- ---------------------------------------------------------------
-- 4. ハッシュ
-- ---------------------------------------------------------------

-- ハッシュ入力の正規化文字列。canonical_version ごとに規則を固定する。
-- 日時はUTC固定、数値は列定義の桁で出力するため、セッション設定に依存しない。
CREATE OR REPLACE FUNCTION core_record_canonical(r core_record) RETURNS text LANGUAGE sql STABLE AS $$
    SELECT concat_ws('|',
        'v' || r.canonical_version,
        r.tenant_id, r.location_id, r.sequence_no, r.record_id,
        r.record_type,
        COALESCE(r.document_type, ''), COALESCE(r.document_id::text, ''), COALESCE(r.line_no::text, ''),
        r.activity_id,
        to_char(r.business_date, 'YYYY-MM-DD'),
        to_char(r.occurred_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US'),
        to_char(r.confirmed_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US'),
        r.recorded_by, r.confirmed_by, r.confirmation_method,
        COALESCE(r.place_id::text, ''), COALESCE(r.product_id::text, ''), COALESCE(r.item_id::text, ''),
        COALESCE(r.supplier_id::text, ''), COALESCE(r.session_id::text, ''),
        COALESCE(r.cost_center, ''), COALESCE(r.internal_order, ''), COALESCE(r.activity_type, ''),
        COALESCE(r.quantity::text, ''), COALESCE(r.unit_code, ''), COALESCE(r.unit_price::text, ''),
        COALESCE(r.amount::text, ''), COALESCE(r.tax_amount::text, ''), COALESCE(r.currency_code, ''),
        COALESCE(r.parent_record_id::text, ''), COALESCE(r.source_record_id::text, ''),
        COALESCE(r.reversal_of_record_id::text, ''), COALESCE(r.source_tmp_id::text, ''),
        COALESCE(r.summary, ''), r.data::text,
        r.prev_hash
    );
$$;

CREATE OR REPLACE FUNCTION core_record_hash(r core_record) RETURNS char(64) LANGUAGE sql STABLE AS $$
    SELECT encode(sha256(convert_to(core_record_canonical(r), 'UTF8')), 'hex');
$$;

-- 検証：欠番、prev_hashの不一致、内容改ざん、末尾の削除を検出する。
CREATE OR REPLACE FUNCTION verify_core_chain(p_tenant_id uuid, p_location_id uuid)
RETURNS TABLE (checked_count bigint, first_bad_sequence bigint, reason text)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    r core_record;
    v_prev char(64) := repeat('0', 64);
    v_expected bigint := 1;
    v_count bigint := 0;
    v_head core_chain_heads%ROWTYPE;
BEGIN
    FOR r IN
        SELECT * FROM core_record
         WHERE tenant_id = p_tenant_id AND location_id = p_location_id
         ORDER BY sequence_no
    LOOP
        v_count := v_count + 1;
        IF r.sequence_no <> v_expected THEN
            RETURN QUERY SELECT v_count, r.sequence_no, 'sequence gap'::text; RETURN;
        END IF;
        IF r.prev_hash <> v_prev THEN
            RETURN QUERY SELECT v_count, r.sequence_no, 'prev_hash mismatch'::text; RETURN;
        END IF;
        IF r.hash <> core_record_hash(r) THEN
            RETURN QUERY SELECT v_count, r.sequence_no, 'hash mismatch (content changed)'::text; RETURN;
        END IF;
        v_prev := r.hash;
        v_expected := v_expected + 1;
    END LOOP;

    SELECT * INTO v_head FROM core_chain_heads
     WHERE tenant_id = p_tenant_id AND location_id = p_location_id;
    IF FOUND AND (v_head.last_sequence_no <> v_expected - 1 OR v_head.last_hash <> v_prev) THEN
        RETURN QUERY SELECT v_count, v_expected, 'chain head mismatch (records removed)'::text; RETURN;
    END IF;
    RETURN QUERY SELECT v_count, NULL::bigint, 'ok'::text;
END;
$$;

-- ---------------------------------------------------------------
-- 5. トリガー
-- ---------------------------------------------------------------

-- 5.1 core_record_tmp：状態遷移と審査者の検査
CREATE OR REPLACE FUNCTION guard_core_record_tmp() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_reviewer_type varchar;
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM assert_actor_tenant(NEW.created_by, NEW.tenant_id);
        PERFORM assert_record_entity(NEW.tenant_id, NEW.location_id, 'location', 'location_id',
                                     ARRAY['store', 'headquarters']);
        IF NEW.status <> 'pending' THEN
            RAISE EXCEPTION 'core_record_tmp must be created as pending';
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.tmp_id <> OLD.tmp_id OR NEW.tenant_id <> OLD.tenant_id OR NEW.location_id <> OLD.location_id
       OR NEW.candidate_payload IS DISTINCT FROM OLD.candidate_payload
       OR NEW.input_text IS DISTINCT FROM OLD.input_text
       OR NEW.field_confidences IS DISTINCT FROM OLD.field_confidences THEN
        RAISE EXCEPTION 'core_record_tmp candidate content is immutable';
    END IF;
    IF OLD.status <> 'pending' AND NEW.status <> OLD.status THEN
        RAISE EXCEPTION 'core_record_tmp status % is final', OLD.status;
    END IF;
    IF NEW.status IN ('approved', 'rejected') AND OLD.status = 'pending' THEN
        SELECT actor_type INTO v_reviewer_type FROM actors WHERE actor_id = NEW.reviewer_id;
        IF v_reviewer_type IS NULL OR v_reviewer_type NOT IN ('user', 'guest_session') THEN
            RAISE EXCEPTION 'core_record_tmp must be reviewed by a human actor';
        END IF;
        PERFORM assert_actor_tenant(NEW.reviewer_id, NEW.tenant_id);
    END IF;
    RETURN NEW;
END;
$$;

-- 5.2 core_record：検証（BEFORE INSERT・先頭）
CREATE OR REPLACE FUNCTION validate_core_record() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_def entity_definitions%ROWTYPE;
    v_confirmer actors%ROWTYPE;
BEGIN
    IF NOT definition_applies(NEW.entity_definition_id, NEW.tenant_id, 'transaction') THEN
        RAISE EXCEPTION 'record definition % is not available to tenant %',
            NEW.entity_definition_id, NEW.tenant_id;
    END IF;
    SELECT * INTO v_def FROM entity_definitions WHERE entity_definition_id = NEW.entity_definition_id;
    IF v_def.entity_code <> NEW.record_type THEN
        RAISE EXCEPTION 'record_type "%" does not match its definition "%"', NEW.record_type, v_def.entity_code;
    END IF;

    PERFORM assert_record_entity(NEW.tenant_id, NEW.location_id, 'location', 'location_id',
                                 ARRAY['store', 'headquarters']);
    PERFORM assert_record_entity(NEW.tenant_id, NEW.place_id, 'location', 'place_id');
    PERFORM assert_record_entity(NEW.tenant_id, NEW.product_id, 'product', 'product_id');
    PERFORM assert_record_entity(NEW.tenant_id, NEW.item_id, 'item', 'item_id');
    PERFORM assert_record_entity(NEW.tenant_id, NEW.supplier_id, 'party', 'supplier_id');
    PERFORM assert_record_entity(NEW.tenant_id, NEW.session_id, 'visit_session', 'session_id');

    PERFORM assert_actor_tenant(NEW.recorded_by, NEW.tenant_id);
    SELECT * INTO v_confirmer FROM actors WHERE actor_id = NEW.confirmed_by;
    IF NOT FOUND OR v_confirmer.tenant_id IS DISTINCT FROM NEW.tenant_id THEN
        RAISE EXCEPTION 'confirmed_by must be an actor of tenant %', NEW.tenant_id;
    END IF;
    IF v_confirmer.actor_type NOT IN ('user', 'guest_session') THEN
        RAISE EXCEPTION 'confirmed_by must be a human actor (got %)', v_confirmer.actor_type;
    END IF;
    IF NEW.confirmation_method = 'guest_table' AND v_confirmer.actor_type <> 'guest_session' THEN
        RAISE EXCEPTION 'guest_table confirmation requires a guest_session actor';
    END IF;
    IF NEW.confirmation_method <> 'guest_table' AND v_confirmer.actor_type <> 'user' THEN
        RAISE EXCEPTION 'confirmation_method % requires a user actor', NEW.confirmation_method;
    END IF;
    IF COALESCE((v_def.lifecycle ->> 'requires_staff_confirmation')::boolean, false)
       AND v_confirmer.actor_type <> 'user' THEN
        RAISE EXCEPTION 'record_type "%" must be confirmed by staff', NEW.record_type;
    END IF;

    PERFORM validate_jsonb_payload(NEW.tenant_id, NEW.entity_definition_id, NEW.data);
    RETURN NEW;
END;
$$;

-- 5.3 core_record：順序採番とハッシュ（BEFORE INSERT・2番目）
CREATE OR REPLACE FUNCTION chain_core_record() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = platform, public, pg_temp AS $$
DECLARE
    v_seq bigint;
    v_prev char(64);
BEGIN
    INSERT INTO core_chain_heads (tenant_id, location_id)
    VALUES (NEW.tenant_id, NEW.location_id)
    ON CONFLICT (tenant_id, location_id) DO NOTHING;

    SELECT last_sequence_no, last_hash INTO v_seq, v_prev
      FROM core_chain_heads
     WHERE tenant_id = NEW.tenant_id AND location_id = NEW.location_id
       FOR UPDATE;

    NEW.sequence_no := v_seq + 1;
    NEW.prev_hash := v_prev;
    NEW.hash := core_record_hash(NEW);

    UPDATE core_chain_heads
       SET last_sequence_no = NEW.sequence_no, last_hash = NEW.hash, updated_at = now()
     WHERE tenant_id = NEW.tenant_id AND location_id = NEW.location_id;
    RETURN NEW;
END;
$$;

-- 5.4 core_record：未確定候補の承認済み化（BEFORE INSERT・3番目）
-- 一つの候補から複数明細が確定され得るため、approved は許容する。
CREATE OR REPLACE FUNCTION promote_core_record_tmp() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = platform, public, pg_temp AS $$
DECLARE
    v_status varchar;
    v_location uuid;
BEGIN
    IF NEW.source_tmp_id IS NULL THEN RETURN NEW; END IF;
    SELECT status, location_id INTO v_status, v_location
      FROM core_record_tmp
     WHERE tenant_id = NEW.tenant_id AND tmp_id = NEW.source_tmp_id
       FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'source tmp % was not found', NEW.source_tmp_id;
    END IF;
    IF v_location <> NEW.location_id THEN
        RAISE EXCEPTION 'source tmp % belongs to another location', NEW.source_tmp_id;
    END IF;
    IF v_status = 'pending' THEN
        UPDATE core_record_tmp
           SET status = 'approved', reviewer_id = NEW.confirmed_by, reviewed_at = NEW.confirmed_at
         WHERE tenant_id = NEW.tenant_id AND tmp_id = NEW.source_tmp_id;
    ELSIF v_status <> 'approved' THEN
        RAISE EXCEPTION 'source tmp % is %, only pending/approved can be confirmed', NEW.source_tmp_id, v_status;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_core_record_tmp_guard BEFORE INSERT OR UPDATE ON core_record_tmp
    FOR EACH ROW EXECUTE FUNCTION guard_core_record_tmp();
CREATE TRIGGER trg_core_record_tmp_updated BEFORE UPDATE ON core_record_tmp
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_core_record_tmp_no_delete BEFORE DELETE ON core_record_tmp
    FOR EACH ROW EXECUTE FUNCTION prevent_physical_delete();

CREATE TRIGGER trg_10_core_record_validate BEFORE INSERT ON core_record
    FOR EACH ROW EXECUTE FUNCTION validate_core_record();
CREATE TRIGGER trg_20_core_record_chain BEFORE INSERT ON core_record
    FOR EACH ROW EXECUTE FUNCTION chain_core_record();
CREATE TRIGGER trg_30_core_record_promote BEFORE INSERT ON core_record
    FOR EACH ROW EXECUTE FUNCTION promote_core_record_tmp();
CREATE TRIGGER trg_core_record_immutable BEFORE UPDATE OR DELETE ON core_record
    FOR EACH ROW EXECUTE FUNCTION prevent_append_only_change();
CREATE TRIGGER trg_core_record_no_truncate BEFORE TRUNCATE ON core_record
    FOR EACH STATEMENT EXECUTE FUNCTION prevent_append_only_change();

CREATE TRIGGER trg_audit_log_immutable BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION prevent_append_only_change();
CREATE TRIGGER trg_audit_log_no_truncate BEFORE TRUNCATE ON audit_log
    FOR EACH STATEMENT EXECUTE FUNCTION prevent_append_only_change();

REVOKE ALL ON FUNCTION chain_core_record() FROM PUBLIC;
REVOKE ALL ON FUNCTION promote_core_record_tmp() FROM PUBLIC;

-- ---------------------------------------------------------------
-- 6. RLS・権限
-- ---------------------------------------------------------------

ALTER TABLE core_chain_heads ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_record_tmp ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_record ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY core_chain_heads_isolation ON core_chain_heads
    USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id());
CREATE POLICY core_record_tmp_isolation ON core_record_tmp
    USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id());
CREATE POLICY core_record_isolation ON core_record
    USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id());
CREATE POLICY audit_log_isolation ON audit_log
    USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id());

GRANT SELECT ON core_chain_heads TO platform_app;
GRANT SELECT, INSERT, UPDATE ON core_record_tmp TO platform_app;
GRANT SELECT, INSERT ON core_record TO platform_app;
GRANT SELECT, INSERT ON audit_log TO platform_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA platform TO platform_app;
GRANT EXECUTE ON FUNCTION verify_core_chain(uuid, uuid) TO platform_app;

COMMIT;
