import json
import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from difflib import SequenceMatcher

from openai import OpenAI
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AiResolutionLog, MenuVersion, MenuVersionItem, Store
from app.schemas import ResolveOrderRequest, ResolveOrderResponse, ResolvedMenuCandidate, ResolvedOrderItem
from app.services.menu_catalog import load_current_menu_version


logger = logging.getLogger(__name__)

GENERIC_MENU_WORDS = (
    "カレーライス", "カレー", "定食", "セット", "ランチ", "単品",
    "メニュー", "料理", "ごはん", "ご飯", "ライス", "ください", "お願い",
)


def _normalized_menu_text(value: str) -> str:
    return re.sub(r"[\s　・･ー\-_/（）()、，,。]+", "", value.casefold())


def _menu_keyword(value: str) -> str:
    result = _normalized_menu_text(value)
    for generic in GENERIC_MENU_WORDS:
        result = result.replace(_normalized_menu_text(generic), "")
    return result

DEFAULT_PROMPT = """あなたは飲食店の音声注文から候補を抽出する処理です。
注文を確定せず、渡されたmenu_idだけを候補として返してください。価格を回答しないでください。
一度の発話に複数商品があれば商品単位に分け、各商品へ候補を返します。
数量が不明ならnull、追加・変更・取消をoperationへ設定します。
売り切れ情報も考慮しますが、入力メニューにないIDを絶対に生成しないでください。"""


class RawCandidate(BaseModel):
    menu_id: str
    option_candidates: list[str] = []


class RawItem(BaseModel):
    source_phrase: str
    quantity: int | None = Field(default=None, ge=1, le=99)
    operation: str = "add"
    candidates: list[RawCandidate] = []


class RawResolution(BaseModel):
    items: list[RawItem] = []


def menu_payload(version: MenuVersion) -> list[dict]:
    return [
        {
            "menu_id": item.menu_id,
            "name": item.name,
            "category": item.category_name,
            "reading": item.reading,
            "aliases": json.loads(item.aliases_json or "[]"),
            "price": item.price,
            "size": item.size_label,
            "set_contents": item.set_contents,
            "options": json.loads(item.toppings_json or "[]"),
            "sold_out": item.sold_out,
            "localized_names": json.loads(item.localized_names_json or "{}"),
        }
        for item in sorted(version.items, key=lambda value: value.id)
    ]


class AiOrderAdapter(ABC):
    provider: str
    model_name: str | None = None

    @abstractmethod
    def resolve(self, request: ResolveOrderRequest, version: MenuVersion) -> RawResolution:
        raise NotImplementedError


class OpenAiOrderAdapter(AiOrderAdapter):
    provider = "openai"

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        options = {"api_key": settings.openai_api_key, "timeout": settings.llm_timeout_seconds, "max_retries": settings.llm_max_retries}
        if settings.llm_api_endpoint:
            options["base_url"] = settings.llm_api_endpoint
        self.client = OpenAI(**options)

    def resolve(self, request: ResolveOrderRequest, version: MenuVersion) -> RawResolution:
        response = self.client.responses.parse(
            model=self.model_name,
            reasoning={"effort": "low"},
            input=[
                {"role": "system", "content": settings.llm_prompt_override or DEFAULT_PROMPT},
                {"role": "user", "content": json.dumps({"store_id": request.store_id, "menu_version": version.version, "recognized_text": request.recognized_text, "input_language": request.input_language, "current_menu": menu_payload(version)}, ensure_ascii=False)},
            ],
            text_format=RawResolution,
        )
        if not response.output_parsed:
            raise ValueError("AIから候補を取得できませんでした")
        return response.output_parsed


