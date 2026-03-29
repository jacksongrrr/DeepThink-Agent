from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置：自 .env 与环境变量加载，禁止在代码中硬编码密钥。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    deepseek_api_key: str = Field(..., validation_alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(
        "https://api.deepseek.com",
        validation_alias="DEEPSEEK_BASE_URL",
    )
    model_chat: str = Field("deepseek-chat", validation_alias="DEEPSEEK_MODEL_CHAT")
    model_reasoner: str = Field("deepseek-reasoner", validation_alias="DEEPSEEK_MODEL_REASONER")
    host: str = Field("127.0.0.1", validation_alias="HOST")
    port: int = Field(8765, validation_alias="PORT")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
