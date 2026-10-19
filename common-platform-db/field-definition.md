# 項目定義書

## 1. 記載規則

- 共通／業種別／企業別: `entity_definitions.scope` で管理する。固定列はすべて共通基盤。
- 固定列／JSONB／候補: `promotion_state=fixed/extension/candidate`。candidateは現在JSONBだが将来の固定列候補。
- NULL: `is_required=true` はJSONB値もNOT NULL相当。固定列はDDLのNOT NULLに従う。
- 履歴: 業務4テーブルは行全体を `change_events` に記録。項目単位は `is_history_tracked` で明示する。
- 機密: public / internal / confidential / personal / restricted。
- 表示規則はUI生成のヒントであり、権限制御の代替ではない。

## 2. 全テーブル共通列

|物理名|論理名|型・桁|NULL|キー・初期値|区分|履歴・機密|AI向け意味／入力・表示／例|
|---|---|---|---|---|---|---|---|
|`*_id`|各行ID|uuid|不可|PK、`gen_random_uuid()`|共通・固定|業務IDは履歴対象、internal|不変の技術ID。UIでは通常非表示|
|`tenant_id`|テナントID|uuid|業務表は不可|FK tenants、複合FKの先頭|共通・固定|履歴対象、restricted|データ境界。認証済みtenantと一致必須|
|`created_at`|作成日時|timestamptz|不可|`now()`|共通・固定|履歴対象、internal|最初に保存された時刻。ISO日時表示|
|`updated_at`|更新日時|timestamptz|不可|`now()`、trigger更新|共通・固定|履歴対象、internal|最後に変更された時刻|
|`created_by`|作成者|uuid|可|FK actors|共通・固定|履歴対象、confidential|作成を行った人・AI・service。他社actor禁止|
|`updated_by`|更新者|uuid|可|FK actors|共通・固定|履歴対象、confidential|直近更新者。他社actor禁止|
|`is_active`|有効フラグ|boolean|不可|true|共通・固定|履歴対象、internal|定義や主体が利用可能か。toggle表示|
|`version_no`|行版番号|integer|不可|1、更新時+1|共通・固定|履歴対象、internal|楽観ロックと変更順序。正整数|

## 3. メタデータ・テナント固定列