class LocalMenuResolver(AiOrderAdapter):
    provider = "local_fallback"

    def resolve(self, request: ResolveOrderRequest, version: MenuVersion) -> RawResolution:
        text = request.recognized_text.casefold()
        number_words = {
            "一": 1, "ひとつ": 1, "一つ": 1, "1": 1, "二": 2, "ふたつ": 2, "二つ": 2, "2": 2, "三": 3, "みっつ": 3, "三つ": 3, "3": 3,
            "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "một": 1, "hai": 2, "ba": 3, "bốn": 4, "năm": 5,
            "一个": 1, "两个": 2, "三个": 3, "四个": 4, "五个": 5,
            "하나": 1, "둘": 2, "셋": 3, "넷": 4, "다섯": 5,
            "ایک": 1, "دو": 2, "تین": 3, "چار": 4, "پانچ": 5,
        }
        def item_terms(item: MenuVersionItem) -> list[str]:
            try:
                localized = json.loads(item.localized_names_json or "{}")
            except (TypeError, ValueError):
                localized = {}
            localized_terms = [value for value in localized.values() if isinstance(value, str)] if isinstance(localized, dict) else []
            return [item.name, item.reading, *json.loads(item.aliases_json or "[]"), *localized_terms]
        def quantity_in(value: str) -> int | None:
            found = [(value.find(word.casefold()), number) for word, number in number_words.items() if word.casefold() in value]
            return min(found, key=lambda match: match[0])[1] if found else None
        operation = "cancel" if any(word in text for word in ("取消", "取り消", "キャンセル")) else "change" if "変更" in text else "add"
        comparison_text = re.sub(r"(?:を|の|一つ|二つ|三つ|ひとつ|ふたつ|みっつ|[123一二三])(?:個|皿|杯)?", "", text).strip()
        category_matches = [
            item for item in version.items
            if not item.sold_out
            and item.category_name
            and comparison_text in item.category_name.casefold()
        ]
        if category_matches:
            category_matches.sort(key=lambda item: item.id)
            return RawResolution(items=[RawItem(
                source_phrase=request.recognized_text,
                quantity=next((number for word, number in number_words.items() if word in text), 1),
                operation=operation,
                candidates=[RawCandidate(menu_id=item.menu_id) for item in category_matches[:5]],
            )])
        keyword_source = comparison_text
        option_words = {
            option["name"] if isinstance(option, dict) else str(option)
            for item in version.items
            for option in json.loads(item.toppings_json or "[]")
        }
        for option_word in option_words:
            keyword_source = keyword_source.replace(option_word.casefold(), "")
        query_keyword = _menu_keyword(keyword_source)
        occurrences: list[tuple[int, MenuVersionItem, str]] = []
        for item in version.items:
            if item.sold_out:
                continue
            terms = item_terms(item)
            found = [
                (text.find(term.casefold()), term)
                for term in terms
                if term
                and term.casefold() in text
                and not (len(query_keyword) >= 2 and not _menu_keyword(term))
            ]
            if found:
                position, term = min(found, key=lambda value: (value[0], -len(value[1])))
                occurrences.append((position, item, term))
        occurrences = [
            occurrence for occurrence in occurrences
            if not any(
                other[0] <= occurrence[0]
                and other[0] + len(other[2]) >= occurrence[0] + len(occurrence[2])
                and len(other[2]) > len(occurrence[2])
                for other in occurrences
            )
        ]
        occurrences.sort(key=lambda value: (value[0], value[1].id))
        if occurrences:
            result = []
            for index, (position, item, term) in enumerate(occurrences):
                end = occurrences[index + 1][0] if index + 1 < len(occurrences) else len(text)
                phrase = text[position:end].strip("、, ") or term
                suffix = text[position + len(term):end]
                previous_end = occurrences[index - 1][0] + len(occurrences[index - 1][2]) if index else 0
                prefix = text[previous_end:position]
                quantity = quantity_in(suffix) or quantity_in(prefix) or 1
                options = [option["name"] if isinstance(option, dict) else str(option) for option in json.loads(item.toppings_json or "[]")]
                selected = [option for option in options if option.casefold() in phrase]
                result.append(RawItem(source_phrase=phrase, quantity=quantity, operation=operation, candidates=[RawCandidate(menu_id=item.menu_id, option_candidates=selected)]))
            return RawResolution(items=result)
        scored: list[tuple[float, MenuVersionItem]] = []
        contained: list[MenuVersionItem] = []
        for item in version.items:
            terms = item_terms(item)
            if comparison_text and any(comparison_text in term.casefold() for term in terms if term):
                contained.append(item)
        if contained:
            contained.sort(key=lambda item: item.id)
            return RawResolution(items=[RawItem(
                source_phrase=request.recognized_text,
                quantity=next((number for word, number in number_words.items() if word in text), 1),
                operation=operation,
                candidates=[RawCandidate(menu_id=item.menu_id) for item in contained[:5]],
            )])
        # 「マトンカレー」のように、商品名の一部＋一般語で話された場合。
        # 一般語を除いた2文字以上のキーワードだけを使い、該当商品は候補表示に留める。
        keyword = query_keyword
        if len(keyword) >= 2:
            keyword_matches: list[tuple[float, MenuVersionItem]] = []
            for item in version.items:
                terms = item_terms(item)
                best_score = 0.0
                for term in terms:
                    term_keyword = _menu_keyword(term)
                    if len(term_keyword) < 2:
                        continue
                    if keyword in term_keyword:
                        best_score = max(best_score, len(keyword) / len(term_keyword))
                    elif term_keyword in keyword:
                        best_score = max(best_score, len(term_keyword) / len(keyword))
                if best_score:
                    keyword_matches.append((best_score, item))
            if keyword_matches:
                keyword_matches.sort(key=lambda value: (-value[0], value[1].id))
                return RawResolution(items=[RawItem(
                    source_phrase=request.recognized_text,
                    quantity=next((number for word, number in number_words.items() if word in text), 1),
                    operation=operation,
                    candidates=[RawCandidate(menu_id=item.menu_id) for _, item in keyword_matches[:5]],
                )])
        for item in version.items:
            terms = item_terms(item)
            score = max((SequenceMatcher(None, comparison_text, term.casefold()).ratio() for term in terms if term), default=0)
            if score >= 0.34:
                scored.append((score, item))
        scored.sort(key=lambda value: (-value[0], value[1].id))
        return RawResolution(items=[RawItem(source_phrase=request.recognized_text, quantity=next((number for word, number in number_words.items() if word in text), 1), operation=operation, candidates=[RawCandidate(menu_id=item.menu_id) for _, item in scored[:5]])] if scored else [])


