# core_record 統合設計（案）

## 1. この文書の位置付け

次の3つを、`core_record` を軸に一つの設計へ統合する案である。

| 系統 | 文書 | 持っているもの |
|---|---|---|
| 介護Excel（原典） | `基本テーブル設計書1017_consistent_v2.xlsx` | `care_records_tmp` → `care_records` → `corrections`、ハッシュチェーン、UI差分パッチ、選択肢辞書 |
| 飲食への一般化 | [core-data-architecture.md](core-data-architecture.md) | `tr_record_tmp` → `tr_record`、活動種別、投影、AI対話層 |
| 共通基盤DB | [common-platform-db/](../common-platform-db/README.md) | tenant分離（複合FK・RLS）、3段の項目定義、JSONB検証、変更履歴 |

呼び名の整理：`care_records` と `tr_record` は同じ役割（確定済み業務事実の主テーブル）なので、本書では **`core_record`**（未確定は `core_record_tmp`）と呼ぶ。

これは設計案である。主要な論点の決定は「8. 決定事項と残課題」、SQLの準備状況は「9」にある。SQLは書いたが、まだ実行・検証していない。

## 2. 統合方針

1. **業務事実の正本は `core_record` だけ。** AI・音声・OCRの出力は `core_record_tmp` に入れ、人が確認したものだけを `core_record` へ確定する。
2. **確定後は更新しない。** 取消・訂正は反対記録の追加で表し、全記録をハッシュチェーンへ入れる。
3. **境界は `tenant`（法人）だけにする。** 店舗・フロア・席・倉庫は tenant の下の「場所」であり、tenant そのものではない。（`org_master` へ席を直接ぶら下げる旧案の修正。）
4. **マスタは `business_records` に統一する。** 商品・品目・仕入先・場所などは固定テーブルを増やさず、定義（`entity_definitions`）付きのレコードにする。
5. **検索・結合・集計・制約に使う値は固定列にする。** JSONBは、有効な項目定義で検証された拡張項目に限る。
6. **現在状態・集計・帳票・AI回答は `core_record` から投影する。** 状態の正本をマスタや別テーブルに持たない。

## 3. 境界：tenant と場所

```text
tenants（法人）
  └─ business_records  entity = location
        ├─ location_type = store    店舗
        ├─ location_type = floor    フロア・エリア
        ├─ location_type = table    席
        └─ location_type = storage  倉庫・冷蔵庫・厨房
  record_relations  (relation_type = located_in)  で階層を表す
```

- 旧案の `org_master` は `tenants` に置き換える。`org_id` は `tenant_id` と書き換える。
- 席は `table` 種別の場所レコードで、`located_in` で店舗またはフロアに属する。店舗を足してもスキーマ変更は不要。
- 複数店舗の法人でも、tenant は一つのままで、店舗ごとの違いは場所レコードと関係で表す。
- tenant 分離は common-platform-db の方式（複合外部キー＋トリガー＋RLS）をそのまま採用する。

## 4. テーブル一覧

### 4.1 基盤

| テーブル | 役割 | 由来 |
|---|---|---|
| `industries` | 業種コード | common |
| `tenants` | 法人。ロケール、タイムゾーン、設定 | common |
| `actors` | 人・AIエージェント・システム・来店セッション | common（`staff_master` を吸収） |
| `modules` | 機能群（注文、仕入、在庫、勤怠など） | common |

### 4.2 定義

| テーブル | 役割 | 由来 |
|---|---|---|
| `entity_definitions` | レコード種別・取引種別の定義 | common |
| `field_definitions` | 項目定義（型、必須、列挙、範囲、ラベル、入力型、選択肢参照） | common + 原典 `ui_field_master` を統合 |
| `wrapper_definitions` | 業種・企業別のかぶせ定義 | common |
| `code_master` | 活動種別、単位、支払方法などの共通コード | docs（`mst_enum_options` を統合） |
| `canonical_value_dict` | 表記揺れ→正準コード | docs |
| `confidence_policy` | AI候補の表示・警告・確認必須・却下の閾値 | docs |
| `ui_layout` / `ui_layout_detail` | 標準画面レイアウト | 原典 |
| `tenant_ui_policy` / `tenant_ui_binding` / `tenant_ui_patch` | 法人ごとのUI差分 | 原典（`org_ui_*` を改名） |

定義は `platform → industry → tenant` の順で項目単位に上書きする。`code_master` と `canonical_value_dict` も同じ3段にする。

### 4.3 マスタ

