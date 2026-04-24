from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AgenticProvider(str, Enum):
    OPENAI = "openai"
    GEMINI = "gemini"
    ANTHROPIC = "anthropic"
    LOCAL = "local"


@dataclass(frozen=True)
class AgenticProviderConfig:
    provider: AgenticProvider
    model: str
    api_key: str | None


def parse_agentic_provider(value: str, *, name: str = "provider") -> AgenticProvider:
    normalized = value.strip().lower()
    for provider in AgenticProvider:
        if normalized == provider.value:
            return provider
    supported = ", ".join(provider.value for provider in AgenticProvider)
    raise ValueError(f"Invalid value for {name}: '{value}'. Supported: {supported}")


def default_model_for_provider(provider: AgenticProvider) -> str:
    if provider == AgenticProvider.OPENAI:
        return "gpt-5.4-mini"
    if provider == AgenticProvider.GEMINI:
        return "gemini-2.5-flash"
    if provider == AgenticProvider.ANTHROPIC:
        return "claude-sonnet-4.5"
    return "local-default"
