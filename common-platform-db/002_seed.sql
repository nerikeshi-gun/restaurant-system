BEGIN;
SET search_path = platform, public;

INSERT INTO industries (industry_code, industry_name, description) VALUES
('trading', '専門商社', '調達、販売、在庫、物流、与信などを扱う業種ラッパー'),
('manufacturing', '製造業', '材料、工程、設備、品質、製造実績などを扱う業種ラッパー')
ON CONFLICT (industry_code) DO UPDATE
SET industry_name = EXCLUDED.industry_name, description = EXCLUDED.description, is_active = true;

INSERT INTO modules (module_code, module_name, description) VALUES
('party', '取引先・組織', '顧客、仕入先、拠点、担当者を共通の関係者として管理'),
('catalog', '品目・サービス', '商品、材料、製品、サービスを共通レコードとして管理'),
('operation', '業務トランザクション', '受発注、入出荷、製造、作業、問い合わせ等の事実を蓄積'),
('platform', '共通基盤', '項目、画面、ワークフロー、API、レポート、AI定義を管理')
ON CONFLICT (module_code) DO UPDATE
SET module_name = EXCLUDED.module_name, description = EXCLUDED.description, is_active = true;

INSERT INTO entity_definitions
    (module_id, definition_kind, scope, entity_code, entity_name, description, lifecycle)
SELECT m.module_id, v.definition_kind::definition_kind, 'platform', v.entity_code,
       v.entity_name, v.description, v.lifecycle::jsonb
FROM modules m
JOIN (VALUES
    ('party','record','party','取引先・組織','顧客・仕入先を固定テーブルに分断せず役割で表現する','{"states":["draft","active","inactive","archived"]}'),
    ('catalog','record','item','品目・サービス','販売品、購入品、材料、製品、サービスを共通表現する','{"states":["draft","active","inactive","archived"]}'),
    ('operation','transaction','business_event','共通業務イベント','受発注、入出荷、製造、作業等の事実を共通取引として表現する','{"states":["draft","posted","completed","cancelled","corrected"]}')
) AS v(module_code,definition_kind,entity_code,entity_name,description,lifecycle)
ON m.module_code = v.module_code
ON CONFLICT ON CONSTRAINT uq_entity_definitions_scope DO UPDATE
SET entity_name = EXCLUDED.entity_name,
    description = EXCLUDED.description,
    lifecycle = EXCLUDED.lifecycle,
    is_active = true;

INSERT INTO field_definitions
    (entity_definition_id, field_code, field_name, description, data_type,
     max_length, numeric_precision, numeric_scale, storage_path, is_required,
     default_value, validation_rules, display_rules, semantic_tags, ai_description,
     sensitivity, promotion_state, is_history_tracked, example_value, sort_order)
SELECT e.entity_definition_id, v.field_code, v.field_name, v.description,
       v.data_type::value_kind, v.max_length, v.numeric_precision, v.numeric_scale,
       v.storage_path, v.is_required, v.default_value::jsonb,
       v.validation_rules::jsonb, v.display_rules::jsonb, v.semantic_tags,
       v.ai_description, v.sensitivity, v.promotion_state, v.is_history_tracked,
       v.example_value::jsonb, v.sort_order
