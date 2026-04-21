"""Mock LLM — no network."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from iskra.core.config import LLMConfig
from iskra.models import LLMResponse


class MockAdapter:
    def __init__(self, settings: dict, llm_config: LLMConfig) -> None:
        del llm_config
        self._template = settings.get("response_template", "[MOCK] Thought registered.")
        self._latency_ms = int(settings.get("latency_ms", 100))
        self._trigger_type = "unknown"

    def prepare_tick(self, trigger_type: str) -> None:
        """MainLoop sets this before each complete() for template placeholders."""
        self._trigger_type = trigger_type

    async def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        await asyncio.sleep(self._latency_ms / 1000.0)
        try:
            content = self._template.format(
                trigger_type=self._trigger_type,
                user_prompt=user_prompt[:200],
            )
        except (KeyError, ValueError):
            content = self._template
        if not content.strip():
            content = "[MOCK] empty"
        return LLMResponse(
            event_id="",
            content=content,
            model="mock",
            tokens_used=0,
            latency_ms=self._latency_ms,
            timestamp=datetime.now(UTC),
        )

    def is_available(self) -> bool:
        return True
