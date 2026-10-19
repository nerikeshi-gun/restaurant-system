# Windows構築手順

## 前提

- PostgreSQL 15以降、またはDocker DesktopのLinuxコンテナエンジン
- PowerShell 5.1以降
- 本フォルダをカレントディレクトリにして実行

## 方法A: ローカルPostgreSQL

現在のPCではPostgreSQL 18.6、Windowsサービス `postgresql-x64-18`、5432番ポートの稼働を確認済みです。

```powershell
cd <common-platform-dbの絶対パス>
.\initialize.ps1 -Mode Local -HostName 127.0.0.1 -Port 5432 -AdminUser postgres -Database common_platform
```

インストール時に設定した `postgres` パスワードを求められます。パスワードをスクリプトやGit管理ファイルへ記載しないでください。

既存DBを意図的に作り直す場合のみ:

```powershell
.\initialize.ps1 -Mode Local -Database common_platform -Rebuild
```

`-Rebuild` は指定DBを `dropdb --force` で削除します。バックアップとDB名を確認してから実行します。

## 方法B: Docker Desktop

```powershell
Copy-Item .env.example .env
notepad .env
# COMMON_PLATFORM_PASSWORDを長いランダム値へ変更
.\initialize.ps1 -Mode Docker
```

ホスト側ポートは、ローカルPostgreSQLの5432番との衝突を避けるため既定で55432番です。変更する場合は `.env` の `COMMON_PLATFORM_PORT` を更新します。

Docker Desktopがインストール済みでもLinuxエンジンが起動していなければDocker方式は使えません。`docker info` が成功することを確認します。今回の実行ではDocker Desktop 27.4.0／Compose 2.31.0は存在しましたが、Linuxエンジンのnamed pipeが作成されず利用不能だったため、ローカルPostgreSQLの隔離クラスタで検証しました。

## テスト

本番用DB名と分けて実行します。

```powershell
.\run-tests.ps1 -Mode Local -Database common_platform_verify
```

成功時は17行すべての `passed` が `t` となり、最後に `Common platform database build completed` が表示されます。1件でも失敗すると `004_verify.sql` がエラー終了します。

## アプリ用ロール

DDLはNOLOGINのグループロール `platform_app` を作ります。実アプリ用LOGINロールは環境ごとに作成し、パスワードをシークレット管理へ保存します。

```sql
CREATE ROLE common_platform_api LOGIN PASSWORD '<secret-from-secret-manager>';
GRANT platform_app TO common_platform_api;
```

各リクエストのDBトランザクション開始直後に、認証済みtenantを設定します。

```sql
BEGIN;
SET LOCAL app.tenant_id = '<tenant-uuid>';
-- query / command
COMMIT;
```

クライアントから任意のtenant IDを受け取ってそのまま設定してはいけません。認証principalとの対応をAPI側で確認します。