|テーブル.物理名|論理名|型・桁|NULL|キー・初期値|区分|履歴・機密|AI向け意味／入力・表示／例|
|---|---|---|---|---|---|---|---|
|`industries.industry_code`|業種コード|varchar(50)|不可|PK|共通・固定|定義履歴、internal|業種定義の不変キー。`trading`|
|`industries.industry_name`|業種名|varchar(200)|不可|-|共通・固定|定義履歴、internal|人向け業種名。`専門商社`|
|`industries.description`|業種説明|text|可|-|共通・固定|定義履歴、internal|業種ラッパーの適用範囲|
|`tenants.tenant_code`|企業コード|varchar(50)|不可|UNIQUE|-|共通・固定|履歴対象、confidential|企業の安定キー。`alpha-trading`|
|`tenants.tenant_name`|企業名|varchar(200)|不可|-|共通・固定|履歴対象、internal|表示名称|
|`tenants.industry_code`|所属業種|varchar(50)|可|FK industries|共通・固定|履歴対象、internal|適用する業種レイヤー|
|`tenants.default_locale`|既定ロケール|varchar(10)|不可|`ja-JP`|共通・固定|履歴対象、internal|日付・数値・文言表示|
|`tenants.default_timezone`|既定TZ|varchar(50)|不可|`Asia/Tokyo`|共通・固定|履歴対象、internal|日時解釈。IANA TZ名|
|`tenants.settings`|企業設定|jsonb object|不可|`{}`|企業別・JSONB|履歴対象、confidential|基盤設定。業務項目は保存しない|
|`actors.actor_type`|主体種別|varchar(30)|不可|CHECK user/agent/system/service|共通・固定|履歴対象、internal|操作主体の分類|
|`actors.actor_code`|主体コード|varchar(100)|不可|tenant内UNIQUE|共通・固定|履歴対象、confidential|認証主体との照合キー。`admin`|
|`actors.display_name`|主体表示名|varchar(200)|不可|-|共通・固定|履歴対象、personal|監査画面の表示名|
|`actors.external_subject`|外部認証sub|varchar(255)|可|-|共通・固定|履歴対象、restricted|IdP subject。通常非表示|
|`actors.attributes`|主体属性|jsonb object|不可|`{}`|企業別・JSONB|履歴対象、confidential|認可補助属性。権限判定は別途検証|
|`modules.module_code`|モジュールコード|varchar(80)|不可|UNIQUE|共通・固定|定義履歴、internal|定義名前空間。`catalog`|
|`modules.module_name`|モジュール名|varchar(200)|不可|-|共通・固定|定義履歴、internal|人向け領域名|
|`modules.description`|モジュール説明|text|可|-|共通・固定|定義履歴、internal|領域の責務|
|`modules.version`|モジュール版|varchar(30)|不可|`1.0.0`|共通・固定|定義履歴、internal|互換性判断用Semantic Version候補|
|`modules.settings`|モジュール設定|jsonb object|不可|`{}`|共通・JSONB|定義履歴、internal|モジュール全体の設定|
|`entity_definitions.module_id`|所属モジュール|uuid|不可|FK modules|共通・固定|定義履歴、internal|定義の名前空間|
|`entity_definitions.definition_kind`|定義種別|enum|不可|record|共通・固定|定義履歴、internal|master相当かtransactionか|
|`entity_definitions.scope`|定義範囲|enum|不可|platform|共通・固定|定義履歴、internal|上書き順位の階層|
|`entity_definitions.tenant_id`|対象企業|uuid|企業scopeのみ必須|FK tenants|企業別・固定|定義履歴、restricted|企業別定義の所有者|
|`entity_definitions.industry_code`|対象業種|varchar(50)|業種scopeのみ必須|FK industries|業種別・固定|定義履歴、internal|業種別定義の対象|
|`entity_definitions.entity_code`|定義コード|varchar(80)|不可|scope内UNIQUE|共通・固定|定義履歴、internal|API・AI用の不変名。`item`|
|`entity_definitions.entity_name`|定義名|varchar(200)|不可|-|各scope・固定|定義履歴、internal|利用者向け名称|
|`entity_definitions.current_schema_version`|スキーマ版|integer|不可|1、正整数|各scope・固定|定義履歴、internal|保存JSONBを解釈する版|
|`entity_definitions.lifecycle`|状態遷移定義|jsonb object|不可|`{}`|各scope・JSONB|定義履歴、internal|許容状態・遷移の説明|
|`entity_definitions.validation_schema`|全体検証定義|jsonb object|不可|`{}`|各scope・JSONB|定義履歴、internal|項目横断検証。実装範囲は要版管理|

## 4. 項目定義テーブル