| テーブル | 役割 |
|---|---|
| `business_records` | 場所、商品、品目、仕入先、設備、利用者などのマスタ。種別は `entity_definitions` |
| `record_relations` | `located_in`、`consists_of`（商品→品目）、`supplies`、`permits_modifier` などの関係 |

`core_record` が参照する軸（商品・品目・場所・仕入先）は、`(tenant_id, record_id)` の複合外部キーで `business_records` を指す。参照先の種別は検証トリガーで確認する。

### 4.4 業務事実

| テーブル | 役割 |
|---|---|
| `core_record_tmp` | AI・音声・OCR・外部連携・手入力による未確定候補 |
| `core_record` | 確定済みユニバーサルジャーナル（追記専用） |
| `core_record_attachment` | 音声、画像、納品書、領収書 |
| `core_record_source` | サマリーやAI回答が参照した記録集合 |
| `form_report` | 帳票出力内容と出力時ハッシュ（チェーン付き） |

`tr_*_detail`（活動別の詳細テーブル）は**最初は作らない**。活動固有の項目は `core_record.data`（JSONB）に入れ、有効な項目定義で検証する。検索・集計で必要になった項目は、common-platform-db の `promotion_state`（candidate → extension → fixed）に従って固定列へ昇格させる。

`core_document`（伝票ヘッダ）も作らない。伝票は `document_type` / `document_id` / `line_no` で束ね、ヘッダ相当の現在状態はビューで投影する。

### 4.5 監査

| テーブル | 役割 |
|---|---|
| `change_events` | マスタ・関係・定義の変更前後値（common） |
| `audit_log` | 閲覧、ログイン、設定変更、確定操作などの操作監査（docs・原典） |

`core_record` 自体の変更履歴は `change_events` では扱わない。更新を許さず、訂正は追記だからである。

## 5. `core_record` の列

docs 8.2 の `tr_record` を土台に、`org_id` を `tenant_id` にし、場所軸を一本化する。

| 区分 | 列 |
|---|---|
| 識別・順序 | `tenant_id`, `record_id`, `location_id`（店舗または本部。ハッシュチェーンの単位）, `sequence_no`, `activity_id`, `document_type`, `document_id`, `line_no`, `entity_definition_id`, `record_type` |
| 日時・操作者 | `business_date`, `occurred_at`, `recorded_at`, `recorded_by`, `confirmed_at`, `confirmed_by`, `confirmation_method` |
| 分析軸 | `place_id`（席・倉庫など）, `product_id`, `item_id`, `supplier_id`, `session_id`, `cost_center`, `internal_order`, `activity_type` |
| 数量・金額 | `quantity`, `unit_code`, `unit_price`, `amount`, `tax_amount`, `currency_code` |
| 関係・証跡 | `parent_record_id`, `source_record_id`, `reversal_of_record_id`, `source_tmp_id` |
| 内容 | `summary`, `data`（JSONB、定義で検証）, `schema_version` |
| ハッシュ | `canonical_version`, `prev_hash`, `hash`, `hash_algorithm` |

主キーは `(tenant_id, record_id)`。一意制約は `(tenant_id, location_id, sequence_no)`。ハッシュチェーンの先頭は `core_chain_heads` が `(tenant_id, location_id)` ごとに持ち、確定時に行ロックで直列化する。

原典 `care_records` との対応：

| 原典（介護） | 統合後 |
|---|---|
| `id`, `org_id` | `record_id`, `tenant_id` |
| `resident_id` | 軸の一つ（利用者はマスタ）。飲食では `session_id` |
| `recorded_by`, `approved_by` | `recorded_by`, `confirmed_by` |
| `care_type`, `activity_type` | `record_type`, `activity_type` |
| `record_summary` / `extra_info` / `audit_summary` | `summary` / `data` / 必要なら `data` 内の監査用キー |
| `cost_center`, `internal_order`, `item_code` | 同名の軸 |
| `pre_hash`, `hash` | `prev_hash`, `hash` |
| `reserved_01…30` | 作らない。拡張は `data` と `promotion_state` で行う |
| `care_records_corrections` | 作らない。`reversal_of_record_id` による反対記録 |

## 6. 人の確認を DB で守る

「AIの出力を自動確定しない」を運用任せにせず、制約とトリガーにする。

- `core_record.confirmed_by` は NOT NULL とし、参照先 `actors` の `actor_type` が `agent` / `system` / `service` なら拒否する。
- 来店客が卓上で確定する場合に備え、`actor_type` に `guest_session`（来店セッション）を加える。社員マスタ登録は要求しない。
- `confidence_policy` の閾値は、表示・警告・確認要求の制御にだけ使い、確定の根拠にはしない（docs 6.3 を維持）。
- 金額・数量・単価は LLM 出力を採用せず、確定時にマスタから通常プログラムが算出する。
- `core_record` への UPDATE / DELETE は権限を与えず、トリガーでも拒否する。

