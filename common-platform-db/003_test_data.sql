BEGIN;
SET search_path = platform, public;

INSERT INTO tenants (tenant_code, tenant_name, industry_code) VALUES
('alpha-trading', 'アルファ専門商事株式会社', 'trading'),
('beta-manufacturing', 'ベータ製造株式会社', 'manufacturing');

INSERT INTO actors (tenant_id, actor_type, actor_code, display_name)
SELECT tenant_id, 'user', 'admin', tenant_name || ' 管理者'
FROM tenants
WHERE tenant_code IN ('alpha-trading', 'beta-manufacturing');

-- 業種別・企業別の定義レイヤー。共通定義と同じ module/kind/entity_code を使う。
INSERT INTO entity_definitions
    (module_id, definition_kind, scope, industry_code, entity_code, entity_name, description)
SELECT m.module_id, 'record', 'industry', v.industry_code, 'item', v.entity_name, v.description
FROM modules m
CROSS JOIN (VALUES
    ('trading','商社向け品目','メーカー型番等を追加'),
    ('manufacturing','製造業向け品目','材質・規格等を追加')
) AS v(industry_code,entity_name,description)
WHERE m.module_code = 'catalog';

INSERT INTO entity_definitions
    (module_id, definition_kind, scope, tenant_id, entity_code, entity_name, description)
SELECT m.module_id, 'record', 'tenant', t.tenant_id, 'item', t.tenant_name || ' 品目', '企業固有の品目定義'
FROM modules m CROSS JOIN tenants t
WHERE m.module_code = 'catalog'
  AND t.tenant_code IN ('alpha-trading', 'beta-manufacturing');

INSERT INTO field_definitions
    (entity_definition_id, field_code, field_name, description, data_type, max_length,
     storage_path, is_required, validation_rules, display_rules, semantic_tags,
     ai_description, sensitivity, promotion_state, is_history_tracked, example_value, sort_order)
SELECT e.entity_definition_id, v.field_code, v.field_name, v.description,
       v.data_type::value_kind, v.max_length, 'data.' || v.field_code, v.is_required,
       v.validation_rules::jsonb, v.display_rules::jsonb, v.semantic_tags,
       v.ai_description, v.sensitivity, v.promotion_state, true, v.example_value::jsonb, v.sort_order
FROM entity_definitions e
JOIN (VALUES
    ('industry','trading',NULL,'name','商材名','商社で扱う商材の名称','string',200,true,'{}','{"label":"商材名"}',ARRAY['identity','search'],'商社業務で扱う品目名。共通のnameを上書きする','internal','candidate','"耐熱ボルト"',10),
    ('industry','trading',NULL,'manufacturer_part_no','メーカー型番','メーカーが付与した型番','string',100,true,'{"pattern":"^[A-Z0-9-]+$"}','{"control":"text"}',ARRAY['manufacturer','search'],'仕入先メーカーの型番。自社SKUと区別する','internal','extension','"HTB-M10-50"',40),
    ('industry','manufacturing',NULL,'material_grade','材質規格','材料の規格・グレード','string',80,true,'{}','{"control":"text"}',ARRAY['material','quality'],'製造条件と品質判定に使う材質規格','internal','extension','"SUS304"',40),
    ('tenant',NULL,'alpha-trading','name','アルファ商材名','アルファ社での表示名','string',200,true,'{}','{"label":"アルファ商材名"}',ARRAY['identity','search'],'アルファ社が使用する商材表示名。最優先定義','internal','candidate','"高耐熱六角ボルト"',10),
    ('tenant',NULL,'alpha-trading','tenant_sku','自社SKU','アルファ社固有の商品コード','string',50,true,'{"pattern":"^A-[0-9]{4}$"}','{"control":"text"}',ARRAY['identity','search'],'アルファ社内で品目を一意に扱うコード','internal','extension','"A-1001"',50),
    ('tenant',NULL,'beta-manufacturing','inspection_code','検査区分','ベータ社固有の受入検査区分','string',30,true,'{"enum":["standard","strict"]}','{"control":"select"}',ARRAY['quality'],'ベータ社の検査ワークフロー選択に使う','confidential','extension','"strict"',50)
) AS v(scope,industry_code,tenant_code,field_code,field_name,description,data_type,max_length,is_required,validation_rules,display_rules,semantic_tags,ai_description,sensitivity,promotion_state,example_value,sort_order)
ON e.scope::text = v.scope
LEFT JOIN tenants t ON t.tenant_id = e.tenant_id
WHERE (e.scope = 'industry' AND e.industry_code = v.industry_code)
   OR (e.scope = 'tenant' AND t.tenant_code = v.tenant_code);

