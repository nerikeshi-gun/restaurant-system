BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA platform;
SET search_path = platform, public;

CREATE TYPE definition_scope AS ENUM ('platform', 'industry', 'tenant');
CREATE TYPE definition_kind AS ENUM ('record', 'transaction');
CREATE TYPE value_kind AS ENUM ('string', 'text', 'integer', 'decimal', 'boolean', 'date', 'timestamp', 'uuid', 'json');
CREATE TYPE record_status AS ENUM ('draft', 'active', 'inactive', 'archived', 'cancelled');
CREATE TYPE transaction_status AS ENUM ('draft', 'posted', 'completed', 'cancelled', 'corrected');

CREATE OR REPLACE FUNCTION jsonb_value_matches_kind(p_value jsonb, p_kind value_kind)
RETURNS boolean LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE v_text text;
BEGIN
    IF p_value IS NULL OR jsonb_typeof(p_value) = 'null' THEN RETURN true; END IF;
    v_text := p_value #>> '{}';
    CASE p_kind
        WHEN 'string', 'text' THEN RETURN jsonb_typeof(p_value) = 'string';
        WHEN 'integer' THEN RETURN jsonb_typeof(p_value) = 'number' AND v_text ~ '^-?[0-9]+$';
        WHEN 'decimal' THEN RETURN jsonb_typeof(p_value) = 'number';
        WHEN 'boolean' THEN RETURN jsonb_typeof(p_value) = 'boolean';
        WHEN 'json' THEN RETURN true;
        WHEN 'date' THEN
            IF jsonb_typeof(p_value) <> 'string' THEN RETURN false; END IF;
            PERFORM v_text::date; RETURN true;
        WHEN 'timestamp' THEN
            IF jsonb_typeof(p_value) <> 'string' THEN RETURN false; END IF;
            PERFORM v_text::timestamptz; RETURN true;
        WHEN 'uuid' THEN
            IF jsonb_typeof(p_value) <> 'string' THEN RETURN false; END IF;
            PERFORM v_text::uuid; RETURN true;
        ELSE RETURN false;
    END CASE;
EXCEPTION WHEN OTHERS THEN RETURN false;
END;
$$;

