\set ON_ERROR_STOP on
SET client_min_messages = warning;
SET search_path = platform, public;

CREATE TEMP TABLE verification_results (
    test_name text PRIMARY KEY,
    passed boolean NOT NULL,
    detail text NOT NULL
);

INSERT INTO verification_results
SELECT '01_object_inventory',
       table_count = 12 AND view_count = 2 AND function_count >= 14
           AND trigger_count >= 20 AND index_count >= 25,
       format('tables=%s views=%s functions=%s triggers=%s indexes=%s',
              table_count, view_count, function_count, trigger_count, index_count)
FROM (
    SELECT
      (SELECT count(*) FROM information_schema.tables WHERE table_schema='platform' AND table_type='BASE TABLE') table_count,
      (SELECT count(*) FROM information_schema.views WHERE table_schema='platform') view_count,
      (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='platform') function_count,
      (SELECT count(*) FROM information_schema.triggers WHERE trigger_schema='platform') trigger_count,
      (SELECT count(*) FROM pg_indexes WHERE schemaname='platform') index_count
) x;

INSERT INTO verification_results
SELECT '02_alpha_effective_fields',
       bool_and(expected_present = actual_present),
       string_agg(field_code || '=' || actual_present, ', ' ORDER BY field_code)
FROM (
    SELECT v.field_code, v.expected_present,
           EXISTS (
             SELECT 1 FROM effective_field_definitions('catalog','record','item',
               (SELECT tenant_id FROM tenants WHERE tenant_code='alpha-trading')) f
             WHERE f.field_code=v.field_code
           ) actual_present
    FROM (VALUES
      ('name',true),('manufacturer_part_no',true),('tenant_sku',true),
      ('material_grade',false),('inspection_code',false)
    ) v(field_code,expected_present)
) checks;

INSERT INTO verification_results
SELECT '03_alpha_override_precedence', source_scope='tenant' AND field_name='アルファ商材名',
       format('name source=%s label=%s',source_scope,field_name)
FROM effective_field_definitions('catalog','record','item',
       (SELECT tenant_id FROM tenants WHERE tenant_code='alpha-trading'))
WHERE field_code='name';

INSERT INTO verification_results
SELECT '04_beta_effective_fields',
       bool_and(expected_present = actual_present),
       string_agg(field_code || '=' || actual_present, ', ' ORDER BY field_code)
FROM (
    SELECT v.field_code, v.expected_present,
           EXISTS (
             SELECT 1 FROM effective_field_definitions('catalog','record','item',
               (SELECT tenant_id FROM tenants WHERE tenant_code='beta-manufacturing')) f
             WHERE f.field_code=v.field_code
           ) actual_present
    FROM (VALUES
      ('name',true),('material_grade',true),('inspection_code',true),
      ('manufacturer_part_no',false),('tenant_sku',false)
    ) v(field_code,expected_present)
) checks;

INSERT INTO verification_results
SELECT '05_wrapper_precedence',
       a_scope='tenant' AND b_scope='platform',
       format('alpha=%s beta=%s',a_scope,b_scope)
FROM (
  SELECT
    (SELECT scope::text FROM effective_wrapper_definitions('catalog','agent',
      (SELECT tenant_id FROM tenants WHERE tenant_code='alpha-trading')) WHERE wrapper_code='item_search') a_scope,
    (SELECT scope::text FROM effective_wrapper_definitions('catalog','agent',
      (SELECT tenant_id FROM tenants WHERE tenant_code='beta-manufacturing')) WHERE wrapper_code='item_search') b_scope
) x;

DO $$
DECLARE a_tenant uuid; b_record uuid; a_record uuid;
BEGIN
  SELECT tenant_id INTO a_tenant FROM tenants WHERE tenant_code='alpha-trading';
  SELECT record_id INTO a_record FROM business_records WHERE business_key='A-ITEM-001';
  SELECT record_id INTO b_record FROM business_records WHERE business_key='B-ITEM-001';
  BEGIN
    INSERT INTO record_relations(tenant_id,from_record_id,to_record_id,relation_type)
    VALUES(a_tenant,a_record,b_record,'invalid_cross_tenant');
    INSERT INTO verification_results VALUES('06_cross_tenant_relation_rejected',false,'insert unexpectedly succeeded');
  EXCEPTION WHEN foreign_key_violation THEN
    INSERT INTO verification_results VALUES('06_cross_tenant_relation_rejected',true,'composite tenant foreign key rejected it');
  END;