-- ラッパーも共通→業種→企業で重ねる。
INSERT INTO wrapper_definitions
    (module_id, scope, industry_code, tenant_id, wrapper_code, wrapper_name, wrapper_type, definition)
SELECT m.module_id, v.scope::definition_scope, v.industry_code, t.tenant_id,
       'item_search', v.wrapper_name, 'agent', v.definition::jsonb
FROM modules m
CROSS JOIN (VALUES
    ('platform',NULL,NULL,'共通品目検索AI','{"fields":["name","item_type"]}'),
    ('industry','trading',NULL,'商社向け品目検索AI','{"fields":["name","manufacturer_part_no"]}'),
    ('tenant',NULL,'alpha-trading','アルファ社品目検索AI','{"fields":["name","tenant_sku","manufacturer_part_no"]}')
) AS v(scope,industry_code,tenant_code,wrapper_name,definition)
LEFT JOIN tenants t ON t.tenant_code = v.tenant_code
WHERE m.module_code = 'catalog';

-- マスター相当レコード。
INSERT INTO business_records
    (tenant_id, entity_definition_id, business_key, record_status, data, created_by, updated_by)
SELECT t.tenant_id, e.entity_definition_id, 'A-PARTY-001', 'active',
       '{"name":"東都部品株式会社","roles":["customer"],"contact":{"email":"sales@tohto.example"}}',
       a.actor_id, a.actor_id
FROM tenants t
JOIN actors a ON a.tenant_id = t.tenant_id AND a.actor_code = 'admin'
CROSS JOIN LATERAL effective_entity_definition('party','record','party',t.tenant_id) e
WHERE t.tenant_code = 'alpha-trading';

INSERT INTO business_records
    (tenant_id, entity_definition_id, business_key, record_status, data, created_by, updated_by)
SELECT t.tenant_id, e.entity_definition_id, 'A-ITEM-001', 'active',
       '{"name":"高耐熱六角ボルト","item_type":"product","base_unit":"pcs","manufacturer_part_no":"HTB-M10-50","tenant_sku":"A-1001"}',
       a.actor_id, a.actor_id
FROM tenants t
JOIN actors a ON a.tenant_id = t.tenant_id AND a.actor_code = 'admin'
CROSS JOIN LATERAL effective_entity_definition('catalog','record','item',t.tenant_id) e
WHERE t.tenant_code = 'alpha-trading';

INSERT INTO business_records
    (tenant_id, entity_definition_id, business_key, record_status, data, created_by, updated_by)
SELECT t.tenant_id, e.entity_definition_id, 'B-ITEM-001', 'active',
       '{"name":"ステンレス鋼板","item_type":"material","base_unit":"kg","material_grade":"SUS304","inspection_code":"strict"}',
       a.actor_id, a.actor_id
FROM tenants t
JOIN actors a ON a.tenant_id = t.tenant_id AND a.actor_code = 'admin'
CROSS JOIN LATERAL effective_entity_definition('catalog','record','item',t.tenant_id) e
WHERE t.tenant_code = 'beta-manufacturing';

INSERT INTO record_relations (tenant_id, from_record_id, to_record_id, relation_type, created_by)
SELECT p.tenant_id, p.record_id, i.record_id, 'purchases_item', a.actor_id
FROM business_records p
JOIN business_records i ON i.tenant_id = p.tenant_id AND i.business_key = 'A-ITEM-001'
JOIN actors a ON a.tenant_id = p.tenant_id AND a.actor_code = 'admin'
WHERE p.business_key = 'A-PARTY-001';

SELECT set_config('app.actor_id', (SELECT actor_id::text FROM actors a JOIN tenants t USING (tenant_id) WHERE t.tenant_code='alpha-trading' AND a.actor_code='admin'), true);
SELECT set_config('app.change_reason', '初回テストデータ登録', true);

INSERT INTO business_transactions
    (tenant_id, module_id, transaction_definition_id, transaction_type, transaction_status,
     subject_record_id, external_key, currency_code, amount, data, created_by, updated_by)
