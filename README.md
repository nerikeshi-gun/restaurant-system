# 小規模飲食店向け共有注文システム

Windows PCを店内サーバーにし、同じLANまたはテザリング内の店員スマートフォン、卓上Androidタブレット、厨房ブラウザで同じ注文を共有するFastAPI + SQLiteのMVPです。

## 重要な障害記録

- [2026-08-24 タブレット・PC接続障害](docs/incident-2026-08-24-tablet-pc-connectivity.md)

## MVPで確認できること

- 店員用画面でテーブルを選択
- 店員とお客様が、同じテーブルの同じ未確定注文をリアルタイム共有
- メニューボタンまたは音声認識結果から注文候補を追加
- 数量、サイズ、大盛りなどをボタンで調整
- 入力者区分（店員／お客様）、入力言語、原文、入力時刻を明細へ保存
- 古い画面からの上書きをバージョン番号で拒否
- タッチボタンを押したときだけ注文を確定
- 確定注文を厨房へ受付順で表示
- 表示用注文番号、テーブル、数量、調整、備考、追加注文、入力時刻を表示
- 厨房で「未着手→調理中→提供済み」または取消へ変更
- 厨房状態を店員・卓上画面へリアルタイム反映
- 売り切れ状態を全端末へリアルタイム反映
- お冷、音声・文字による問い合わせ、会計依頼
- 確定済み明細だけを使った会計候補計算
- 厨房から文字またはWindows音声入力（`Win + H`）で返答
- APIキーなしで動くルールベース注文解析
- 店舗・注文時刻に対応する有効メニューバージョンを使ったAI候補生成
- 現在メニュー全件をJSONでAIへ渡す方式（RAG・ベクトル検索・事前絞込みなし）
- 候補が一件でも人が商品ボタンを押す確認フロー
- CSVによる店舗メニューのバージョン更新
- 店名・基調色・注文画面の箱の並びを管理画面から変更
- 多言語入力時の原文／日本語確認欄
- 将来のPOS連携用JSONモックアダプター

AIや音声認識の結果は`tr_record`相当の確定データへ自動登録しません。商品、販売状態、数量、オプション、価格はサーバー側の通常プログラムが再検証し、人が「注文を確定して厨房へ」を押した明細だけを確定します。

設計原則は[業務基盤の設計思想とテーブル構成](docs/core-data-architecture.md)を参照してください。共通基盤DBとの統合案は[core_record統合設計（案）](docs/core-record-integrated-design.md)です。
今回追加したAI候補解析の詳細は[AI注文候補解析仕様](docs/ai-order-resolution.md)を参照してください。

## Windowsでのセットアップ

PowerShellでこのフォルダーを開きます。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

OpenAI APIキーは任意です。未設定でもルールベース解析で動きます。利用する場合だけ`.env`の`OPENAI_API_KEY`へ設定してください。キーはブラウザへ送りません。

```text
OPENAI_API_KEY=ここへPC上で設定
OPENAI_MODEL=gpt-5-mini
OPENAI_FALLBACK_MODEL=gpt-5-nano
LLM_TIMEOUT_SECONDS=8
LLM_MAX_RETRIES=1
LLM_PROVIDER=openai
STORE_MONTHLY_AI_LIMIT=10000
LLM_ENABLED=true
```

Gemini無料枠を使う場合は、Google AI StudioでAPIキーを作成して次のように切り替えます。

```text
GEMINI_API_KEY=ここへPC上で設定
GEMINI_MODEL=gemini-3.5-flash-lite
LLM_PROVIDER=gemini
LLM_ENABLED=true
```

Gemini接続時は問い合わせ翻訳にGeminiを使用し、APIエラー時は手動確認へ戻ります。

設定後はサーバーを再起動します。`/admin`の「注文解析」が`OpenAI接続`になれば設定が読み込まれています。実際の各解析結果にも使用プロバイダーを記録し、API障害時は注文を止めずローカル解析へ切り替えます。

注文解析は`gpt-5-mini → gpt-5-nano → ローカルルール`の順で切り替わります。各外部モデルは8秒で打ち切り、結果を返さない場合は次へ進みます。モデル名は`.env`だけで変更できます。将来Gemini Flashなどを使う場合も、`Interpreter`実装を一つ追加して同じチェーンへ挿入します。

新しい注文候補APIは次です。ブラウザは店舗ID、認識文字列、入力言語だけを送り、APIキーとメニュー全件は送信しません。

```text
POST /api/ai/resolve-order
```

```json
{
  "store_id": "STORE001",
  "recognized_text": "実験定食を一つ",
  "input_language": "ja"
}
```