## 7. 既存SQLiteからの対応

| 現行MVP | 統合後 |
|---|---|
| `stores` | `tenants`（法人）＋ 場所レコード（店舗） |
| `dining_tables`, `table_sessions` | 場所レコード（席）、`session_id`（来店セッション） |
| `menu_items`, `menu_aliases` | `business_records`（商品）＋ 別名は `data` または `canonical_value_dict` |
| `menu_categories`（メニュー用） | `business_records`（商品分類）または `code_master` |
| `menu_categories`（オプション用）, `modifier_groups`, `modifier_options` | 調整分類・調整選択肢のレコード＋ `permits_modifier` 関係。**二重管理を解消** |
| `menu_versions`, `menu_version_items` | `business_records` の `effective_from/to` と `schema_version`。全件コピーは廃止 |
| `orders`, `order_items`, `order_item_modifiers` | `core_record`（`record_type` = 注文・修正・取消）。現在状態はビュー |
| `interpretations`, `ai_resolution_logs` | `core_record_tmp`（候補・信頼度・モデル・プロンプト版） |
| `service_requests`, `messages` | `core_record`（`record_type` = 依頼・応答） |
| `display_number_counters` | 営業日ごとの採番を `core_record` の `data` またはビューで表現 |

`order_items` が持つ「注文時点の商品名・単価・メニュー版のスナップショット」という良い設計は、`core_record.unit_price`、`summary`、`schema_version` に引き継ぐ。

## 8. 決定事項と残課題

docs 16章と common-platform-db の `design-review.md` の未決事項のうち、SQLに落とすために次を決めた。覆す場合は、この表と `005`〜`007` を同時に直す。

| # | 論点 | 決定 | 理由 |
|---|---|---|---|
| 1 | ハッシュチェーンの単位 | **`(tenant_id, location_id)`、つまり店舗ごと。** 本部の記録は本部の場所レコードのチェーンに入れる。 | 全店舗で一本にすると、全店の確定が一つの行ロックで直列になる。店舗内の順序と改ざん検出で足りる。 |
| 2 | マスタの置き場 | **全て `business_records`。** 検索用に `display_name` だけ固定列として追加した。商品・品目の専用テーブル化は、実測で遅いと分かるまで行わない。 | テーブルを増やさず、tenant分離と項目検証を一か所で守れる。 |
| 3 | `data`（JSONB）の範囲 | **活動固有の項目は全て JSONB から始める。** 検索・集計で使うと決まった項目は `promotion_state` に従い固定列へ昇格する。数量・金額・単価・税額・軸は最初から固定列。 | 詳細テーブルを先に作ると、介護Excelの `reserved_01…30` と同じ状態になる。 |
| 4 | 売上認識と在庫消費 | **売上は会計（入金）の確定、在庫消費は調理開始、注文確定は厨房受付。** それぞれ別の `record_type` で追記し、集計はビューが行う。 | 注文の取消・調理前の変更で売上が動かない。調理開始以降は食材が使われたとみなせる。 |
| 5 | 税の端数処理 | **会計の確定時に、税率ごとに一回だけ端数処理する。** 既定は切り捨て。明細の `tax_amount` は按分した参考値で、確定値は会計記録が持つ。方式は tenant の設定で変えられるようにする。 | 請求書の税額は税率ごとの合計に対して一回の端数処理が求められるため。 |
| 6 | `guest_session` の確定 | **注文明細の確定のみ可。** 取消・入金・値引きは、取引定義の `lifecycle.requires_staff_confirmation` で店員に限る。確定方法は `confirmation_method` に必ず記録する。 | 卓上の注文は自然な操作だが、金銭に関わる操作は人の責任を明確にする。 |
| 7 | 実装先 | **新しいデータ層は PostgreSQL。** SQLite には移植しない。現行MVPは、リポジトリ層を介して段階的に切り替え、切替前の注文は開始時の記録として取り込む。 | RLS、JSONB検証、複合外部キーがSQLiteにない。二重実装は保守できない。 |
| 8 | AI対話層の自律度 | **第一段階は候補提示のみ。** 発注・補充などの一次案の自動起案は、`core_record_tmp` に `pending` で置くところまで。確定は常に人。 | `confirmed_by` を人に限るDB制約と整合する。 |