CREATE TABLE industries (
    industry_code varchar(50) PRIMARY KEY,
    industry_name varchar(200) NOT NULL,
    description text,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE tenants (
    tenant_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_code varchar(50) NOT NULL UNIQUE,
    tenant_name varchar(200) NOT NULL,
    industry_code varchar(50) REFERENCES industries(industry_code),
    default_locale varchar(10) NOT NULL DEFAULT 'ja-JP',
    default_timezone varchar(50) NOT NULL DEFAULT 'Asia/Tokyo',
    settings jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_tenants_settings_object CHECK (jsonb_typeof(settings) = 'object')
);

CREATE TABLE actors (
    actor_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid REFERENCES tenants(tenant_id),
    actor_type varchar(30) NOT NULL CHECK (actor_type IN ('user', 'agent', 'system', 'service')),
    actor_code varchar(100) NOT NULL,
    display_name varchar(200) NOT NULL,
    external_subject varchar(255),
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_actors_tenant_code UNIQUE NULLS NOT DISTINCT (tenant_id, actor_code),
    CONSTRAINT uq_actors_tenant_actor UNIQUE (tenant_id, actor_id),
    CONSTRAINT ck_actors_attributes_object CHECK (jsonb_typeof(attributes) = 'object')
);

CREATE TABLE modules (
    module_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    module_code varchar(80) NOT NULL UNIQUE,
    module_name varchar(200) NOT NULL,
    description text,
    version varchar(30) NOT NULL DEFAULT '1.0.0',
    settings jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_modules_settings_object CHECK (jsonb_typeof(settings) = 'object')
);

CREATE TABLE entity_definitions (
    entity_definition_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    module_id uuid NOT NULL REFERENCES modules(module_id),
    definition_kind definition_kind NOT NULL DEFAULT 'record',
    scope definition_scope NOT NULL DEFAULT 'platform',
    tenant_id uuid REFERENCES tenants(tenant_id),
    industry_code varchar(50) REFERENCES industries(industry_code),
    entity_code varchar(80) NOT NULL,
    entity_name varchar(200) NOT NULL,
    description text,
    current_schema_version integer NOT NULL DEFAULT 1 CHECK (current_schema_version > 0),
    lifecycle jsonb NOT NULL DEFAULT '{}'::jsonb,
    validation_schema jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_entity_definitions_scope UNIQUE NULLS NOT DISTINCT
        (module_id, definition_kind, scope, tenant_id, industry_code, entity_code),
    CONSTRAINT ck_entity_definitions_scope CHECK (
        (scope = 'platform' AND tenant_id IS NULL AND industry_code IS NULL)
        OR (scope = 'industry' AND tenant_id IS NULL AND industry_code IS NOT NULL)
        OR (scope = 'tenant' AND tenant_id IS NOT NULL AND industry_code IS NULL)
    ),
    CONSTRAINT ck_entity_definitions_lifecycle_object CHECK (jsonb_typeof(lifecycle) = 'object'),
    CONSTRAINT ck_entity_definitions_validation_object CHECK (jsonb_typeof(validation_schema) = 'object')
);

CREATE TABLE field_definitions (
    field_definition_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_definition_id uuid NOT NULL REFERENCES entity_definitions(entity_definition_id) ON DELETE CASCADE,
    field_code varchar(80) NOT NULL,
    field_name varchar(200) NOT NULL,
    description text,
    data_type value_kind NOT NULL,
    max_length integer CHECK (max_length IS NULL OR max_length > 0),
    numeric_precision integer CHECK (numeric_precision IS NULL OR numeric_precision > 0),
    numeric_scale integer CHECK (numeric_scale IS NULL OR numeric_scale >= 0),
    storage_path varchar(255) NOT NULL,
    is_required boolean NOT NULL DEFAULT false,
    is_multivalued boolean NOT NULL DEFAULT false,
    default_value jsonb,
    validation_rules jsonb NOT NULL DEFAULT '{}'::jsonb,
    display_rules jsonb NOT NULL DEFAULT '{}'::jsonb,
    semantic_tags text[] NOT NULL DEFAULT '{}',
    ai_description text,
    sensitivity varchar(30) NOT NULL DEFAULT 'internal'
        CHECK (sensitivity IN ('public', 'internal', 'confidential', 'personal', 'restricted')),
    promotion_state varchar(30) NOT NULL DEFAULT 'extension'
        CHECK (promotion_state IN ('fixed', 'extension', 'candidate')),
    is_history_tracked boolean NOT NULL DEFAULT true,
    example_value jsonb,
    sort_order integer NOT NULL DEFAULT 0,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_field_definitions_code UNIQUE (entity_definition_id, field_code),
    CONSTRAINT ck_field_definitions_code CHECK (field_code ~ '^[a-z][a-z0-9_]*$'),
    CONSTRAINT ck_field_definitions_storage CHECK (
        (promotion_state = 'fixed' AND storage_path ~ '^core\.[a-z][a-z0-9_]*$')
        OR (promotion_state IN ('extension', 'candidate') AND storage_path = 'data.' || field_code)
    ),
    CONSTRAINT ck_field_definitions_numeric_shape CHECK (
        numeric_scale IS NULL OR numeric_precision IS NULL OR numeric_scale <= numeric_precision
    ),
    CONSTRAINT ck_field_definitions_validation_object CHECK (jsonb_typeof(validation_rules) = 'object'),
    CONSTRAINT ck_field_definitions_display_object CHECK (jsonb_typeof(display_rules) = 'object'),
    CONSTRAINT ck_field_definitions_default_type CHECK (default_value IS NULL OR jsonb_value_matches_kind(default_value, data_type)),
    CONSTRAINT ck_field_definitions_example_type CHECK (example_value IS NULL OR jsonb_value_matches_kind(example_value, data_type))
);

CREATE TABLE business_records (
    record_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    entity_definition_id uuid NOT NULL REFERENCES entity_definitions(entity_definition_id),
    record_no bigint GENERATED ALWAYS AS IDENTITY,
    business_key varchar(200),
    record_status record_status NOT NULL DEFAULT 'draft',
    schema_version integer NOT NULL DEFAULT 1 CHECK (schema_version > 0),
    effective_from timestamptz,
    effective_to timestamptz,
    data jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_ref jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_by uuid REFERENCES actors(actor_id),
    updated_by uuid REFERENCES actors(actor_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version_no integer NOT NULL DEFAULT 1 CHECK (version_no > 0),
    CONSTRAINT uq_business_records_key UNIQUE (tenant_id, entity_definition_id, business_key),
    CONSTRAINT uq_business_records_tenant_record UNIQUE (tenant_id, record_id),
    CONSTRAINT ck_business_records_effective_period CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from),
    CONSTRAINT ck_business_records_data_object CHECK (jsonb_typeof(data) = 'object'),
    CONSTRAINT ck_business_records_source_object CHECK (jsonb_typeof(source_ref) = 'object')
);

CREATE TABLE record_relations (
    relation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    from_record_id uuid NOT NULL,
    to_record_id uuid NOT NULL,
    relation_type varchar(80) NOT NULL,
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    valid_from timestamptz,
    valid_to timestamptz,
    created_by uuid REFERENCES actors(actor_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_record_relations_from FOREIGN KEY (tenant_id, from_record_id) REFERENCES business_records(tenant_id, record_id),
    CONSTRAINT fk_record_relations_to FOREIGN KEY (tenant_id, to_record_id) REFERENCES business_records(tenant_id, record_id),
    CONSTRAINT uq_record_relations UNIQUE (tenant_id, from_record_id, to_record_id, relation_type),
    CONSTRAINT ck_record_relations_distinct CHECK (from_record_id <> to_record_id),
    CONSTRAINT ck_record_relations_period CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from),
    CONSTRAINT ck_record_relations_attributes_object CHECK (jsonb_typeof(attributes) = 'object')
);

CREATE TABLE business_transactions (
    transaction_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    module_id uuid NOT NULL REFERENCES modules(module_id),
    transaction_definition_id uuid NOT NULL REFERENCES entity_definitions(entity_definition_id),
    transaction_no bigint GENERATED ALWAYS AS IDENTITY,
    transaction_type varchar(80) NOT NULL,
    business_date date NOT NULL DEFAULT current_date,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    transaction_status transaction_status NOT NULL DEFAULT 'draft',
    subject_record_id uuid,
    parent_transaction_id uuid,
    supersedes_transaction_id uuid,
    external_key varchar(200),
    currency_code char(3),
    amount numeric(20,4),
    cancellation_reason text,
    data jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_ref jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_by uuid REFERENCES actors(actor_id),
    updated_by uuid REFERENCES actors(actor_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version_no integer NOT NULL DEFAULT 1 CHECK (version_no > 0),
    CONSTRAINT uq_business_transactions_external UNIQUE (tenant_id, module_id, external_key),
    CONSTRAINT uq_business_transactions_tenant_tx UNIQUE (tenant_id, transaction_id),
    CONSTRAINT fk_business_transactions_subject FOREIGN KEY (tenant_id, subject_record_id) REFERENCES business_records(tenant_id, record_id),
    CONSTRAINT fk_business_transactions_parent FOREIGN KEY (tenant_id, parent_transaction_id) REFERENCES business_transactions(tenant_id, transaction_id),
    CONSTRAINT fk_business_transactions_supersedes FOREIGN KEY (tenant_id, supersedes_transaction_id) REFERENCES business_transactions(tenant_id, transaction_id),
    CONSTRAINT ck_business_transactions_currency CHECK (currency_code IS NULL OR currency_code ~ '^[A-Z]{3}$'),
    CONSTRAINT ck_business_transactions_cancellation CHECK (transaction_status <> 'cancelled' OR cancellation_reason IS NOT NULL),
    CONSTRAINT ck_business_transactions_data_object CHECK (jsonb_typeof(data) = 'object'),
    CONSTRAINT ck_business_transactions_source_object CHECK (jsonb_typeof(source_ref) = 'object')
);

CREATE TABLE transaction_lines (
    transaction_line_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    transaction_id uuid NOT NULL,
    line_no integer NOT NULL CHECK (line_no > 0),
    line_type varchar(80) NOT NULL,
    related_record_id uuid,
    quantity numeric(20,6),
    unit_code varchar(30),
    unit_price numeric(20,6),
    line_amount numeric(20,4),
    data jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_transaction_lines_transaction FOREIGN KEY (tenant_id, transaction_id) REFERENCES business_transactions(tenant_id, transaction_id),
    CONSTRAINT fk_transaction_lines_record FOREIGN KEY (tenant_id, related_record_id) REFERENCES business_records(tenant_id, record_id),
    CONSTRAINT uq_transaction_lines_no UNIQUE (tenant_id, transaction_id, line_no),
    CONSTRAINT ck_transaction_lines_data_object CHECK (jsonb_typeof(data) = 'object')
);

CREATE TABLE wrapper_definitions (
    wrapper_definition_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    module_id uuid NOT NULL REFERENCES modules(module_id),
    scope definition_scope NOT NULL,
    tenant_id uuid REFERENCES tenants(tenant_id),
    industry_code varchar(50) REFERENCES industries(industry_code),
    wrapper_code varchar(80) NOT NULL,
    wrapper_name varchar(200) NOT NULL,
    wrapper_type varchar(30) NOT NULL CHECK (wrapper_type IN ('screen', 'workflow', 'api', 'report', 'agent')),
    definition jsonb NOT NULL,
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_wrapper_definitions_scope UNIQUE NULLS NOT DISTINCT (module_id, scope, tenant_id, industry_code, wrapper_code, wrapper_type, version),
    CONSTRAINT ck_wrapper_definitions_scope CHECK (
        (scope = 'platform' AND tenant_id IS NULL AND industry_code IS NULL)
        OR (scope = 'industry' AND tenant_id IS NULL AND industry_code IS NOT NULL)
        OR (scope = 'tenant' AND tenant_id IS NOT NULL AND industry_code IS NULL)
    ),
    CONSTRAINT ck_wrapper_definitions_object CHECK (jsonb_typeof(definition) = 'object')
);

CREATE TABLE change_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
    aggregate_type varchar(80) NOT NULL,
    aggregate_id uuid NOT NULL,
    event_type varchar(80) NOT NULL,
    row_version integer,
    before_data jsonb,
    after_data jsonb,
    changed_fields text[] NOT NULL DEFAULT '{}',
    reason text,
    correlation_id uuid,
    actor_id uuid REFERENCES actors(actor_id),
    occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_entity_definitions_resolution ON entity_definitions (module_id, definition_kind, entity_code, scope, industry_code, tenant_id) WHERE is_active;
CREATE INDEX ix_field_definitions_resolution ON field_definitions (entity_definition_id, field_code) WHERE is_active;
CREATE INDEX ix_records_tenant_entity_status ON business_records (tenant_id, entity_definition_id, record_status);
CREATE INDEX ix_records_business_key ON business_records (tenant_id, business_key);
CREATE INDEX ix_records_data_gin ON business_records USING gin (data jsonb_path_ops);
CREATE INDEX ix_relations_from ON record_relations (tenant_id, from_record_id, relation_type);
CREATE INDEX ix_relations_to ON record_relations (tenant_id, to_record_id, relation_type);
CREATE INDEX ix_transactions_lookup ON business_transactions (tenant_id, module_id, transaction_type, business_date DESC);
CREATE INDEX ix_transactions_subject ON business_transactions (tenant_id, subject_record_id, occurred_at DESC);
CREATE INDEX ix_transactions_data_gin ON business_transactions USING gin (data jsonb_path_ops);
CREATE INDEX ix_lines_related_record ON transaction_lines (tenant_id, related_record_id);
CREATE INDEX ix_change_events_tenant_aggregate ON change_events (tenant_id, aggregate_type, aggregate_id, occurred_at DESC);
CREATE INDEX ix_change_events_correlation ON change_events (correlation_id) WHERE correlation_id IS NOT NULL;

CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION maintain_business_version() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id THEN
        RAISE EXCEPTION 'tenant_id is immutable for %.%', TG_TABLE_SCHEMA, TG_TABLE_NAME;
    END IF;
    NEW.updated_at := now();
    NEW.version_no := OLD.version_no + 1;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION definition_applies(
    p_entity_definition_id uuid,
    p_tenant_id uuid,
    p_expected_kind definition_kind
) RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT EXISTS (
        SELECT 1
        FROM entity_definitions e
        JOIN tenants t ON t.tenant_id = p_tenant_id AND t.is_active
        WHERE e.entity_definition_id = p_entity_definition_id
          AND e.definition_kind = p_expected_kind
          AND e.is_active
          AND (
              e.scope = 'platform'
              OR (e.scope = 'industry' AND e.industry_code = t.industry_code)
              OR (e.scope = 'tenant' AND e.tenant_id = p_tenant_id)
          )
    );
$$;

CREATE OR REPLACE FUNCTION effective_entity_definition(
    p_module_code varchar,
    p_definition_kind definition_kind,
    p_entity_code varchar,
    p_tenant_id uuid
) RETURNS SETOF entity_definitions LANGUAGE sql STABLE AS $$
    SELECT e.*
    FROM entity_definitions e
    JOIN modules m ON m.module_id = e.module_id AND m.module_code = p_module_code
    JOIN tenants t ON t.tenant_id = p_tenant_id AND t.is_active
    WHERE e.definition_kind = p_definition_kind
      AND e.entity_code = p_entity_code
      AND e.is_active
      AND (
          e.scope = 'platform'
          OR (e.scope = 'industry' AND e.industry_code = t.industry_code)
          OR (e.scope = 'tenant' AND e.tenant_id = p_tenant_id)
      )
    ORDER BY CASE e.scope WHEN 'tenant' THEN 3 WHEN 'industry' THEN 2 ELSE 1 END DESC,
             e.updated_at DESC
    LIMIT 1;
$$;

CREATE OR REPLACE FUNCTION effective_field_definitions(
    p_module_code varchar,
    p_definition_kind definition_kind,
    p_entity_code varchar,
    p_tenant_id uuid
) RETURNS TABLE (
    field_definition_id uuid, entity_definition_id uuid, field_code varchar,
    field_name varchar, description text, data_type value_kind, max_length integer,
    numeric_precision integer, numeric_scale integer, storage_path varchar,
    is_required boolean, is_multivalued boolean, default_value jsonb,
    validation_rules jsonb, display_rules jsonb, semantic_tags text[],
    ai_description text, sensitivity varchar, promotion_state varchar,
    is_history_tracked boolean, example_value jsonb, sort_order integer,
    source_scope definition_scope, source_industry_code varchar, source_tenant_id uuid
) LANGUAGE sql STABLE AS $$
    SELECT DISTINCT ON (f.field_code)
           f.field_definition_id, f.entity_definition_id, f.field_code, f.field_name,
           f.description, f.data_type, f.max_length, f.numeric_precision, f.numeric_scale,
           f.storage_path, f.is_required, f.is_multivalued, f.default_value,
           f.validation_rules, f.display_rules, f.semantic_tags, f.ai_description,
           f.sensitivity, f.promotion_state, f.is_history_tracked, f.example_value,
           f.sort_order, e.scope, e.industry_code, e.tenant_id
    FROM field_definitions f
    JOIN entity_definitions e ON e.entity_definition_id = f.entity_definition_id AND e.is_active
    JOIN modules m ON m.module_id = e.module_id AND m.module_code = p_module_code
    JOIN tenants t ON t.tenant_id = p_tenant_id AND t.is_active
    WHERE e.definition_kind = p_definition_kind
      AND e.entity_code = p_entity_code
      AND f.is_active
      AND (
          e.scope = 'platform'
          OR (e.scope = 'industry' AND e.industry_code = t.industry_code)
          OR (e.scope = 'tenant' AND e.tenant_id = p_tenant_id)
      )
    ORDER BY f.field_code,
             CASE e.scope WHEN 'tenant' THEN 3 WHEN 'industry' THEN 2 ELSE 1 END DESC,
             f.updated_at DESC;
$$;

CREATE OR REPLACE FUNCTION effective_field_definitions(
    p_entity_definition_id uuid,
    p_tenant_id uuid
) RETURNS TABLE (
    field_definition_id uuid, entity_definition_id uuid, field_code varchar,
    field_name varchar, description text, data_type value_kind, max_length integer,
    numeric_precision integer, numeric_scale integer, storage_path varchar,
    is_required boolean, is_multivalued boolean, default_value jsonb,
    validation_rules jsonb, display_rules jsonb, semantic_tags text[],
    ai_description text, sensitivity varchar, promotion_state varchar,
    is_history_tracked boolean, example_value jsonb, sort_order integer,
    source_scope definition_scope, source_industry_code varchar, source_tenant_id uuid
) LANGUAGE sql STABLE AS $$
    SELECT ef.*
    FROM entity_definitions base
    JOIN modules m ON m.module_id = base.module_id
    CROSS JOIN LATERAL effective_field_definitions(m.module_code, base.definition_kind, base.entity_code, p_tenant_id) ef
    WHERE base.entity_definition_id = p_entity_definition_id;
$$;

CREATE OR REPLACE FUNCTION effective_wrapper_definitions(
    p_module_code varchar,
    p_wrapper_type varchar,
    p_tenant_id uuid
) RETURNS SETOF wrapper_definitions LANGUAGE sql STABLE AS $$
    SELECT DISTINCT ON (w.wrapper_code) w.*
    FROM wrapper_definitions w
    JOIN modules m ON m.module_id = w.module_id AND m.module_code = p_module_code
    JOIN tenants t ON t.tenant_id = p_tenant_id AND t.is_active
    WHERE w.wrapper_type = p_wrapper_type
      AND w.is_active
      AND (
          w.scope = 'platform'
          OR (w.scope = 'industry' AND w.industry_code = t.industry_code)
          OR (w.scope = 'tenant' AND w.tenant_id = p_tenant_id)
      )
    ORDER BY w.wrapper_code,
             CASE w.scope WHEN 'tenant' THEN 3 WHEN 'industry' THEN 2 ELSE 1 END DESC,
             w.version DESC;
$$;

CREATE OR REPLACE FUNCTION validate_jsonb_payload(
    p_tenant_id uuid,
    p_entity_definition_id uuid,
    p_data jsonb
) RETURNS void LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_kind definition_kind;
    v_entity_code varchar;
    v_module_code varchar;
    v_field record;
    v_key text;
    v_value jsonb;
    v_text text;
BEGIN
    SELECT e.definition_kind, e.entity_code, m.module_code
      INTO v_kind, v_entity_code, v_module_code
      FROM entity_definitions e
      JOIN modules m ON m.module_id = e.module_id
     WHERE e.entity_definition_id = p_entity_definition_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'definition % was not found', p_entity_definition_id; END IF;

    FOR v_key IN SELECT jsonb_object_keys(p_data)
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM effective_field_definitions(v_module_code, v_kind, v_entity_code, p_tenant_id) f
            WHERE f.storage_path = 'data.' || v_key
        ) THEN
            RAISE EXCEPTION 'undefined JSONB field "%" for %.% tenant %', v_key, v_module_code, v_entity_code, p_tenant_id;
        END IF;
    END LOOP;

    FOR v_field IN
        SELECT * FROM effective_field_definitions(v_module_code, v_kind, v_entity_code, p_tenant_id)
        WHERE storage_path LIKE 'data.%'
    LOOP
        v_key := substring(v_field.storage_path FROM 6);
        IF v_field.is_required AND (NOT p_data ? v_key OR jsonb_typeof(p_data -> v_key) = 'null') THEN
            RAISE EXCEPTION 'required JSONB field "%" is missing', v_key;
        END IF;
        IF p_data ? v_key AND jsonb_typeof(p_data -> v_key) <> 'null' THEN
            v_value := p_data -> v_key;
            v_text := v_value #>> '{}';
            IF NOT jsonb_value_matches_kind(v_value, v_field.data_type) THEN
                RAISE EXCEPTION 'JSONB field "%" does not match type %', v_key, v_field.data_type;
            END IF;
            IF v_field.max_length IS NOT NULL AND v_field.data_type IN ('string', 'text')
               AND char_length(v_text) > v_field.max_length THEN
                RAISE EXCEPTION 'JSONB field "%" exceeds max length %', v_key, v_field.max_length;
            END IF;
            IF v_field.validation_rules ? 'enum'
               AND NOT ((v_field.validation_rules -> 'enum') @> jsonb_build_array(v_value)) THEN
                RAISE EXCEPTION 'JSONB field "%" is not in the allowed enum', v_key;
            END IF;
            IF v_field.validation_rules ? 'pattern' AND v_text !~ (v_field.validation_rules ->> 'pattern') THEN
                RAISE EXCEPTION 'JSONB field "%" does not match its pattern', v_key;
            END IF;
            IF v_field.data_type IN ('integer', 'decimal') AND v_field.validation_rules ? 'minimum'
               AND v_text::numeric < (v_field.validation_rules ->> 'minimum')::numeric THEN
                RAISE EXCEPTION 'JSONB field "%" is below its minimum', v_key;
            END IF;
            IF v_field.data_type IN ('integer', 'decimal') AND v_field.validation_rules ? 'maximum'
               AND v_text::numeric > (v_field.validation_rules ->> 'maximum')::numeric THEN
                RAISE EXCEPTION 'JSONB field "%" is above its maximum', v_key;
            END IF;
        END IF;
    END LOOP;
END;
$$;

CREATE OR REPLACE FUNCTION assert_actor_tenant(p_actor_id uuid, p_tenant_id uuid)
RETURNS void LANGUAGE plpgsql STABLE AS $$
DECLARE v_actor_tenant uuid;
BEGIN
    IF p_actor_id IS NULL THEN RETURN; END IF;
    SELECT tenant_id INTO v_actor_tenant FROM actors WHERE actor_id = p_actor_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'actor % was not found', p_actor_id; END IF;
    IF v_actor_tenant IS NOT NULL AND v_actor_tenant <> p_tenant_id THEN
        RAISE EXCEPTION 'actor % belongs to another tenant', p_actor_id;
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION validate_business_record() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.record_id <> OLD.record_id THEN RAISE EXCEPTION 'record_id is immutable'; END IF;
    IF NOT definition_applies(NEW.entity_definition_id, NEW.tenant_id, 'record') THEN
        RAISE EXCEPTION 'record definition % is not available to tenant %', NEW.entity_definition_id, NEW.tenant_id;
    END IF;
    PERFORM assert_actor_tenant(NEW.created_by, NEW.tenant_id);
    PERFORM assert_actor_tenant(NEW.updated_by, NEW.tenant_id);
    PERFORM validate_jsonb_payload(NEW.tenant_id, NEW.entity_definition_id, NEW.data);
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION validate_business_transaction() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_definition entity_definitions%ROWTYPE;
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.transaction_id <> OLD.transaction_id THEN RAISE EXCEPTION 'transaction_id is immutable'; END IF;
    IF NOT definition_applies(NEW.transaction_definition_id, NEW.tenant_id, 'transaction') THEN
        RAISE EXCEPTION 'transaction definition % is not available to tenant %', NEW.transaction_definition_id, NEW.tenant_id;
    END IF;
    SELECT * INTO v_definition FROM entity_definitions WHERE entity_definition_id = NEW.transaction_definition_id;
    IF v_definition.module_id <> NEW.module_id OR v_definition.entity_code <> NEW.transaction_type THEN
        RAISE EXCEPTION 'transaction module/type does not match its definition';
    END IF;
    PERFORM assert_actor_tenant(NEW.created_by, NEW.tenant_id);
    PERFORM assert_actor_tenant(NEW.updated_by, NEW.tenant_id);
    PERFORM validate_jsonb_payload(NEW.tenant_id, NEW.transaction_definition_id, NEW.data);
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION validate_relation_actor() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND (NEW.relation_id <> OLD.relation_id OR NEW.tenant_id <> OLD.tenant_id
       OR NEW.from_record_id <> OLD.from_record_id OR NEW.to_record_id <> OLD.to_record_id) THEN
        RAISE EXCEPTION 'relation identity and tenant are immutable';
    END IF;
    PERFORM assert_actor_tenant(NEW.created_by, NEW.tenant_id);
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION validate_transaction_line() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND (NEW.transaction_line_id <> OLD.transaction_line_id
       OR NEW.tenant_id <> OLD.tenant_id OR NEW.transaction_id <> OLD.transaction_id) THEN
        RAISE EXCEPTION 'transaction line identity and tenant are immutable';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION prevent_physical_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'physical DELETE is prohibited on %.%; use a status change or correcting transaction',
        TG_TABLE_SCHEMA, TG_TABLE_NAME;
END;
$$;

CREATE OR REPLACE FUNCTION audit_row_change() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = platform, pg_temp AS $$
DECLARE
    v_before jsonb;
    v_after jsonb;
    v_tenant uuid;
    v_id uuid;
    v_actor uuid;
    v_version integer;
    v_changed text[];
BEGIN
    v_before := CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE to_jsonb(OLD) END;
    v_after := CASE WHEN TG_OP = 'DELETE' THEN NULL ELSE to_jsonb(NEW) END;
    v_tenant := COALESCE(NULLIF(v_after ->> 'tenant_id', '')::uuid, NULLIF(v_before ->> 'tenant_id', '')::uuid);
    v_id := COALESCE(
        NULLIF(v_after ->> 'record_id', '')::uuid, NULLIF(v_before ->> 'record_id', '')::uuid,
        NULLIF(v_after ->> 'relation_id', '')::uuid, NULLIF(v_before ->> 'relation_id', '')::uuid,
        NULLIF(v_after ->> 'transaction_id', '')::uuid, NULLIF(v_before ->> 'transaction_id', '')::uuid,
        NULLIF(v_after ->> 'transaction_line_id', '')::uuid, NULLIF(v_before ->> 'transaction_line_id', '')::uuid
    );
    v_actor := COALESCE(
        NULLIF(v_after ->> 'updated_by', '')::uuid,
        NULLIF(v_after ->> 'created_by', '')::uuid,
        NULLIF(current_setting('app.actor_id', true), '')::uuid
    );
    v_version := COALESCE(NULLIF(v_after ->> 'version_no', '')::integer, NULLIF(v_before ->> 'version_no', '')::integer);

    SELECT COALESCE(array_agg(k ORDER BY k), '{}') INTO v_changed
    FROM (
        SELECT jsonb_object_keys(COALESCE(v_before, '{}'::jsonb)) AS k
        UNION
        SELECT jsonb_object_keys(COALESCE(v_after, '{}'::jsonb)) AS k
    ) keys
    WHERE v_before -> k IS DISTINCT FROM v_after -> k;

    PERFORM assert_actor_tenant(v_actor, v_tenant);

    INSERT INTO change_events (
        tenant_id, aggregate_type, aggregate_id, event_type, row_version,
        before_data, after_data, changed_fields, reason, correlation_id, actor_id
    ) VALUES (
        v_tenant, TG_TABLE_NAME, v_id, lower(TG_OP), v_version,
        v_before, v_after, v_changed,
        NULLIF(current_setting('app.change_reason', true), ''),
        NULLIF(current_setting('app.correlation_id', true), '')::uuid,
        v_actor
    );
    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_industries_updated BEFORE UPDATE ON industries FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_tenants_updated BEFORE UPDATE ON tenants FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_actors_updated BEFORE UPDATE ON actors FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_modules_updated BEFORE UPDATE ON modules FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_entities_updated BEFORE UPDATE ON entity_definitions FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_fields_updated BEFORE UPDATE ON field_definitions FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_wrappers_updated BEFORE UPDATE ON wrapper_definitions FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_10_records_version BEFORE UPDATE ON business_records FOR EACH ROW EXECUTE FUNCTION maintain_business_version();
CREATE TRIGGER trg_20_records_validate BEFORE INSERT OR UPDATE ON business_records FOR EACH ROW EXECUTE FUNCTION validate_business_record();
CREATE TRIGGER trg_10_transactions_version BEFORE UPDATE ON business_transactions FOR EACH ROW EXECUTE FUNCTION maintain_business_version();
CREATE TRIGGER trg_20_transactions_validate BEFORE INSERT OR UPDATE ON business_transactions FOR EACH ROW EXECUTE FUNCTION validate_business_transaction();
CREATE TRIGGER trg_relations_validate BEFORE INSERT OR UPDATE ON record_relations FOR EACH ROW EXECUTE FUNCTION validate_relation_actor();
CREATE TRIGGER trg_lines_validate BEFORE INSERT OR UPDATE ON transaction_lines FOR EACH ROW EXECUTE FUNCTION validate_transaction_line();

CREATE TRIGGER trg_records_no_delete BEFORE DELETE ON business_records FOR EACH ROW EXECUTE FUNCTION prevent_physical_delete();
CREATE TRIGGER trg_relations_no_delete BEFORE DELETE ON record_relations FOR EACH ROW EXECUTE FUNCTION prevent_physical_delete();
CREATE TRIGGER trg_transactions_no_delete BEFORE DELETE ON business_transactions FOR EACH ROW EXECUTE FUNCTION prevent_physical_delete();
CREATE TRIGGER trg_lines_no_delete BEFORE DELETE ON transaction_lines FOR EACH ROW EXECUTE FUNCTION prevent_physical_delete();

CREATE TRIGGER trg_records_audit AFTER INSERT OR UPDATE OR DELETE ON business_records FOR EACH ROW EXECUTE FUNCTION audit_row_change();
CREATE TRIGGER trg_relations_audit AFTER INSERT OR UPDATE OR DELETE ON record_relations FOR EACH ROW EXECUTE FUNCTION audit_row_change();
CREATE TRIGGER trg_transactions_audit AFTER INSERT OR UPDATE OR DELETE ON business_transactions FOR EACH ROW EXECUTE FUNCTION audit_row_change();
CREATE TRIGGER trg_lines_audit AFTER INSERT OR UPDATE OR DELETE ON transaction_lines FOR EACH ROW EXECUTE FUNCTION audit_row_change();

CREATE VIEW v_active_records WITH (security_invoker = true) AS
SELECT r.record_id, r.tenant_id, m.module_code, e.entity_code, e.entity_name,
       r.business_key, r.record_status, r.data, r.schema_version, r.version_no, r.updated_at
FROM business_records r
JOIN entity_definitions e ON e.entity_definition_id = r.entity_definition_id
JOIN modules m ON m.module_id = e.module_id
WHERE r.record_status = 'active';

CREATE VIEW v_field_definition_catalog WITH (security_invoker = true) AS
SELECT m.module_code, e.definition_kind, e.entity_code, e.entity_name,
       e.scope, e.industry_code, e.tenant_id,
       f.field_definition_id, f.field_code, f.field_name, f.description,
       f.data_type, f.max_length, f.numeric_precision, f.numeric_scale,
       f.storage_path, f.is_required, f.is_multivalued, f.default_value,
       f.validation_rules, f.display_rules, f.semantic_tags, f.ai_description,
       f.sensitivity, f.promotion_state, f.is_history_tracked, f.example_value,
       f.sort_order
FROM entity_definitions e
JOIN modules m ON m.module_id = e.module_id
JOIN field_definitions f ON f.entity_definition_id = e.entity_definition_id
WHERE e.is_active AND f.is_active;

CREATE OR REPLACE FUNCTION current_tenant_id() RETURNS uuid LANGUAGE sql STABLE AS $$
    SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid;
$$;

ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE actors ENABLE ROW LEVEL SECURITY;
ALTER TABLE entity_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE field_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE business_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE record_relations ENABLE ROW LEVEL SECURITY;
ALTER TABLE business_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE transaction_lines ENABLE ROW LEVEL SECURITY;
ALTER TABLE wrapper_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE change_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenants_isolation ON tenants
    USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id());