サーバーは注文時刻に有効な最新メニューバージョンを取得し、売り切れを含む全商品をAIへ渡します。AIが返した外部メニューIDはサーバーで再検証し、存在しないID、無効なID、売り切れ商品を候補から除外します。価格・商品名・オプション料金はAI出力を使わず、現在の店舗DBから取得します。

起動します。

```powershell
.\start.ps1
```

`\.venv\Scripts\python.exe が認識されない`場合は、仮想環境がまだないため、最初の`py -3.12 -m venv .venv`から実行してください。

## 画面URL

Windows PC自身では次を開きます。

- 入口：`http://localhost:8000/`
- 店員用テーブル選択：`http://localhost:8000/staff`
- 店員用1番テーブル：`http://localhost:8000/staff/table/1`（店員用ハンディ画面。商品選択と注文確認を下部タブで切り替え）
- 卓上用1番テーブル：`http://localhost:8000/table/1`
- 厨房：`http://localhost:8000/kitchen`
- カテゴリ・メニュー・売り切れ管理：`http://localhost:8000/admin`
- メニュー新規登録：`http://localhost:8000/admin/menu/new`
- オプション設定：`http://localhost:8000/admin/options`
- 店舗名・注文画面デザイン設定：`http://localhost:8000/admin/store`
- API仕様：`http://localhost:8000/docs`

Android端末では`localhost`ではなく、Windows PCのIPv4アドレスを使います。

```text
http://192.168.1.20:8000/table/1
```

PCのアドレスはPowerShellの`ipconfig`で確認できます。Windows Defender Firewallの確認が出た場合は、プライベートネットワークだけ許可してください。

## テストデータ

初回起動時にSQLiteへ次を登録します。

- テーブル：1番～10番
- ドリンク：キリン、アサヒ、サントリーの生ビール
- 料理：枝豆、唐揚げ、ライス、Aランチ、アジフライ定食、カレーライス
- 調整：ビールサイズ、普通盛り／大盛り

既存の`data/restaurant.db`は削除せず、起動時にMVP用の追加列と不足メニューだけを補います。

## 店舗メニューCSV

`/admin`から、Excel版とCSV版のひな形・現在メニューをダウンロードできます。通常の店舗作業ではExcel版を使用します。Excelの`選択肢グループ1～5`は、店舗で登録済みの「辛さ」「盛り」「ビールサイズ」などをプルダウンから選択できます。編集した`.xlsx`をそのまま取り込めます。CSVは既存システムや自動処理との連携・従来運用との互換用で、管理画面では折りたたんでいます。店舗ID、メニューバージョン、有効開始日時はサーバーが自動設定します。

```text
menu_id,name_ja,price,category,category_order,available,alias,reading,short_name,display_order,size,set_contents,toppings,localized_names
```

`available`は販売中なら`1`、売り切れなら`0`です。`alias`は`|`区切りで複数指定できます。従来の詳細形式も互換対応しており、任意列として`store_id,store_name,menu_version,valid_from,valid_to,category_order,name,short_name,reading,aliases,display_order,size,set_contents,toppings,sold_out,localized_names`を指定できます。管理画面からの新規登録・編集でも新しいメニューバージョンを作成します。既存注文明細には注文時点の商品名、価格、メニューバージョン、AI候補、人が選択した候補がスナップショットとして残ります。

`toppings`は`辛さ,大,中,小`のように「グループ名、選択肢…」の順で入力します。複数グループを設定するときだけ、`辛さ,大,中,小 / ご飯量,大盛,普通,小盛`のように` / `で区切ります。Excelで保存すると、セル内のカンマは自動的にCSV用の引用符で囲まれます。

## 店舗名・注文画面デザイン

`/admin/store`で店名、ボタンの基調色、注文画面にある「注文入力」「メニューから選ぶ」「店内サービス」の箱の順番を変更できます。PC表示とタブレット表示を切り替え、それぞれ別の並びを保存できます。箱はドラッグ操作のほか、タブレットでも使える上下ボタンで並べ替えられます。「このテーブルの注文」は右側・上・下から配置を選べます。設定は店内DBへ保存し、開いている注文画面へリアルタイムに反映します。

端末の幅が変わっても操作不能にならないよう、任意の座標へ置く方式ではなく、箱の順序と注文欄の位置を選ぶ方式にしています。

## オプション

カテゴリとオプションは同じ`menu_categories`テーブルで管理し、`is_menu_category`と`is_option_group`の用途フラグで区別します。`/admin/options`で「辛さ」「ごはん量」「トッピング」などを登録します。オプションごとに、1つだけ選ぶか複数選べるか、必須か、標準の選択肢、追加料金、表示順、販売状態を設定できます。

