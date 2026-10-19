import json
import logging
import re
from abc import ABC, abstractmethod

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Interpretation, MenuItem
from app.schemas import Candidate, CandidateItem, InterpretRequest, InterpretResponse, LlmInterpretation
from app.services.menu import load_available_menu, to_menu_view


SYSTEM_PROMPT = """あなたは飲食店の注文候補抽出器です。渡された販売中メニューだけを使ってください。
注文を確定してはいけません。価格を生成してはいけません。商品は必ずmenu_item_idで参照します。
音声が曖昧なら複数候補を返してください。数量が聞き取れなければnullにします。
追加はoperation=add、数量変更はoperation=change、取消はoperation=cancelにします。
お冷、こぼした、待ち時間、会計、店員呼び出しはservice_requestに分類します。
質問は、お客さんが次に選ぶ必要がある一つの事柄だけを短い日本語で示してください。"""

logger = logging.getLogger(__name__)


class Interpreter(ABC):
    name: str

    @abstractmethod
    def interpret(self, request: InterpretRequest, menu: list[MenuItem]) -> LlmInterpretation:
        raise NotImplementedError


class OpenAIInterpreter(Interpreter):
    name = "openai"

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.client = OpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )

    def interpret(self, request: InterpretRequest, menu: list[MenuItem]) -> LlmInterpretation:
        menu_payload = [
            {
                "id": item.id,
                "name": item.name,
                "short_name": item.short_name,
                "localized_names": json.loads(item.localized_names_json or "{}"),
                "aliases": [alias.alias for alias in item.aliases],
                "modifier_options": [
                    {"id": option.id, "name": option.name}
                    for link in item.modifier_groups
                    for option in link.group.options
                ],
            }
            for item in menu
        ]
        response = self.client.responses.parse(
            model=self.model_name,
            reasoning={"effort": "low"},
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "utterance": request.japanese_text or request.text,
                            "source_utterance": request.text,
                            "input_language": request.input_language,
                            "stt_alternatives": request.stt_alternatives,
                            "available_menu": menu_payload,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            text_format=LlmInterpretation,
        )
        if not response.output_parsed:
            raise ValueError("LLMから有効な候補を取得できませんでした")
        return response.output_parsed


class LocalFallbackInterpreter(Interpreter):
    name = "local_fallback"

    def interpret(self, request: InterpretRequest, menu: list[MenuItem]) -> LlmInterpretation:
        text = (request.japanese_text or request.text).casefold()
        request_words = {
            "お冷": "water",
            "水ください": "water",
            "こぼした": "spill",
            "あと何分": "wait_time",
            "会計": "checkout",
            "店員": "call_staff",
        }
        for word, request_type in request_words.items():
            if word in text:
                return LlmInterpretation(intent="service_request", service_request_type=request_type)

        number_words = {
            "一": 1, "1": 1, "ひとつ": 1, "一つ": 1,
            "二": 2, "2": 2, "ふたつ": 2, "二つ": 2,
            "三": 3, "3": 3, "みっつ": 3, "三つ": 3,
            "四": 4, "4": 4, "四つ": 4,
            "五": 5, "5": 5, "五つ": 5,
            "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "một": 1, "hai": 2, "ba": 3, "bốn": 4, "năm": 5,
            "一个": 1, "两个": 2, "三个": 3, "四个": 4, "五个": 5,
            "하나": 1, "둘": 2, "셋": 3, "넷": 4, "다섯": 5,
            "ایک": 1, "دو": 2, "تین": 3, "چار": 4, "پانچ": 5,
        }
        operation = "cancel" if any(word in text for word in ["取り消", "取消", "キャンセル"]) else "change" if "変更" in text else "add"
        matches: list[tuple[MenuItem, int, str]] = []
        for item in menu:
            try:
                localized = json.loads(item.localized_names_json or "{}")
            except (TypeError, ValueError):
                localized = {}
            terms = [item.name, item.short_name, *(alias.alias for alias in item.aliases), *(localized.values() if isinstance(localized, dict) else [])]
            found = [(text.find(term.casefold()), term) for term in terms if term and term.casefold() in text]
            if found:
                position, term = min(found, key=lambda value: value[0])
                matches.append((item, position, term))
            elif any(text in term.casefold() for term in terms if term):
                matches.append((item, 0, text))

        matches.sort(key=lambda value: (value[1], value[0].display_order))
        distinct_positions = {position for _, position, _ in matches}
        if len(matches) > 1 and len(distinct_positions) > 1:
            items: list[CandidateItem] = []
            for index, (item, position, term) in enumerate(matches):
                next_position = next((other[1] for other in matches[index + 1:] if other[1] > position), len(text))
                fragment = text[position + len(term):next_position]
                quantity = next((value for word, value in number_words.items() if word.casefold() in fragment), 1)
                option_ids = [
                    option.id
                    for link in item.modifier_groups
                    for option in link.group.options
                    if option.name.casefold() in fragment
                ]
                items.append(CandidateItem(menu_item_id=item.id, quantity=quantity, modifier_option_ids=option_ids, operation=operation))
            label = "、".join(f"{menu_item.short_name} {candidate.quantity}点" for (menu_item, _, _), candidate in zip(matches, items))
            candidates = [Candidate(items=items, label=label)]
        else:
            quantity_matches = list(re.finditer(r"(ひとつ|ふたつ|みっつ|[一二三四五12345])(?:つ|個|皿|杯)?", text))
            quantity_match = quantity_matches[-1] if operation == "change" and quantity_matches else quantity_matches[0] if quantity_matches else None
            quantity = number_words.get(quantity_match.group(1), 1) if quantity_match else 1
            candidates = [
                Candidate(
                    items=[CandidateItem(menu_item_id=item.id, quantity=quantity, operation=operation)],
                    label=item.short_name,
                )
                for item, _, _ in matches[:5]
            ]
        return LlmInterpretation(
            intent="order" if candidates else "unknown",
            candidates=candidates,
            question="どの商品ですか？" if len(candidates) > 1 else None,
        )


