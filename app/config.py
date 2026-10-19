from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    restaurant_name: str = "サンプル食堂"
    default_store_id: str = "STORE001"
    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'restaurant.db').as_posix()}"
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    openai_fallback_model: str = "gpt-5-nano"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    llm_timeout_seconds: float = 8.0
    llm_max_retries: int = 1
    llm_provider: str = "openai"
    llm_api_endpoint: str = ""
    llm_prompt_override: str = ""
    store_monthly_ai_limit: int = 10000
    llm_enabled: bool = True

    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")


settings = Settings()