|物理名|論理名|型・桁|NULL|キー・初期値|区分|履歴・機密|AI向け意味／入力・表示／例|
|---|---|---|---|---|---|---|---|
|`field_definition_id`|項目定義ID|uuid|不可|PK、自動採番|共通・固定|定義履歴、internal|定義行の不変ID|
|`entity_definition_id`|親定義ID|uuid|不可|FK、親内でfield_code UNIQUE|各scope・固定|定義履歴、internal|どのrecord/transactionの項目か|
|`field_code`|物理名|varchar(80)|不可|小文字snake_case|各scope・固定|定義履歴、internal|JSONキー／APIキー。`manufacturer_part_no`|
|`field_name`|論理名|varchar(200)|不可|-|各scope・固定|定義履歴、internal|画面ラベル|
|`description`|業務説明|text|可|-|各scope・固定|定義履歴、internal|人が読む意味|
|`data_type`|データ型|value_kind|不可|-|各scope・固定|定義履歴、internal|AIとDB検証が使う型|
|`max_length`|最大桁数|integer|可|正整数|各scope・固定|定義履歴、internal|string/textの最大長|
|`numeric_precision`|数値精度|integer|可|正整数|各scope・固定|定義履歴、internal|decimal総桁数|
|`numeric_scale`|小数桁|integer|可|0以上、precision以下|各scope・固定|定義履歴、internal|decimal小数桁|
|`storage_path`|保存先|varchar(255)|不可|core.* / data.field_code|各scope・固定|定義履歴、internal|固定列かJSONBキーかを機械判定|
|`is_required`|必須|boolean|不可|false|各scope・固定|定義履歴、internal|trueなら欠落/nullを保存拒否|
|`is_multivalued`|複数値|boolean|不可|false|各scope・固定|定義履歴、internal|配列等の複数値か|
|`default_value`|初期値|jsonb|可|型一致CHECK|各scope・JSONB|定義履歴、項目に従う|型を保った初期値|
|`validation_rules`|入力・検証規則|jsonb object|不可|`{}`|各scope・JSONB|定義履歴、internal|enum/pattern/minimum/maximum等|
|`display_rules`|表示規則|jsonb object|不可|`{}`|各scope・JSONB|定義履歴、internal|control/label/width/section等|
|`semantic_tags`|意味タグ|text[]|不可|`{}`|各scope・固定|定義履歴、internal|AI検索・類似判定用|
|`ai_description`|AI向け説明|text|可|-|各scope・固定|定義履歴、internal|値の意味、誤解しやすい点、用途|
|`sensitivity`|機密区分|varchar(30)|不可|internal、CHECK|各scope・固定|定義履歴|出力・ログ・権限判断の入力|
|`promotion_state`|格納区分|varchar(30)|不可|extension、CHECK|各scope・固定|定義履歴、internal|fixed/extension/candidate|
|`is_history_tracked`|履歴対象|boolean|不可|true|各scope・固定|定義履歴、internal|変更差分へ含める意図|
|`example_value`|使用例|jsonb|可|型一致CHECK|各scope・JSONB|定義履歴、項目に従う|AIプロンプト・UI例|
|`sort_order`|表示順|integer|不可|0|各scope・固定|定義履歴、internal|標準フォーム順序|

## 5. 業務固定列

