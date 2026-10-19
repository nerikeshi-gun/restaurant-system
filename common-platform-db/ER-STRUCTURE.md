# ER構造

## 全体

```text
industries ──< tenants ──< actors
                   │
modules ──< entity_definitions ──< field_definitions
   │               │                    │
   │               │        platform / industry / tenant
   │               │                    │
   │               ├──< business_records ──< record_relations >── business_records
   │               │          │
   └───────────────< business_transactions ──< transaction_lines >── business_records
                              │       │
                              │       └── parent / supersedes transaction
                              └── subject record

modules ──< wrapper_definitions

business_records / record_relations / business_transactions / transaction_lines
                              └──< change_events
```

## 定義レイヤー

`entity_definitions` は `module_id + definition_kind + entity_code` が同じ行を、scopeごとに重ねます。

```text
platform definition
    └─ industry definition（tenant.industry_codeに一致）
          └─ tenant definition（tenant_idに一致）
```

`effective_field_definitions` はfield_codeごとにtenant、industry、platformの順で最初の定義を採用します。企業固有定義が共通定義を丸ごとコピーする必要はありません。`effective_entity_definition` と `effective_wrapper_definitions` も同じ優先順位です。

## 業務マスター相当

`business_records` が顧客、仕入先、商品、材料、設備等を共通保持します。種別は参照するrecord型 `entity_definitions` とJSONB項目で表し、固定テーブルへ分断しません。対象間の関係は `record_relations` で表します。

## 業務上の事実

`business_transactions` がヘッダ、`transaction_lines` が明細です。transaction型定義を必須参照し、取引JSONBも有効な項目定義で検証します。subject、parent、supersedes、line related recordはいずれもtenant_idを含む複合外部キーです。

## 履歴

業務4テーブルのINSERT/UPDATEは `change_events` へbefore/after、changed_fields、row_version、reason、actor、correlation IDを記録します。物理DELETEはDBトリガーで拒否します。取消はstatus変更、訂正は元取引をcorrectedにし、新取引の `supersedes_transaction_id` で元取引を参照します。

## テナント分離

- 複合外部キー: 他社レコードを関係・取引・明細へ混入させない。
- scope検証: 他社固有の定義を使用させない。
- actor検証: 他社actorを作成者・更新者に設定させない。
- RLS: `app.tenant_id` と一致する業務行だけを `platform_app` へ表示する。
- VIEWは `security_invoker=true` とし、呼出者のRLSを維持する。
