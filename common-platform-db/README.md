# 生成AI時代の共通業務基盤DB

PostgreSQL 15以降を対象に、業種別・企業別ラッパーを重ねて展開するための共通データ基盤です。完成済みのCRM/ERP機能を固定化せず、識別、関係、履歴、項目定義、拡張規則だけを共通化します。

## 設計原則

- 顧客、仕入先、商品、材料、設備等は、役割や定義を伴う `business_records` として保持する。
- 受発注、入出荷、製造、作業、問い合わせ等の事実は `business_transactions` と `transaction_lines` に保持する。
- 業種・企業固有値は `data jsonb` に置くが、登録前に有効な `field_definitions` が存在し、型・必須・列挙・範囲・形式規則を満たすことをDBトリガーで検証する。
- 定義は `platform → industry → tenant` の優先順位で項目単位に解決する。
- 検索、結合、集計、制約、監査に必要な値は固定列にする。
- 更新は `change_events` に前後値・変更項目・理由・操作者を記録する。
- 業務レコード、関係、取引、明細の物理削除は禁止し、状態変更または訂正取引で表現する。
- 複合外部キー、検証トリガー、RLSの三層でテナント混入を防ぐ。

## 成果物

|ファイル|内容|
|---|---|
|`001_schema.sql`|型、12テーブル、2 VIEW、17関数、トリガー、索引、RLS、アプリ用グループロール|
|`002_seed.sql`|業種、共通モジュール、共通レコード／取引定義、共通項目定義|
|`003_test_data.sql`|2社、業種別・企業別定義、マスター、関係、取引、明細、取消・訂正データ|
|`004_verify.sql`|テナント分離、定義優先順位、JSONB検証、監査、検索、取消・訂正の自動検証|
|`initialize.ps1`|Docker／ローカルPostgreSQL共通の構築スクリプト|
|`run-tests.ps1`|クリーンな検証DBを再作成して全SQLを実行|
|`docker-compose.yml`|Docker用PostgreSQL 16。ホスト側は既定で55432番|
|`field-definition.md`|固定列・JSONB項目の項目定義書|
|`ER-STRUCTURE.md`|ER構造と定義解決、履歴、テナント境界の説明|
|`WINDOWS-SETUP.md`|Windowsでの構築手順|
|`OPERATIONS.md`|停止、再起動、バックアップ、復元手順|
|`005_core_record.sql`|core_record 統合設計の基盤（確定ジャーナル、未確定候補、ハッシュチェーン、監査ログ）|
|`006_restaurant_seed.sql`|飲食業の定義（場所・商品・来店セッション・注文などの活動）|
|`007_core_record_verify.sql`|core_record の自動検証（29項目）|
|`design-review.md`|原本の問題、修正内容、未決事項|
|`test-results.md`|実際に実行した環境・コマンド・検証結果|

## 最短の構築

Docker DesktopのLinuxエンジンが利用可能な場合:

```powershell
Copy-Item .env.example .env
# .env の COMMON_PLATFORM_PASSWORD を安全な値へ変更する
.\initialize.ps1 -Mode Docker
```

ローカルPostgreSQLを使う場合:

```powershell
.\initialize.ps1 -Mode Local -Database common_platform -HostName 127.0.0.1 -Port 5432 -AdminUser postgres
```

テストは業務DBと分離したDB名で実行します。

```powershell
.\run-tests.ps1 -Mode Local -Database common_platform_verify
```

`-Rebuild` は対象DBまたはDocker内の `platform` スキーマを削除して作り直します。対象名を確認した場合だけ指定してください。

## AIエージェントが使う入口

AIへ生テーブルの推測結果を渡さず、対象テナントに有効な定義だけを取得します。

```sql
SELECT *
FROM platform.effective_field_definitions(
  'catalog', 'record', 'item', :tenant_id
)
ORDER BY sort_order, field_code;
```

アプリ接続ではトランザクション開始直後に `SET LOCAL app.tenant_id = '<tenant uuid>'` を設定し、DBログインロールを `platform_app` のメンバーにします。認証済み利用者とテナントIDの結び付けは必ずAPI層で検証してください。
