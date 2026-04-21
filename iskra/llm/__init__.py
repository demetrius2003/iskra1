"""LLM adapters."""

from typing import Any

from iskra.core.config import LLMConfig
from iskra.llm.gigachat_adapter import GigaChatAdapter
from iskra.llm.mock_adapter import MockAdapter
from iskra.llm.ollama_adapter import OllamaAdapter
from iskra.llm.protocol import LLMAdapter
from iskra.llm.yandexgpt_adapter import YandexGPTAdapter


def create_llm_adapter(config: LLMConfig) -> LLMAdapter:
    name = config.adapter
    settings: dict[str, Any] = dict(config.settings.get(name, {}))
    if name == "mock":
        return MockAdapter(settings, config)
    if name == "ollama":
        return OllamaAdapter(settings, config)
    if name == "gigachat":
        return GigaChatAdapter(settings, config)
    if name in ("yandexgpt", "yandex_gpt"):
        return YandexGPTAdapter(settings, config)
    raise ValueError(f"Unknown llm adapter: {name}")