def _validate_llm_result(result: LlmInterpretation, menu: list[MenuItem]) -> LlmInterpretation:
    valid_items = {item.id: item for item in menu}
    valid_options = {
        item.id: {option.id for link in item.modifier_groups for option in link.group.options}
        for item in menu
    }
    clean_candidates: list[Candidate] = []
    for candidate in result.candidates[:5]:
        clean_items: list[CandidateItem] = []
        for item in candidate.items:
            if item.menu_item_id not in valid_items:
                continue
            allowed = valid_options[item.menu_item_id]
            clean_items.append(
                CandidateItem(
                    menu_item_id=item.menu_item_id,
                    quantity=item.quantity,
                    modifier_option_ids=[option_id for option_id in item.modifier_option_ids if option_id in allowed],
                    operation=item.operation,
                )
            )
        if clean_items:
            clean_candidates.append(Candidate(items=clean_items, label=candidate.label))
    result.candidates = clean_candidates
    if result.intent == "order" and not clean_candidates:
        result.intent = "unknown"
    return result


def interpret_input(db: Session, request: InterpretRequest) -> InterpretResponse:
    menu = load_available_menu(db)
    interpreters: list[Interpreter] = []
    if settings.llm_enabled and settings.openai_api_key:
        model_names = list(dict.fromkeys([settings.openai_model, settings.openai_fallback_model]))
        interpreters.extend(OpenAIInterpreter(model_name) for model_name in model_names if model_name)
    interpreters.append(LocalFallbackInterpreter())

    result: LlmInterpretation | None = None
    interpreter: Interpreter = interpreters[-1]
    for candidate_interpreter in interpreters:
        try:
            result = candidate_interpreter.interpret(request, menu)
            interpreter = candidate_interpreter
            break
        except Exception:
            logger.exception(
                "注文解析に失敗したため次の解析器へ切り替えます: provider=%s model=%s",
                candidate_interpreter.name,
                getattr(candidate_interpreter, "model_name", None),
            )
    if result is None:
        # 最後のLocalFallbackInterpreterは外部依存がないため通常ここへは到達しない。
        result = LlmInterpretation(intent="unknown")
    result = _validate_llm_result(result, menu)

    record = Interpretation(
        session_id=request.session_id,
        original_text=request.text,
        result_json=result.model_dump_json(),
        provider=interpreter.name,
        model_name=getattr(interpreter, "model_name", None),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    if result.intent == "service_request":
        state = "service_request"
    elif not result.candidates:
        state = "needs_retry"
    elif len(result.candidates) == 1:
        state = "ready_to_confirm"
    else:
        state = "needs_item_choice"

    referenced_ids = {item.menu_item_id for candidate in result.candidates for item in candidate.items}
    return InterpretResponse(
        interpretation_id=record.id,
        state=state,
        question=result.question,
        candidates=result.candidates,
        menu_items=[to_menu_view(item) for item in menu if item.id in referenced_ids],
        service_request_type=result.service_request_type,
        provider=interpreter.name,
        model_name=getattr(interpreter, "model_name", None),
    )