CREATE POLICY actors_isolation ON actors
    USING (tenant_id IS NULL OR tenant_id = current_tenant_id())
    WITH CHECK (tenant_id IS NULL OR tenant_id = current_tenant_id());
CREATE POLICY entity_definitions_isolation ON entity_definitions
    USING (
        scope = 'platform'
        OR (scope = 'tenant' AND tenant_id = current_tenant_id())
        OR (scope = 'industry' AND industry_code = (SELECT t.industry_code FROM tenants t WHERE t.tenant_id = current_tenant_id()))
    )
    WITH CHECK (
        scope = 'platform'
        OR (scope = 'tenant' AND tenant_id = current_tenant_id())
        OR (scope = 'industry' AND industry_code = (SELECT t.industry_code FROM tenants t WHERE t.tenant_id = current_tenant_id()))
    );
CREATE POLICY field_definitions_isolation ON field_definitions
    USING (EXISTS (SELECT 1 FROM entity_definitions e WHERE e.entity_definition_id = field_definitions.entity_definition_id))
    WITH CHECK (EXISTS (SELECT 1 FROM entity_definitions e WHERE e.entity_definition_id = field_definitions.entity_definition_id));
CREATE POLICY business_records_isolation ON business_records
    USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id());
CREATE POLICY record_relations_isolation ON record_relations
    USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id());
