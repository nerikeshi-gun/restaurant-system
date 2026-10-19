# 設計レビューと修正記録

## 原本の実行結果

原本の `001_schema.sql` と `002_seed.sql` はPostgreSQL 18.6へ文法エラーなく適用できました。しかし、実データを用いた否定テストで次の問題を再現しました。

|問題|原本での結果|修正|
|---|---|---|
|他社actorを `created_by` に設定|成功してしまう|actor所属テナント検証トリガー|
|A社のrelationからB社recordを参照|成功してしまう|`(tenant_id, record_id)` 複合外部キー|
|A社transactionからB社recordを参照|成功してしまう|取引対象の複合外部キー|
|A社固有entity definitionをB社recordで使用|成功してしまう|定義scope適用検証|
|共通entity IDから企業別fieldを解決|取得できない|module/kind/entity code横断の優先順位解決|
|企業別entity IDから共通fieldを解決|取得できない|同上|
|未定義JSONBキー|登録できる|有効項目定義との照合トリガー|
|JSONBの型・必須・列挙等|DBで未検証|型、長さ、enum、pattern、min/max検証|
|更新監査の `changed_fields`|常に空|before/after差分を算出|
|業務レコードの物理削除|成功してしまう|DELETE禁止トリガーとDELETE権限非付与|
|取引の更新時刻・version|更新されない|`updated_at` と `version_no` の自動更新|
|nullable business/external key|NULLが1件しか登録できない|通常のUNIQUEへ変更しNULL複数を許可|
|transaction JSONBの意味|定義への参照がない|`transaction_definition_id` と定義種別を追加|
|業種コード|自由文字列|`industries` を追加し外部キー化|
|Composeの5432番|ローカルPostgreSQLと衝突|ホスト既定ポートを55432へ変更|
|Composeの平文パスワード|YAMLへ固定値|環境変数必須化、`.env.example` のみ提供|

## テナント境界

データ参照時のRLSに加え、参照関係そのものを複合外部キーで同一テナントへ制限しました。RLSを迂回できるDB所有者が誤操作しても、record relation、transaction subject、parent/supersedes transaction、transaction lineの他社参照は成立しません。actorと定義scopeはトリガーで同様に検証します。

RLSは `app.tenant_id` を使用します。これはSQL利用者自身が任意に設定できるため、単独では認証境界になりません。API層で認証済みprincipalとtenantを照合し、一般利用者へ直接SQL接続を許可しないことが前提です。

## JSONBの扱い

`promotion_state=fixed` は `core.*`、`extension/candidate` は `data.<field_code>` に限定しました。レコード／取引の保存時に、有効定義に存在しないキーを拒否します。JSONBを自由領域として使う場合も、先に項目定義の承認・登録が必要です。

## 未決事項と次に設計すべき論点

1. 認証基盤のprincipalとtenantの確実な結合方法。JWT claim、接続プール、DBロールの責任分界を決める。
2. `field_definitions` 変更の承認ワークフローと、定義そのものの版管理・公開日時・ロールバック。
3. スキーマバージョン更新時の既存JSONBデータ移行、後方互換、再検証ジョブ。
4. 金額の税・端数・複数通貨・為替レート。現在のamountは共通集計軸だけを定義。
5. 単位変換と数量精度。`unit_code` の標準辞書・換算ルールは未定義。
6. posted済み取引の取消を状態変更だけで許すか、必ず反対取引を作るか。会計・在庫領域では反対取引を推奨。
7. `transaction_lines.data` の拡張定義モデル。現版では空オブジェクトを使用し、明細固有JSONBの本格利用は次版で定義を追加する。
8. 個人情報・機密情報の列／キー単位マスキング、暗号化、保持期限、削除要求への対応。
9. 監査ログの改ざん耐性。別ストレージ転送、署名、WORM保管、管理者操作監査を検討する。
10. 大量データ時のtenant/dateパーティショニング、アーカイブ、GIN索引コストの実測。
11. wrapper定義のJSON Schema、互換性、署名、デプロイ単位。
12. 業種コード体系と、1社が複数業種を持つ場合のモデル。