### 残課題

- `display_name` と、プラットフォーム定義の `data.name`（item, party）が重複している。`name` を廃止して `display_name` に一本化するか決める。
- 取消の反対記録で、数量・金額の符号が元記録と逆であることをDBで強制するか、サービス層で守るか。
- `core_record_attachment` / `core_record_source` / `form_report`、`code_master` / `canonical_value_dict` / `confidence_policy`、UI定義（`ui_layout` 系）は未作成。
- `business_transactions` / `transaction_lines` の廃止時期。現行データがなければ移行後に削除する。
- 認証済み利用者と `app.tenant_id` の結び付け（API層）、定義の承認ワークフロー、個人情報のマスキングは `design-review.md` の未決事項を引き継ぐ。

## 9. SQLの準備状況

| ファイル | 内容 | 状態 |
|---|---|---|
| [005_core_record.sql](../common-platform-db/005_core_record.sql) | 既存テーブルの拡張、`core_chain_heads` / `core_record_tmp` / `core_record` / `audit_log`、ハッシュ、検証トリガー、RLS | 実行・検証済み |
| [006_restaurant_seed.sql](../common-platform-db/006_restaurant_seed.sql) | 業種 `restaurant`、場所・商品・来店セッションの定義、注文・厨房状態・取消・入金・依頼・販売可否の活動定義 | 実行・検証済み |
| [007_core_record_verify.sql](../common-platform-db/007_core_record_verify.sql) | 29項目の自動検証（採番、チェーン、改ざん検出、人の確認、tenant分離、追記専用、RLS、セッション設定非依存） | 29/29 合格 |

`initialize.ps1` は、`004_verify.sql` がテーブル数を厳密に検査するため、005〜007を004の後に適用する。実行には PostgreSQL 15 以降が必要。

実行環境と結果は [common-platform-db/test-results.md](../common-platform-db/test-results.md) の「core_record 追加分」を参照。

### マスタ移行（SQLite → 共通基盤DB）

[tools/sqlite_to_platform_sql.py](../tools/sqlite_to_platform_sql.py) が、現行SQLiteのマスタを投入SQLへ変換する。標準ライブラリだけで動き、SQLiteは読み取り専用で開く。

```powershell
.\.venv\Scripts\python.exe tools\sqlite_to_platform_sql.py --db data\restaurant.db --out tmp\migration.sql
psql -v ON_ERROR_STOP=1 -d <db> -f tmp\migration.sql
```

| 移行元 | 移行先 |
|---|---|
| `stores` | `tenants`（法人。既定は店舗IDを小文字にした値）＋ 場所レコード（店舗） |
| `dining_tables` | 場所レコード（席）。`located_in` で店舗に属する。QRトークンも移行する |
| `menu_items`, `menu_aliases` | 商品レコード。別名は `data.aliases`、アーカイブ済みは `archived` |
| `menu_categories`（オプション用） | 調整分類レコード。使われていない `modifier_groups` テーブルは移行しない |
| `modifier_options` | 調整選択肢レコード。`option_of` で分類に属する |
| `menu_item_modifier_groups` | `permits_modifier` 関係（必須・表示順を属性に持つ） |

- 何度適用しても同じ結果になる（`business_key` で upsert し、変更がなければ更新しない）。
- 現行の実データ（店舗1・席10・商品36・調整分類4・選択肢9・関係44）をPostgreSQL 18.4で適用し、件数が一致すること、再適用で版数・変更履歴が増えないことを確認した。
- **税区分は移行元にないため、全商品へ `--default-tax-category`（既定 `standard`）を入れる。** 軽減税率の商品は移行後に直す必要がある。
- 移行しないもの：注文履歴、来店セッション、販売可否（売り切れ）、席の利用状態、店舗の画面設定（基調色・レイアウト）。
- 出力SQLには席のQRトークンが含まれるため、`tmp/` に出力し、リポジトリへコミットしない。

### 実装順序（案）

1. 005〜007 を PostgreSQL で実行し、検証を通す（完了）
2. 場所・商品・調整のマスタ移行スクリプト（SQLite → `business_records`）（完了。品目・仕入先は現行DBにないため対象外）
3. 確定サービス（正規化 → 検証 → 人の確認 → `core_record`）。AI解析は `core_record_tmp` へ
4. 注文状態・厨房一覧・会計をビューへ置き換える
5. 取消・訂正を反対記録へ置き換える
6. 仕入・在庫・仕込みの活動を追加する
7. 会計締めとハッシュ検証画面、帳票・日報・AI質問回答