|テーブル.物理名|論理名|型・桁|NULL|キー・初期値|区分|履歴・機密|AI向け意味／入力・表示／例|
|---|---|---|---|---|---|---|---|
|`business_records.entity_definition_id`|レコード定義|uuid|不可|FK、scope検証|共通・固定|履歴対象、internal|dataの意味と検証定義|
|`business_records.record_no`|内部連番|bigint identity|不可|自動|共通・固定|履歴対象、internal|人向け番号ではない|
|`business_records.business_key`|業務キー|varchar(200)|可|tenant/definition内UNIQUE|共通・固定|履歴対象、internal|外部・人の安定識別子|
|`business_records.record_status`|状態|record_status|不可|draft|共通・固定|履歴対象、internal|削除の代わりにinactive等を使用|
|`business_records.schema_version`|保存スキーマ版|integer|不可|1|共通・固定|履歴対象、internal|dataを保存した時点の定義版|
|`business_records.effective_from/to`|有効期間|timestamptz|可|to>=from CHECK|共通・固定|履歴対象、internal|マスターの業務有効期間|
|`business_records.data`|拡張値|jsonb object|不可|`{}`、定義検証|各scope・JSONB|全体履歴、項目別機密|有効field定義のキーだけ許可|
|`business_records.source_ref`|出典|jsonb object|不可|`{}`|共通・JSONB|履歴対象、confidential|取込元、原文、外部ID|
|`record_relations.from_record_id/to_record_id`|関係元／先|uuid|不可|同一tenant複合FK|共通・固定|履歴対象、internal|マスター間の方向付き関係|
|`record_relations.relation_type`|関係種別|varchar(80)|不可|組合せUNIQUE|共通・固定|履歴対象、internal|`purchases_item` 等|
|`record_relations.attributes`|関係属性|jsonb object|不可|`{}`|各scope・JSONB|全体履歴、internal|関係自体の条件|
|`record_relations.valid_from/to`|関係有効期間|timestamptz|可|to>=from CHECK|共通・固定|履歴対象、internal|契約・所属等の期間|
|`business_transactions.module_id`|取引モジュール|uuid|不可|FK modules|共通・固定|履歴対象、internal|取引領域|
|`business_transactions.transaction_definition_id`|取引定義|uuid|不可|FK、scope/kind検証|共通・固定|履歴対象、internal|transaction dataの有効定義|
|`business_transactions.transaction_no`|内部取引連番|bigint identity|不可|自動|共通・固定|履歴対象、internal|内部順序。伝票番号ではない|
|`business_transactions.transaction_type`|取引種別|varchar(80)|不可|定義code一致|共通・固定|履歴対象、internal|`business_event` 等|
|`business_transactions.business_date`|業務日|date|不可|current_date|共通・固定|履歴対象、internal|締め・集計日|
|`business_transactions.occurred_at`|発生日時|timestamptz|不可|now()|共通・固定|履歴対象、internal|事実が発生した時刻|
|`business_transactions.transaction_status`|取引状態|enum|不可|draft|共通・固定|履歴対象、internal|posted/completed/cancelled/corrected|
|`business_transactions.subject_record_id`|主対象|uuid|可|同一tenant複合FK|共通・固定|履歴対象、internal|顧客、品目、設備等の中心対象|
|`business_transactions.parent_transaction_id`|親取引|uuid|可|同一tenant複合FK|共通・固定|履歴対象、internal|派生・子取引の親|
|`business_transactions.supersedes_transaction_id`|訂正元取引|uuid|可|同一tenant複合FK|共通・固定|履歴対象、internal|この取引が置き換える元事実|
|`business_transactions.external_key`|外部取引キー|varchar(200)|可|tenant/module内UNIQUE|共通・固定|履歴対象、confidential|外部伝票との冪等キー|
|`business_transactions.currency_code`|通貨|char(3)|可|大文字3文字CHECK|共通・固定|履歴対象、internal|ISO 4217想定。`JPY`|
|`business_transactions.amount`|金額|numeric(20,4)|可|-|共通・固定|履歴対象、confidential|共通集計額|
|`business_transactions.cancellation_reason`|取消理由|text|取消時必須|status連動CHECK|共通・固定|履歴対象、confidential|物理削除せず理由を説明|
|`business_transactions.data`|取引拡張値|jsonb object|不可|`{}`、定義検証|各scope・JSONB|全体履歴、項目別機密|有効なtransaction項目のみ|
|`business_transactions.source_ref`|取引出典|jsonb object|不可|`{}`|共通・JSONB|履歴対象、confidential|受信API、原票等|
|`transaction_lines.transaction_id`|親取引|uuid|不可|同一tenant複合FK|共通・固定|履歴対象、internal|明細のヘッダ|
|`transaction_lines.line_no`|行番号|integer|不可|正整数、取引内UNIQUE|共通・固定|履歴対象、internal|表示・照合順|
|`transaction_lines.line_type`|明細種別|varchar(80)|不可|-|共通・固定|履歴対象、internal|item、fee、work等|
|`transaction_lines.related_record_id`|関連マスター|uuid|可|同一tenant複合FK|共通・固定|履歴対象、internal|品目・材料・設備等|
|`transaction_lines.quantity`|数量|numeric(20,6)|可|-|共通・固定|履歴対象、internal|符号を含む数量|
|`transaction_lines.unit_code`|単位|varchar(30)|可|-|共通・固定|履歴対象、internal|`pcs`、`kg`|
|`transaction_lines.unit_price`|単価|numeric(20,6)|可|-|共通・固定|履歴対象、confidential|単位当たり価格|
|`transaction_lines.line_amount`|明細金額|numeric(20,4)|可|-|共通・固定|履歴対象、confidential|端数処理後の金額|
|`transaction_lines.data`|明細拡張値|jsonb object|不可|`{}`|将来拡張|全体履歴、internal|現版は空を使用。定義モデルは未決|

## 6. ラッパー・監査固定列

