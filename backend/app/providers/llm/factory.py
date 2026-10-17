"""Factory selecting the active ``LLMProvider`` from ``Settings.llm_provider``."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.domain.interfaces.llm_provider import LLMProvider
from app.providers.llm.template_provider import TemplateLLMProvider

logger = get_logger(__name__)


def build_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "gemini" and settings.gemini_api_key:
        from app.providers.llm.gemini_provider import GeminiLLMProvider

        return GeminiLLMProvider(api_key=settings.gemini_api_key)
    if settings.llm_provider != "template":
        logger.warning(
            "llm_provider=%s not configured or missing API key; falling back to template",
            settings.llm_provider,
        )
    return TemplateLLMProvider()


@lru_cache
def get_llm_provider() -> LLMProvider:
    return build_llm_provider(get_settings())