END $$;

DO $$
DECLARE b_tenant uuid; b_definition uuid; a_actor uuid;
BEGIN
  SELECT tenant_id INTO b_tenant FROM tenants WHERE tenant_code='beta-manufacturing';
  SELECT e.entity_definition_id INTO b_definition
    FROM effective_entity_definition('catalog','record','item',b_tenant) e;
  SELECT a.actor_id INTO a_actor FROM actors a JOIN tenants t USING(tenant_id)
    WHERE t.tenant_code='alpha-trading' AND a.actor_code='admin';
  BEGIN
    INSERT INTO business_records(tenant_id,entity_definition_id,business_key,record_status,data,created_by)
    VALUES(b_tenant,b_definition,'INVALID-ACTOR','active',
      '{"name":"invalid","item_type":"material","material_grade":"SUS304","inspection_code":"strict"}',a_actor);
    INSERT INTO verification_results VALUES('07_cross_tenant_actor_rejected',false,'insert unexpectedly succeeded');
  EXCEPTION WHEN OTHERS THEN
    INSERT INTO verification_results VALUES('07_cross_tenant_actor_rejected',SQLSTATE='P0001','SQLSTATE='||SQLSTATE);
  END;
END $$;

DO $$
DECLARE b_tenant uuid; a_definition uuid;
BEGIN
  SELECT tenant_id INTO b_tenant FROM tenants WHERE tenant_code='beta-manufacturing';
  SELECT e.entity_definition_id INTO a_definition
    FROM entity_definitions e JOIN tenants t ON t.tenant_id=e.tenant_id
    WHERE t.tenant_code='alpha-trading' AND e.entity_code='item' AND e.scope='tenant';
  BEGIN
    INSERT INTO business_records(tenant_id,entity_definition_id,business_key,record_status,data)
    VALUES(b_tenant,a_definition,'INVALID-DEFINITION','active','{}');
    INSERT INTO verification_results VALUES('08_cross_tenant_definition_rejected',false,'insert unexpectedly succeeded');
  EXCEPTION WHEN OTHERS THEN
    INSERT INTO verification_results VALUES('08_cross_tenant_definition_rejected',SQLSTATE='P0001','SQLSTATE='||SQLSTATE);
  END;
END $$;

DO $$
DECLARE a_tenant uuid; a_definition uuid;
BEGIN
  SELECT tenant_id INTO a_tenant FROM tenants WHERE tenant_code='alpha-trading';
  SELECT entity_definition_id INTO a_definition FROM effective_entity_definition('catalog','record','item',a_tenant);
  BEGIN
    INSERT INTO business_records(tenant_id,entity_definition_id,business_key,record_status,data)
    VALUES(a_tenant,a_definition,'INVALID-UNKNOWN','active',
      '{"name":"invalid","item_type":"product","manufacturer_part_no":"ABC-1","tenant_sku":"A-9999","unknown_key":"x"}');
    INSERT INTO verification_results VALUES('09_undefined_jsonb_rejected',false,'insert unexpectedly succeeded');
  EXCEPTION WHEN OTHERS THEN
    INSERT INTO verification_results VALUES('09_undefined_jsonb_rejected',SQLSTATE='P0001','SQLSTATE='||SQLSTATE);
  END;
  BEGIN
    INSERT INTO business_records(tenant_id,entity_definition_id,business_key,record_status,data)
    VALUES(a_tenant,a_definition,'INVALID-TYPE','active',
      '{"name":123,"item_type":"product","manufacturer_part_no":"ABC-1","tenant_sku":"A-9998"}');
    INSERT INTO verification_results VALUES('10_jsonb_type_rejected',false,'insert unexpectedly succeeded');
  EXCEPTION WHEN OTHERS THEN
    INSERT INTO verification_results VALUES('10_jsonb_type_rejected',SQLSTATE='P0001','SQLSTATE='||SQLSTATE);
  END;