作成したオプションはメニュー登録・編集画面で商品へ割り当てます。注文画面では商品を選んだ直後に大きな選択ボタンが表示され、必須項目を人が選ぶまで「注文へ追加」は押せません。必須オプションは標準値が登録されていても自動選択しません。価格と追加料金はLLMではなく、サーバーが現在の店舗DBを再検証して計算します。後から設定を変更しても、確定済みの注文明細には注文時点の商品名・価格・選択肢が残ります。

オプションと選択ボタンは管理画面から削除できます。ただし、メニューで使用中のオプションや注文履歴に記録済みの選択ボタンは履歴保護のため削除せず、「使用する」を外して非表示にします。

## 音声入力

注文画面の「音声注文」はブラウザ標準のWeb Speech APIを使います。一度押すと録音を開始し、「確認」やメニューなど別のボタンを押すと終了します。画面下部の「音声注文」は注文入力欄へ戻ってから同じ録音を開始します。認識結果は文字欄へ入り、必ず候補確認と確定ボタンを経由します。

ブラウザが音声認識へ対応していない場合や、LAN内HTTPでマイク権限が制限される場合も、文字入力およびAndroidキーボードのマイク入力を利用できます。本番でアプリ内マイクを確実に使う場合は、ローカルHTTPSまたはAndroidラッパーを導入します。

### Androidでアプリ内マイクを使う

AndroidでChromeのマイク権限を許可しても、`http://192.168.x.x:8000`は安全な接続ではないため、ブラウザ側でマイクを拒否します。PCのIPv4アドレスが`192.168.1.20`の場合は、最初に次を実行します。

```powershell
.\setup-https.ps1 -IpAddress 192.168.1.20
```

その後、次の順で一度だけAndroidへ店舗LAN用CA証明書を登録します。

1. PCで`.\start.ps1`を実行する
2. Android Chromeで`http://192.168.1.20:8000/setup/local-ca`を開き、証明書をダウンロードする
3. Androidの「設定→セキュリティ→暗号化と認証情報→証明書のインストール→CA証明書」から登録する（端末により名称は異なる）
4. HTTPサーバーを停止する
5. PCで`.\start-https.ps1`を実行する
6. Android Chromeで`https://192.168.1.20:8443/table/1`を開く

厨房PC自身でもHTTPSを警告なしで利用するため、現在のWindowsユーザーへ同じCA証明書を登録します。管理者権限は不要です。

```powershell
.\install-pc-ca.ps1
```

登録後はChromeをすべて閉じて開き直し、PCも証明書のIPと一致する`https://192.168.1.20:8443/`を利用します。CAを削除する場合は`.\uninstall-pc-ca.ps1`を実行します。

PCのIPアドレスが変わった場合は、新しいIPを指定して`setup-https.ps1`を再実行します。CA秘密鍵はプロジェクトやOneDrive内ではなく、Windowsユーザーの`LOCALAPPDATA`へ保存します。

入力例：

- `Aランチを一つ、アジフライ定食を二つ`
- `生ビールを一つ`（ブランド候補を表示）
- `カレーを一つ、大盛り`
- `唐揚げを取り消し`
- `唐揚げを二つから一つに変更`

## 多言語とPOSの接続口

入力言語が日本語以外の場合は、原文と確認用日本語欄を併記します。外部翻訳API未設定時は人が日本語を確認・修正します。翻訳アダプターは`app/services/translation.py`、注文解析アダプターは`app/services/interpreter.py`です。

POS連携は`app/services/pos.py`へ分離しています。現在は外部送信せず、次のAPIで確定注文のJSONプレビューを取得できます。

```text
GET /api/v1/shared-orders/{order_id}/pos-export
```

## テスト

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

共有注文の同時WebSocket配信、店員／お客様の入力者記録、タッチ確定、厨房状態同期、古い注文バージョンの更新拒否に加え、正確な料理名、省略名、音声誤認識、数量、オプション、複数商品、該当なし、売り切れ、AIの不正ID、APIタイムアウト、メニュー更新後の価格保持をテストします。

## MVP後に必要なもの

- 本番用の認証、店員PIN、端末登録
- テーブル利用開始・終了、支払済み、日次締め
- 翻訳名称と原材料・アレルゲンの詳細編集画面
- ローカルHTTPSまたはAndroidラッパー
- 外部STT、翻訳、TTS、LLMアダプターの本番実装
- Loyverse等のPOSアダプターと再送・エラー管理
- SQLiteバックアップ、監査ログ、`tr_record`基盤への確定記録連携
