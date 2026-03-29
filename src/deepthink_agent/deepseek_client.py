from __future__ import annotations

from openai import AsyncOpenAI

from deepthink_agent.config import Settings


def create_async_client(settings: Settings) -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
    )