END $$;

DO $$
BEGIN
  BEGIN
    DELETE FROM business_records WHERE business_key='A-ITEM-001';
    INSERT INTO verification_results VALUES('11_physical_delete_rejected',false,'delete unexpectedly succeeded');
  EXCEPTION WHEN OTHERS THEN
    INSERT INTO verification_results VALUES('11_physical_delete_rejected',SQLSTATE='P0001','SQLSTATE='||SQLSTATE);
  END;
END $$;

INSERT INTO verification_results
SELECT '12_update_audit_before_after',
       before_data #>> '{data,name}' = '高耐熱六角ボルト'
       AND after_data #>> '{data,name}' = '超高耐熱六角ボルト'
       AND changed_fields @> ARRAY['data']
       AND reason = '品目表示名の改訂',
       format('before=%s after=%s fields=%s reason=%s',before_data #>> '{data,name}',
              after_data #>> '{data,name}',changed_fields,reason)
FROM change_events
WHERE aggregate_id=(SELECT record_id FROM business_records WHERE business_key='A-ITEM-001')
  AND event_type='update'
ORDER BY event_id DESC LIMIT 1;

INSERT INTO verification_results
SELECT '13_jsonb_gin_search', count(*)=1,
       'matched='||count(*)
FROM business_records
WHERE tenant_id=(SELECT tenant_id FROM tenants WHERE tenant_code='alpha-trading')
  AND data @> '{"manufacturer_part_no":"HTB-M10-50"}';

INSERT INTO verification_results
SELECT '14_cancellation_is_historical',
       x.transaction_status='cancelled'
       AND x.cancellation_reason='試作計画変更'
       AND EXISTS (
         SELECT 1 FROM change_events c WHERE c.aggregate_id=x.transaction_id
           AND c.event_type='update'
           AND c.before_data->>'transaction_status'='posted'
           AND c.after_data->>'transaction_status'='cancelled'
       ),
       format('status=%s reason=%s',x.transaction_status,x.cancellation_reason)
FROM business_transactions x WHERE external_key='B-MO-001';

INSERT INTO verification_results
SELECT '15_correction_keeps_original',
       old.transaction_status='corrected'
       AND revision.supersedes_transaction_id=old.transaction_id
       AND old.transaction_id<>revision.transaction_id,
       format('old=%s revision=%s',old.transaction_id,revision.transaction_id)
FROM business_transactions old
JOIN business_transactions revision ON revision.external_key='A-SO-001-R1'
WHERE old.external_key='A-SO-001';

SELECT tenant_id AS alpha_tenant_id FROM tenants WHERE tenant_code='alpha-trading' \gset
GRANT SELECT, INSERT ON verification_results TO platform_app;
SET ROLE platform_app;
SELECT set_config('app.tenant_id', :'alpha_tenant_id', false);
INSERT INTO verification_results
SELECT '16_rls_hides_other_tenant',
       count(*) FILTER (WHERE business_key='B-ITEM-001')=0
       AND count(*) FILTER (WHERE business_key='A-ITEM-001')=1,
       'visible_records='||count(*)
FROM business_records;
RESET ROLE;
SELECT set_config('app.tenant_id', '', false);

INSERT INTO verification_results
SELECT '17_required_constraints_present', count(*) >= 18,
       'foreign_keys_and_checks='||count(*)
FROM information_schema.table_constraints
WHERE table_schema='platform' AND constraint_type IN ('FOREIGN KEY','CHECK');

TABLE verification_results ORDER BY test_name;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM verification_results WHERE NOT passed) THEN
    RAISE EXCEPTION 'verification failed: %',
      (SELECT string_agg(test_name, ', ') FROM verification_results WHERE NOT passed);
  END IF;
END $$;