def validate_resolution(raw: RawResolution, request: ResolveOrderRequest, version: MenuVersion, provider: str, model_name: str | None) -> ResolveOrderResponse:
    now = datetime.now(timezone.utc)
    def active(item: MenuVersionItem) -> bool:
        start = item.valid_from.replace(tzinfo=timezone.utc) if item.valid_from.tzinfo is None else item.valid_from
        end = item.valid_to.replace(tzinfo=timezone.utc) if item.valid_to and item.valid_to.tzinfo is None else item.valid_to
        return not item.sold_out and start <= now and (end is None or end > now)
    valid = {item.menu_id: item for item in version.items if active(item)}
    items: list[ResolvedOrderItem] = []
    for raw_item in raw.items[:30]:
        candidates = []
        for candidate in raw_item.candidates[:5]:
            item = valid.get(candidate.menu_id)
            if not item:
                continue
            allowed = {option["name"] if isinstance(option, dict) else str(option) for option in json.loads(item.toppings_json or "[]")}
            candidates.append(ResolvedMenuCandidate(menu_id=item.menu_id, menu_item_id=item.menu_item_id, name=item.name, option_candidates=[value for value in candidate.option_candidates if value in allowed]))
        if candidates:
            items.append(ResolvedOrderItem(source_phrase=raw_item.source_phrase, quantity=raw_item.quantity, operation=raw_item.operation if raw_item.operation in {"add", "change", "cancel"} else "add", candidates=candidates))
    candidate_count = sum(len(item.candidates) for item in items)
    status = "not_found" if not candidate_count else "ambiguous" if any(len(item.candidates) > 1 for item in items) else "needs_confirmation"
    return ResolveOrderResponse(status=status, recognized_text=request.recognized_text, menu_version=version.version, items=items, provider=provider, model_name=model_name, message="音声から候補を作れませんでした。メニューから選んでください" if not items else None)


def resolve_order(db: Session, request: ResolveOrderRequest) -> ResolveOrderResponse:
    version = load_current_menu_version(db, request.store_id)
    if not version:
        raise ValueError("現在有効なメニューがありません")
    store = db.get(Store, request.store_id)
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    used = db.scalar(select(func.count(AiResolutionLog.id)).where(AiResolutionLog.store_id == request.store_id, AiResolutionLog.created_at >= month_start)) or 0
    allow_external = bool(settings.llm_enabled and settings.openai_api_key and store and used < store.monthly_ai_request_limit)
    adapters: list[AiOrderAdapter] = []
    if allow_external and settings.llm_provider == "openai":
        for model in dict.fromkeys([settings.openai_model, settings.openai_fallback_model]):
            if model:
                adapters.append(OpenAiOrderAdapter(model))
    adapters.append(LocalMenuResolver())
    response: ResolveOrderResponse | None = None
    for adapter in adapters:
        try:
            response = validate_resolution(adapter.resolve(request, version), request, version, adapter.provider, adapter.model_name)
            break
        except Exception:
            logger.exception("AI注文候補の生成に失敗: provider=%s model=%s", adapter.provider, adapter.model_name)
    if response is None:
        response = ResolveOrderResponse(status="fallback", recognized_text=request.recognized_text, menu_version=version.version, provider="local_fallback", message="音声から候補を作れませんでした。メニューから選んでください")
    db.add(AiResolutionLog(store_id=request.store_id, menu_version=version.version, recognized_text=request.recognized_text, input_language=request.input_language, provider=response.provider, model_name=response.model_name, result_json=response.model_dump_json()))
    db.commit()
    return response
