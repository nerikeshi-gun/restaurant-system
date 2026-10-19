from abc import ABC, abstractmethod
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


LANGUAGE_NAMES = {
    "ja": "Japanese", "en": "English", "zh": "Simplified Chinese",
    "ko": "Korean", "vi": "Vietnamese", "ur": "Urdu",
}


class Translator(ABC):
    @abstractmethod
    def prepare(self, source_text: str, source_language: str, target_language: str = "ja") -> dict:
        raise NotImplementedError


class ManualTranslator(Translator):
    def prepare(self, source_text: str, source_language: str, target_language: str = "ja") -> dict:
        return {
            "provider": "manual", "source_text": source_text,
            "source_language": source_language, "target_language": target_language,
            "translated_text": source_text if source_language == target_language else "",
            "manual_confirmation_required": True,
        }


class GeminiTranslator(Translator):
    def prepare(self, source_text: str, source_language: str, target_language: str = "ja") -> dict:
        if source_language == target_language:
            translated = source_text
        else:
            target = LANGUAGE_NAMES.get(target_language, target_language)
            response = httpx.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent",
                headers={"x-goog-api-key": settings.gemini_api_key, "Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": (
                        f"Translate the following restaurant customer message into {target}. "
                        "Return only the translation, without quotes or explanation. "
                        f"Preserve names and quantities exactly.\n\n{source_text}"
                    )}]}],
                    "generationConfig": {"temperature": 0, "maxOutputTokens": 256},
                },
                timeout=settings.llm_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            translated = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        return {
            "provider": "gemini", "model": settings.gemini_model,
            "source_text": source_text, "source_language": source_language,
            "target_language": target_language, "translated_text": translated,
            "manual_confirmation_required": False,
        }


class ConfiguredTranslator(Translator):
    def prepare(self, source_text: str, source_language: str, target_language: str = "ja") -> dict:
        if settings.llm_enabled and settings.llm_provider == "gemini" and settings.gemini_api_key:
            try:
                return GeminiTranslator().prepare(source_text, source_language, target_language)
            except Exception:
                logger.exception("Gemini翻訳に失敗したため手動確認へ切り替えます")
                return ManualTranslator().prepare(source_text, source_language, target_language)
        return ManualTranslator().prepare(source_text, source_language, target_language)


translator: Translator = ConfiguredTranslator()
