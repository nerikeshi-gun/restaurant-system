# 運用手順

## 停止と再起動

### Docker

```powershell
docker compose stop
docker compose start
docker compose restart db
```

`docker compose down` はコンテナとネットワークを削除しますが、名前付きvolumeは残ります。`docker compose down -v` はDBデータを削除するため、再構築を明示的に行う場合以外は実行しません。

### Windowsサービス版PostgreSQL

管理者PowerShellで実行します。

```powershell
Stop-Service postgresql-x64-18
Start-Service postgresql-x64-18
Restart-Service postgresql-x64-18
Get-Service postgresql-x64-18
```

## バックアップ

カスタム形式は圧縮、選択復元、並列復元に対応します。

```powershell
pg_dump -h 127.0.0.1 -p 5432 -U postgres -d common_platform `
  -Fc -f .\backup\common_platform_20260903.dump
```

Dockerの場合:

```powershell
docker compose exec -T db pg_dump -U platform -d common_platform -Fc > .\backup\common_platform_20260903.dump
```

バックアップ後に `pg_restore --list` で読めることを確認し、定期的に別DBへ復元テストを行います。dumpファイルには機密情報が含まれるため、アクセス制御と暗号化を行います。

## 復元

既存DBへ上書きせず、最初は別名DBへ復元して検証します。

```powershell
createdb -h 127.0.0.1 -p 5432 -U postgres common_platform_restore_test
pg_restore -h 127.0.0.1 -p 5432 -U postgres `
  -d common_platform_restore_test --clean --if-exists .\backup\common_platform_20260903.dump
psql -h 127.0.0.1 -p 5432 -U postgres -d common_platform_restore_test `
  -c "SELECT count(*) FROM platform.tenants;"
```

Dockerへ復元する場合はdumpを標準入力で渡します。

```powershell
Get-Content -AsByteStream .\backup\common_platform_20260903.dump |
  docker compose exec -T db pg_restore -U platform -d common_platform --clean --if-exists
```

PowerShell 5.1ではバイナリのパイプ処理を避け、`docker cp` でコンテナへコピーしてから `pg_restore` を実行してください。

## 日常確認

```sql
SELECT now(), current_database(), version();
SELECT tenant_id, count(*) FROM platform.business_records GROUP BY tenant_id;
SELECT tenant_id, count(*) FROM platform.business_transactions GROUP BY tenant_id;
SELECT event_type, count(*) FROM platform.change_events GROUP BY event_type;
SELECT * FROM platform.effective_field_definitions('catalog','record','item', '<tenant-uuid>');
```

## 取消・訂正

- draft等の不要データでも物理DELETEしない。
- マスターは `record_status=inactive/cancelled/archived` とする。
- 取引取消は `transaction_status=cancelled` と `cancellation_reason` を同時に更新する。
- 訂正は元取引を `corrected` にし、新取引の `supersedes_transaction_id` へ元IDを設定する。
- 更新前に `SET LOCAL app.change_reason`、`app.actor_id`、`app.correlation_id` を設定する。

## 障害時の注意

DDL再適用で直そうとせず、まずログとバックアップを確保します。`initialize.ps1 -Rebuild`、volume削除、DB削除は復旧操作ではなく再作成操作です。