SELECT t.tenant_id, m.module_id, e.entity_definition_id, 'business_event', 'posted',
       p.record_id, 'A-SO-001', 'JPY', 125000,
       '{"reference_no":"SO-2026-001","note":"定期受注"}', a.actor_id, a.actor_id
FROM tenants t
JOIN actors a ON a.tenant_id=t.tenant_id AND a.actor_code='admin'
JOIN business_records p ON p.tenant_id=t.tenant_id AND p.business_key='A-PARTY-001'
JOIN modules m ON m.module_code='operation'
CROSS JOIN LATERAL effective_entity_definition('operation','transaction','business_event',t.tenant_id) e
WHERE t.tenant_code='alpha-trading';

INSERT INTO transaction_lines
    (tenant_id, transaction_id, line_no, line_type, related_record_id, quantity, unit_code, unit_price, line_amount)
SELECT x.tenant_id, x.transaction_id, 1, 'item', i.record_id, 100, 'pcs', 1250, 125000
FROM business_transactions x
JOIN business_records i ON i.tenant_id=x.tenant_id AND i.business_key='A-ITEM-001'
WHERE x.external_key='A-SO-001';

INSERT INTO business_transactions
    (tenant_id, module_id, transaction_definition_id, transaction_type, transaction_status,
     subject_record_id, external_key, amount, data, created_by, updated_by)
SELECT t.tenant_id, m.module_id, e.entity_definition_id, 'business_event', 'posted',
       i.record_id, 'B-MO-001', 500,
       '{"reference_no":"MO-2026-001","note":"試作ロット"}', a.actor_id, a.actor_id
FROM tenants t
JOIN actors a ON a.tenant_id=t.tenant_id AND a.actor_code='admin'
JOIN business_records i ON i.tenant_id=t.tenant_id AND i.business_key='B-ITEM-001'
JOIN modules m ON m.module_code='operation'
CROSS JOIN LATERAL effective_entity_definition('operation','transaction','business_event',t.tenant_id) e
WHERE t.tenant_code='beta-manufacturing';

-- 更新前後、取消、訂正を履歴へ残す。
SELECT set_config('app.change_reason', '品目表示名の改訂', true);
UPDATE business_records
SET data = jsonb_set(data, '{name}', '"超高耐熱六角ボルト"'), updated_by = created_by
WHERE business_key = 'A-ITEM-001';

SELECT set_config('app.actor_id', (SELECT actor_id::text FROM actors a JOIN tenants t USING (tenant_id) WHERE t.tenant_code='beta-manufacturing' AND a.actor_code='admin'), true);
SELECT set_config('app.change_reason', '製造指示の取消', true);
UPDATE business_transactions
SET transaction_status='cancelled', cancellation_reason='試作計画変更', updated_by=created_by
WHERE external_key='B-MO-001';

SELECT set_config('app.actor_id', (SELECT actor_id::text FROM actors a JOIN tenants t USING (tenant_id) WHERE t.tenant_code='alpha-trading' AND a.actor_code='admin'), true);
SELECT set_config('app.change_reason', '受注数量訂正', true);
UPDATE business_transactions SET transaction_status='corrected', updated_by=created_by
WHERE external_key='A-SO-001';

INSERT INTO business_transactions
    (tenant_id, module_id, transaction_definition_id, transaction_type, transaction_status,
     subject_record_id, supersedes_transaction_id, external_key, currency_code, amount,
     data, created_by, updated_by)
SELECT x.tenant_id, x.module_id, x.transaction_definition_id, x.transaction_type, 'posted',
       x.subject_record_id, x.transaction_id, 'A-SO-001-R1', x.currency_code, 120000,
       '{"reference_no":"SO-2026-001-R1","note":"数量訂正版"}', x.created_by, x.updated_by
FROM business_transactions x WHERE x.external_key='A-SO-001';

INSERT INTO transaction_lines
    (tenant_id, transaction_id, line_no, line_type, related_record_id, quantity, unit_code, unit_price, line_amount)
SELECT x.tenant_id, x.transaction_id, 1, 'item', i.record_id, 96, 'pcs', 1250, 120000
FROM business_transactions x
JOIN business_records i ON i.tenant_id=x.tenant_id AND i.business_key='A-ITEM-001'
WHERE x.external_key='A-SO-001-R1';

COMMIT;
