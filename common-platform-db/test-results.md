# 実行テスト結果

実行日: 2026-09-03（Asia/Tokyo）

## 環境

- OS: Windows
- PostgreSQL: 18.6
- 検証サーバー: インストール済みバイナリから作成した隔離クラスタ
- 接続先: 127.0.0.1:55432
- 最終自動テストDB: `common_platform_verify_script`
- Docker Desktop: 27.4.0、Compose 2.31.0を検出。ただしLinuxエンジンのnamed pipeが存在せず使用不可
- 検証完了後、隔離クラスタは停止。本番Windowsサービス（5432番）は継続稼働

本番Windowsサービスの5432番DBとデータには触れず、隔離クラスタで原本と修正版を検証しました。

## 原本の再現結果

- `001_schema.sql`: 適用成功
- `002_seed.sql`: 適用成功
- 他社actor参照: 誤って成功
- 他社record relation: 誤って成功
- 他社transaction subject: 誤って成功
- 他社固有entity definition: 誤って成功
- 共通／企業別field定義の統合: 失敗
- undefined JSONB field拒否: 失敗
- audit changed_fields: 空
- physical DELETE拒否: 失敗

## 修正版のクリーン再構築

実行コマンド:

```powershell
.\run-tests.ps1 -Mode Local -HostName 127.0.0.1 -Port 55432 `
  -AdminUser postgres -Database common_platform_verify_script
```

生成数:

- テーブル: 12
- VIEW: 2
- 関数: 17
- トリガー: 33（information_schema上のイベント別行数）
- インデックス: 38（PK／UNIQUE付随索引を含む）

検証結果:

|#|テスト|結果|実測概要|
|---:|---|---|---|
|1|オブジェクト生成|PASS|tables=12, views=2, functions=17, triggers=33, indexes=38|
|2|A社の有効項目|PASS|共通＋商社＋A社、製造業／B社項目なし|
|3|項目上書き優先順位|PASS|nameはtenant定義「アルファ商材名」|
|4|B社の有効項目|PASS|共通＋製造業＋B社、商社／A社項目なし|
|5|wrapper優先順位|PASS|A社=tenant、B社=platform|
|6|他社relation拒否|PASS|複合外部キーで拒否|
|7|他社actor拒否|PASS|検証トリガーで拒否|
|8|他社definition拒否|PASS|scope検証で拒否|
|9|未定義JSONB拒否|PASS|保存前検証で拒否|
|10|JSONB型不一致拒否|PASS|保存前検証で拒否|
|11|物理DELETE拒否|PASS|削除防止トリガーで拒否|
|12|更新監査before/after|PASS|旧名、新名、changed_fields、reasonを確認|
|13|JSONB検索|PASS|GIN対象の包含検索で1件一致|
|14|取消履歴|PASS|posted→cancelledと理由を監査で確認|
|15|訂正履歴|PASS|元取引を保持しrevisionがsupersedes参照|
|16|RLS他社非表示|PASS|A社contextでB社0件、A社対象1件|
|17|制約生成|PASS|FK／CHECKを確認|

最終結果: **17/17 PASS**。`004_verify.sql` 最終assertも成功し、終了コード0を確認しました。

## core_record 追加分（005〜007）

実行日: 2026-10-19（Asia/Tokyo）

### 環境

- OS: Windows 11
- PostgreSQL: 18.4（`pixeltable-pgserver` 0.6.0 の同梱バイナリを一時ディレクトリへ展開し、127.0.0.1:55433 の隔離クラスタで起動）
- 本番相当のDBや既存サービスには触れていない
- 同梱ビルドに `pgcrypto` 拡張がないため、001 の `CREATE EXTENSION pgcrypto` 行だけを除いたコピーで適用した。005 のハッシュは PostgreSQL 組み込みの `sha256()` を使うため `pgcrypto` に依存しない。通常のPostgreSQLでは 001 をそのまま適用できる。

### 手順と結果

1. 001, 002, 003, 004 を適用：`004` の17項目すべて合格（005 適用前のため `tables=12`）。
2. 005, 006 を適用：エラーなし。
3. 007 を実行：**29/29 合格**。内訳は、採番とハッシュ連鎖、候補の承認済み化、店舗ごとのチェーン、UPDATE / DELETE / TRUNCATE の拒否、AIが確定者になれないこと、来店客が入金を確定できないこと、他社参照の拒否、種別違いの参照の拒否、未定義キー・必須欠落の拒否、反対記録の二重化拒否、拒否された試行で欠番が出ないこと、内容改ざんと末尾削除の検出、監査ログの追記専用、RLS、セッションのタイムゾーン・日付形式に依存しないこと。
4. 同時書込み：8セッションが同じ店舗へ各40件（計320件）を並行してINSERT。連番は320件すべて一意で、`verify_core_chain` は `ok`（325件）。

### 未確認

- Docker 経由の `initialize.ps1` / `run-tests.ps1` からの実行（ファイル順の変更を含む）
- 大量データ時の性能（`core_record` が数百万行になった場合のチェーン直列化の影響を含む）
