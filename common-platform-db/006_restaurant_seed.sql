-- 006_restaurant_seed.sql
-- 飲食業の業種ラッパー：場所・商品・来店セッションのレコード定義と、活動（取引）定義。
-- 005_core_record.sql の後に適用する。
BEGIN;
SET search_path = platform, public;

INSERT INTO industries (industry_code, industry_name, description) VALUES
('restaurant', '飲食業', '店舗、席、商品、注文、調理、会計などを扱う業種ラッパー')
ON CONFLICT (industry_code) DO UPDATE
SET industry_name = EXCLUDED.industry_name, description = EXCLUDED.description, is_active = true;

-- ---------------------------------------------------------------
-- レコード定義（マスタ）
-- ---------------------------------------------------------------
INSERT INTO entity_definitions
    (module_id, definition_kind, scope, industry_code, entity_code, entity_name, description, lifecycle)
SELECT m.module_id, v.definition_kind::definition_kind, 'industry', 'restaurant',
       v.entity_code, v.entity_name, v.description, v.lifecycle::jsonb
FROM modules m
JOIN (VALUES
    ('party',   'record', 'location',      '場所',
     '本部・店舗・フロア・席・倉庫。階層は record_relations の located_in で表す',
     '{"states":["draft","active","inactive","archived"]}'),
    ('catalog', 'record', 'product',       '販売商品',
     'お客様へ販売する商品。仕入・在庫の品目(item)とは分ける',
     '{"states":["draft","active","inactive","archived"]}'),
    ('catalog', 'record', 'modifier_group', '調整分類',
     'サイズ、盛り、辛さなどの調整の分類。商品へは permits_modifier 関係で割り当てる',
     '{"states":["draft","active","inactive","archived"]}'),
    ('catalog', 'record', 'modifier_option', '調整選択肢',
     '小・中・大、大盛などの選択肢。調整分類へは option_of 関係で属する',
     '{"states":["draft","active","inactive","archived"]}'),
    ('operation','record','visit_session', '来店セッション',
     '席の利用開始から終了までの来店単位。匿名で、会員IDは後から関連付ける',
     '{"states":["draft","active","archived"]}'),
    ('operation','transaction','order_line',        '注文明細',
     '人が確認して確定した注文の一明細', '{"states":["posted"]}'),
    ('operation','transaction','kitchen_status_set','厨房状態変更',
     '未着手・調理中・提供済みなどの状態変更を追記する', '{"states":["posted"]}'),
    ('operation','transaction','order_cancel',      '注文取消',
     '確定済み明細の取消。反対記録として追記する',
     '{"states":["posted"],"requires_staff_confirmation":true}'),
    ('operation','transaction','payment_received',  '入金',
     '会計での支払受領', '{"states":["posted"],"requires_staff_confirmation":true}'),
    ('operation','transaction','service_request',   'サービス依頼',
     'お冷、こぼした、あと何分、会計依頼など', '{"states":["posted"]}'),
    ('operation','transaction','availability_set',  '販売可否変更',
     '売り切れ・販売再開。販売可否は商品マスタではなく活動から投影する', '{"states":["posted"]}')
) AS v(module_code, definition_kind, entity_code, entity_name, description, lifecycle)
ON m.module_code = v.module_code
ON CONFLICT ON CONSTRAINT uq_entity_definitions_scope DO UPDATE
SET entity_name = EXCLUDED.entity_name,
    description = EXCLUDED.description,
    lifecycle = EXCLUDED.lifecycle,
    is_active = true;

-- ---------------------------------------------------------------
-- 項目定義（すべて data.* の拡張項目。検索・集計で必要になったら昇格させる）
-- ---------------------------------------------------------------
INSERT INTO field_definitions
    (entity_definition_id, field_code, field_name, description, data_type, max_length,
     storage_path, is_required, validation_rules, sensitivity, promotion_state, sort_order)
SELECT e.entity_definition_id, v.field_code, v.field_name, v.description,
       v.data_type::value_kind, v.max_length, 'data.' || v.field_code, v.is_required,
       v.validation_rules::jsonb, v.sensitivity, 'extension', v.sort_order