CREATE POLICY business_transactions_isolation ON business_transactions
    USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id());
CREATE POLICY transaction_lines_isolation ON transaction_lines
    USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id());
CREATE POLICY wrapper_definitions_isolation ON wrapper_definitions
    USING (
        scope = 'platform'
        OR (scope = 'tenant' AND tenant_id = current_tenant_id())
        OR (scope = 'industry' AND industry_code = (SELECT t.industry_code FROM tenants t WHERE t.tenant_id = current_tenant_id()))
    )
    WITH CHECK (
        scope = 'platform'
        OR (scope = 'tenant' AND tenant_id = current_tenant_id())
        OR (scope = 'industry' AND industry_code = (SELECT t.industry_code FROM tenants t WHERE t.tenant_id = current_tenant_id()))
    );
CREATE POLICY change_events_isolation ON change_events USING (tenant_id = current_tenant_id());

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'platform_app') THEN
        CREATE ROLE platform_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
END;
$$;

GRANT USAGE ON SCHEMA platform TO platform_app;
GRANT USAGE ON TYPE definition_scope, definition_kind, value_kind, record_status, transaction_status TO platform_app;
GRANT SELECT ON industries, modules TO platform_app;
GRANT SELECT ON tenants, actors, entity_definitions, field_definitions, wrapper_definitions, change_events TO platform_app;
GRANT SELECT, INSERT, UPDATE ON business_records, record_relations, business_transactions, transaction_lines TO platform_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA platform TO platform_app;
GRANT SELECT ON v_active_records, v_field_definition_catalog TO platform_app;
GRANT EXECUTE ON FUNCTION effective_entity_definition(varchar, definition_kind, varchar, uuid) TO platform_app;
GRANT EXECUTE ON FUNCTION effective_field_definitions(varchar, definition_kind, varchar, uuid) TO platform_app;
GRANT EXECUTE ON FUNCTION effective_field_definitions(uuid, uuid) TO platform_app;
GRANT EXECUTE ON FUNCTION effective_wrapper_definitions(varchar, varchar, uuid) TO platform_app;
REVOKE ALL ON FUNCTION audit_row_change() FROM PUBLIC;

COMMIT;