FROM entity_definitions e
JOIN modules m ON m.module_id = e.module_id
JOIN (VALUES
    ('party','record','business_key','業務キー','外部システムや人が対象を一意に識別するキー','string',200,NULL,NULL,'core.business_key',false,NULL,'{}','{"visible":true}',ARRAY['identity','integration'],'重複判定と外部参照に使う安定キー','internal','fixed',true,'"CUS-001"',1),
    ('party','record','record_status','状態','レコードの有効・無効・取消状態','string',30,NULL,NULL,'core.record_status',true,'"draft"','{"enum":["draft","active","inactive","archived","cancelled"]}','{"control":"select"}',ARRAY['lifecycle'],'利用可能性とライフサイクルを示す固定状態','internal','fixed',true,'"active"',2),
    ('party','record','name','名称','正式名称または表示名称','string',200,NULL,NULL,'data.name',true,NULL,'{}','{"control":"text","width":240}',ARRAY['identity','search'],'対象を人間とAIが識別する基本名称','internal','candidate',true,'"東都商事株式会社"',10),
    ('party','record','roles','役割','customer、supplier等。複数可','json',NULL,NULL,NULL,'data.roles',true,NULL,'{"items":{"type":"string"}}','{"control":"multiselect"}',ARRAY['classification'],'顧客・仕入先などの業務上の役割','internal','extension',true,'["customer","supplier"]',20),
    ('party','record','contact','連絡先','電話、メール、住所等','json',NULL,NULL,NULL,'data.contact',false,NULL,'{}','{"section":"contact"}',ARRAY['contact','personal'],'連絡手段。個人情報として最小権限で扱う','personal','extension',true,'{"email":"info@example.jp"}',30),
    ('item','record','business_key','業務キー','品目コード等の安定した識別キー','string',200,NULL,NULL,'core.business_key',false,NULL,'{}','{"visible":true}',ARRAY['identity','integration'],'品目を外部システムと照合する固定キー','internal','fixed',true,'"ITEM-001"',1),
    ('item','record','record_status','状態','品目の利用状態','string',30,NULL,NULL,'core.record_status',true,'"draft"','{"enum":["draft","active","inactive","archived","cancelled"]}','{"control":"select"}',ARRAY['lifecycle'],'品目が取引に利用可能かを示す','internal','fixed',true,'"active"',2),
    ('item','record','name','品目名','品目・サービスの表示名称','string',200,NULL,NULL,'data.name',true,NULL,'{}','{"control":"text","width":240}',ARRAY['identity','search'],'品目を識別する名称','internal','candidate',true,'"高耐熱ボルト"',10),
    ('item','record','item_type','品目区分','product、material、service、asset','string',30,NULL,NULL,'data.item_type',true,NULL,'{"enum":["product","material","service","asset"]}','{"control":"select"}',ARRAY['classification'],'販売品・材料・サービス等の共通区分','internal','candidate',true,'"product"',20),
    ('item','record','base_unit','基本単位','個、kg、時間等','string',30,NULL,NULL,'data.base_unit',false,NULL,'{}','{"control":"text","width":80}',ARRAY['quantity'],'数量解釈に使う基本単位','internal','candidate',true,'"pcs"',30),
    ('business_event','transaction','business_date','業務日','集計・締め処理の基準日','date',NULL,NULL,NULL,'core.business_date',true,NULL,'{}','{"control":"date"}',ARRAY['time','accounting'],'業務上この事実が属する日付','internal','fixed',true,'"2026-09-03"',1),
    ('business_event','transaction','transaction_status','取引状態','下書き・計上済・完了・取消・訂正済','string',30,NULL,NULL,'core.transaction_status',true,'"draft"','{"enum":["draft","posted","completed","cancelled","corrected"]}','{"control":"select"}',ARRAY['lifecycle'],'取引事実の現在状態。削除の代わりに更新する','internal','fixed',true,'"posted"',2),
    ('business_event','transaction','amount','金額','取引ヘッダの共通金額','decimal',NULL,20,4,'core.amount',false,NULL,'{}','{"format":"currency"}',ARRAY['amount'],'通貨コードと組み合わせて集計する固定金額','confidential','fixed',true,'125000.0000',3),
    ('business_event','transaction','reference_no','参照番号','伝票番号や外部参照番号','string',100,NULL,NULL,'data.reference_no',true,NULL,'{}','{"control":"text"}',ARRAY['identity','search'],'業務担当者とAIが取引を照合する番号','internal','candidate',true,'"SO-2026-001"',10),
    ('business_event','transaction','note','摘要','取引に関する自由記述','text',1000,NULL,NULL,'data.note',false,NULL,'{}','{"control":"textarea"}',ARRAY['memo'],'取引背景を補足する。事実と推測を混同しない','internal','extension',true,'"定期受注"',20)
) AS v(entity_code,definition_kind,field_code,field_name,description,data_type,max_length,numeric_precision,numeric_scale,storage_path,is_required,default_value,validation_rules,display_rules,semantic_tags,ai_description,sensitivity,promotion_state,is_history_tracked,example_value,sort_order)
ON e.entity_code = v.entity_code
AND e.definition_kind = v.definition_kind::definition_kind
AND e.scope = 'platform'
ON CONFLICT ON CONSTRAINT uq_field_definitions_code DO UPDATE
SET field_name = EXCLUDED.field_name,
    description = EXCLUDED.description,
    data_type = EXCLUDED.data_type,
    max_length = EXCLUDED.max_length,
    numeric_precision = EXCLUDED.numeric_precision,
    numeric_scale = EXCLUDED.numeric_scale,
    storage_path = EXCLUDED.storage_path,
    is_required = EXCLUDED.is_required,
    default_value = EXCLUDED.default_value,
    validation_rules = EXCLUDED.validation_rules,
    display_rules = EXCLUDED.display_rules,
    semantic_tags = EXCLUDED.semantic_tags,
    ai_description = EXCLUDED.ai_description,
    sensitivity = EXCLUDED.sensitivity,
    promotion_state = EXCLUDED.promotion_state,
    is_history_tracked = EXCLUDED.is_history_tracked,
    example_value = EXCLUDED.example_value,
    sort_order = EXCLUDED.sort_order,
    is_active = true;

COMMIT;
