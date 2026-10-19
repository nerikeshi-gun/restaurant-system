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