FROM entity_definitions e
JOIN (VALUES
    ('location','location_type','場所区分','headquarters / store / floor / table / storage','string',30,true,
     '{"enum":["headquarters","store","floor","table","storage"]}','internal',10),
    ('location','seats','席数','席の収容人数','integer',NULL,false,'{"minimum":1}','internal',20),
    ('location','qr_token','QRトークン','卓上端末の識別用。漏えい時は再発行する','string',100,false,'{}','restricted',30),
    ('location','area_label','エリア表示','画面に出す案内名','string',100,false,'{}','internal',40),

    ('product','kitchen_name','厨房表示名','厨房画面と伝票に出す短い名称','string',100,false,'{}','internal',10),
    ('product','price','販売単価','現在の販売単価。確定時は core_record.unit_price にスナップショットする','decimal',NULL,true,'{"minimum":0}','internal',20),
    ('product','tax_category','税区分','standard / reduced / exempt','string',20,true,
     '{"enum":["standard","reduced","exempt"]}','internal',30),
    ('product','category','表示分類','ドリンク、料理など','string',100,false,'{}','internal',40),
    ('product','aliases','別名・読み','音声認識の別名、略称、読み、よくある誤認識','json',NULL,false,'{}','internal',50),

    ('product','reading','読み','ひらがな・カタカナの読み。音声認識の照合に使う','string',200,false,'{}','internal',60),
    ('product','size_label','サイズ表示','大・中・小など商品に固有の表示','string',50,false,'{}','internal',70),
    ('product','set_contents','セット内容','セット商品の構成の説明','text',500,false,'{}','internal',80),
    ('product','localized_names','多言語名称','言語コードをキーにした表示名。例 {"en":"Rice"}','json',NULL,false,'{}','internal',90),

    ('modifier_group','selection_type','選択方式','single: 一つだけ / multiple: 複数','string',20,true,
     '{"enum":["single","multiple"]}','internal',10),
    ('modifier_option','price_delta','追加料金','標準からの価格差。マイナスも可','decimal',NULL,true,'{}','internal',10),
    ('modifier_option','is_default','標準選択','true で初期選択。必須項目でも自動選択はしない','boolean',NULL,false,'{}','internal',20),

    ('visit_session','party_size','人数','来店人数','integer',NULL,false,'{"minimum":1}','internal',10),

    ('order_line','modifiers','調整','サイズ、盛り、辛さなどの選択結果','json',NULL,false,'{}','internal',10),
    ('order_line','original_text','原文','音声認識または入力された原文','text',2000,false,'{}','internal',20),
    ('order_line','input_language','入力言語','ja, en など','string',10,false,'{}','internal',30),
    ('order_line','notes','備考','調理メモ','text',500,false,'{}','internal',40),

    ('kitchen_status_set','kitchen_status','厨房状態','pending / cooking / served / cancelled','string',20,true,
     '{"enum":["pending","cooking","served","cancelled"]}','internal',10),

    ('order_cancel','reason','取消理由','取消の理由','text',500,true,'{}','internal',10),

    ('payment_received','payment_method','支払方法','cash / card / qr / other','string',20,true,
     '{"enum":["cash","card","qr","other"]}','confidential',10),
    ('payment_received','tendered','受領額','お預かり額','decimal',NULL,false,'{"minimum":0}','confidential',20),

    ('service_request','request_type','依頼種別','water / spill / wait_time / checkout / other','string',20,true,
     '{"enum":["water","spill","wait_time","checkout","other"]}','internal',10),
    ('service_request','message','内容','依頼内容','text',500,false,'{}','internal',20),

    ('availability_set','available','販売可否','false で売り切れ','boolean',NULL,true,'{}','internal',10)
) AS v(entity_code, field_code, field_name, description, data_type, max_length, is_required,
       validation_rules, sensitivity, sort_order)
  ON e.entity_code = v.entity_code AND e.scope = 'industry' AND e.industry_code = 'restaurant'
ON CONFLICT ON CONSTRAINT uq_field_definitions_code DO UPDATE
SET field_name = EXCLUDED.field_name,
    description = EXCLUDED.description,
    data_type = EXCLUDED.data_type,
    max_length = EXCLUDED.max_length,
    is_required = EXCLUDED.is_required,
    validation_rules = EXCLUDED.validation_rules,
    sensitivity = EXCLUDED.sensitivity,
    sort_order = EXCLUDED.sort_order,
    is_active = true;

COMMIT;
