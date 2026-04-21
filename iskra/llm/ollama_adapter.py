"""Ollama chat API adapter."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import httpx

from iskra.core.config import LLMConfig
from iskra.llm.protocol import LLMNetworkError, LLMRateLimitError, LLMTimeoutError
from iskra.models import LLMResponse


class OllamaAdapter:
    def __init__(self, settings: dict[str, Any], llm_config: LLMConfig) -> None:
        self._base_url = str(settings.get("base_url", "http://localhost:11434")).rstrip("/")
        self._model = str(settings.get("model", "llama3:8b"))
        self._timeout = float(settings.get("timeout_seconds", 60))
        self._llm_config = llm_config

    async def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        t0 = time.monotonic()
        url = f"{self._base_url}/api/chat"
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": self._llm_config.temperature,
                "num_predict": self._llm_config.max_tokens,
            },
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 429:
                    raise LLMRateLimitError("ollama rate limited")
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException as e:
            raise LLMTimeoutError(str(e)) from e
        except LLMRateLimitError:
            raise
        except httpx.HTTPError as e:
            raise LLMNetworkError(str(e)) from e

        latency = int((time.monotonic() - t0) * 1000)
        msg = data.get("message") or {}
        content = (msg.get("content") or "").strip() or "(empty response)"
        tokens = int(data.get("eval_count", 0) or 0)
        return LLMResponse(
            event_id="",
            content=content,
            model=self._model,
            tokens_used=tokens,
            latency_ms=latency,
            timestamp=datetime.now(UTC),
        )

    def is_available(self) -> bool:
        try:
            r = httpx.get(f"{self._base_url}/api/tags", timeout=5.0)
            return r.status_code == 200
        except Exception:
            return False
