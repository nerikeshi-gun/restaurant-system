import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def offline_settings(monkeypatch):
    """テストが.envのAPIキーを読んで外部LLM/翻訳APIへ接続しないようにする。

    各テストが個別にsettingsを上書きする場合は、この後で上書きされる。
    """
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "llm_provider", "openai")