|テーブル.物理名|論理名|型・桁|NULL|キー・初期値|区分|履歴・機密|AI向け意味／入力・表示／例|
|---|---|---|---|---|---|---|---|
|`wrapper_definitions.scope/tenant_id/industry_code`|適用範囲|enum/uuid/varchar|scope依存|相互CHECK|各scope・固定|定義履歴、internal|共通→業種→企業の優先順位|
|`wrapper_definitions.wrapper_code`|ラッパーコード|varchar(80)|不可|scope/type/version内UNIQUE|各scope・固定|定義履歴、internal|画面/API/workflow/report/agentの不変名|
|`wrapper_definitions.wrapper_name`|ラッパー名|varchar(200)|不可|-|各scope・固定|定義履歴、internal|利用者向け名称|
|`wrapper_definitions.wrapper_type`|ラッパー種別|varchar(30)|不可|CHECK|各scope・固定|定義履歴、internal|screen/workflow/api/report/agent|
|`wrapper_definitions.definition`|ラッパー定義|jsonb object|不可|-|各scope・JSONB|定義履歴、confidential|UI・API・AIの差分定義|
|`wrapper_definitions.version`|版|integer|不可|1、正整数|各scope・固定|定義履歴、internal|同一ラッパーの公開版|
|`change_events.event_id`|履歴連番|bigint identity|不可|PK|共通・固定|監査、restricted|監査順序|
|`change_events.aggregate_type/id`|対象種別／ID|varchar(80)/uuid|不可|-|共通・固定|監査、restricted|変更対象の表と行|
|`change_events.event_type`|操作|varchar(80)|不可|-|共通・固定|監査、restricted|insert/update|
|`change_events.row_version`|対象版|integer|可|-|共通・固定|監査、restricted|更新後version|
|`change_events.before_data/after_data`|変更前／後|jsonb|可|-|共通・JSONB|監査、restricted|完全な前後像。一般画面へ非表示|
|`change_events.changed_fields`|変更項目|text[]|不可|`{}`|共通・固定|監査、restricted|差分のトップレベル列名|
|`change_events.reason`|変更理由|text|可|session setting|共通・固定|監査、confidential|業務理由|
|`change_events.correlation_id`|相関ID|uuid|可|索引|共通・固定|監査、internal|1リクエストの変更を束ねる|
|`change_events.actor_id`|操作主体|uuid|可|FK actors|共通・固定|監査、confidential|変更を実行した人・AI・service|
|`change_events.occurred_at`|変更日時|timestamptz|不可|now()|共通・固定|監査、restricted|DBで変更を記録した時刻|

## 7. 登録済みJSONB項目

|対象・scope|物理名／論理名|型・桁／NULL|格納・履歴・機密|AI向け意味|入力・表示・使用例|
|---|---|---|---|---|---|
|party・共通|`name`／名称|string(200)／不可|candidate、履歴、internal|対象の基本名称|text、`東都商事株式会社`|
|party・共通|`roles`／役割|json／不可|extension、履歴、internal|customer/supplier等の役割|multiselect、`["customer"]`|
|party・共通|`contact`／連絡先|json／可|extension、履歴、personal|電話・メール等の個人情報|contact section、`{"email":"..."}`|
|item・共通|`name`／品目名|string(200)／不可|candidate、履歴、internal|品目識別名|text、`高耐熱ボルト`|
|item・共通|`item_type`／品目区分|string(30)／不可|candidate、履歴、internal|product/material/service/asset|select、enum|
|item・共通|`base_unit`／基本単位|string(30)／可|candidate、履歴、internal|数量解釈の単位|text、`pcs`|
|transaction・共通|`reference_no`／参照番号|string(100)／不可|candidate、履歴、internal|伝票照合番号|text、`SO-2026-001`|
|transaction・共通|`note`／摘要|text(1000)／可|extension、履歴、internal|取引背景。事実と推測を区別|textarea、`定期受注`|
|item・商社|`manufacturer_part_no`／メーカー型番|string(100)／不可|extension、履歴、internal|メーカー型番。自社SKUではない|`^[A-Z0-9-]+$`、`HTB-M10-50`|
|item・製造業|`material_grade`／材質規格|string(80)／不可|extension、履歴、internal|製造・品質条件の材質規格|text、`SUS304`|
|item・A社|`tenant_sku`／自社SKU|string(50)／不可|extension、履歴、internal|A社内品目コード|`^A-[0-9]{4}$`、`A-1001`|
|item・B社|`inspection_code`／検査区分|string(30)／不可|extension、履歴、confidential|B社の検査フロー選択|enum standard/strict|

上記の実体は `002_seed.sql` と `003_test_data.sql` にあり、最新の有効定義は `effective_field_definitions` で取得します。
