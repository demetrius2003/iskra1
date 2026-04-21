"""YandexGPT (Yandex Cloud Foundation Models) — completion API."""

from __future__ import annotations

import logging
import re
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from iskra.core.config import LLMConfig
from iskra.llm.protocol import LLMNetworkError, LLMRateLimitError, LLMTimeoutError
from iskra.models import LLMResponse

logger = logging.getLogger("iskra.llm.yandexgpt")

_COMPLETION_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"


class YandexGPTAdapter:
    """
    Настройки (config.llm.settings.yandexgpt):
      folder_id — каталог в Yandex Cloud (обязательно)
      auth — \"iam\" | \"api_key\" (по умолчанию iam)
      iam_token — Bearer-токен (короткоживущий; обновляйте снаружи или через cron)
      api_key — секрет ключа API (заголовок Api-Key)
      model_uri — полный URI, например gpt://b1g.../yandexgpt/latest (если задан — folder/model игнорируются)
      model — имя модели без префикса, по умолчанию yandexgpt
      model_version — суффикс URI, по умолчанию latest (yandexgpt-lite, yandexgpt и т.д.)
    """

    def __init__(self, settings: dict[str, Any], llm_config: LLMConfig) -> None:
        self._llm_config = llm_config
        self._folder_id = str(settings.get("folder_id", "")).strip()
        self._auth = str(settings.get("auth", "iam")).lower().strip()
        self._iam_token = str(settings.get("iam_token", "")).strip()
        self._api_key = str(settings.get("api_key", "")).strip()
        self._timeout = float(settings.get("timeout_seconds", 120))
        self._completion_url = str(settings.get("completion_url", _COMPLETION_URL)).rstrip("/")

        model_uri = str(settings.get("model_uri", "")).strip()
        if model_uri:
            self._model_uri = model_uri
            m = re.match(r"^gpt://([^/]+)/", model_uri)
            if m:
                self._folder_id = self._folder_id or m.group(1)
        elif not self._folder_id:
            raise ValueError("yandexgpt: задайте folder_id или полный model_uri")
        else:
            model = str(settings.get("model", "yandexgpt")).strip()
            version = str(settings.get("model_version", "latest")).strip()
            self._model_uri = f"gpt://{self._folder_id}/{model}/{version}"

    def _auth_headers(self) -> dict[str, str]:
        if self._auth == "api_key":
            if not self._api_key:
                raise LLMNetworkError("yandexgpt: пустой api_key")
            return {"Authorization": f"Api-Key {self._api_key}"}
        if not self._iam_token:
            raise LLMNetworkError("yandexgpt: пустой iam_token (auth=iam)")
        return {"Authorization": f"Bearer {self._iam_token}"}

    async def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        try:
            auth_h = self._auth_headers()
        except LLMNetworkError:
            raise

        payload: dict[str, Any] = {
            "modelUri": self._model_uri,
            "completionOptions": {
                "stream": False,
                "temperature": self._llm_config.temperature,
                "maxTokens": self._llm_config.max_tokens,
            },
            "messages": [
                {"role": "system", "text": system_prompt},
                {"role": "user", "text": user_prompt},
            ],
        }
        headers = {
            **auth_h,
            "Content-Type": "application/json",
            "x-folder-id": self._folder_id,
        }
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(self._completion_url, headers=headers, json=payload)
                if resp.status_code == 429:
                    raise LLMRateLimitError("yandexgpt rate limit")
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException as e:
            raise LLMTimeoutError(str(e)) from e
        except LLMRateLimitError:
            raise
        except httpx.HTTPStatusError as e:
            raise LLMNetworkError(f"yandexgpt HTTP {e.response.status_code}: {e.response.text[:500]}") from e
        except httpx.HTTPError as e:
            raise LLMNetworkError(str(e)) from e

        latency = int((time.monotonic() - t0) * 1000)
        result = data.get("result") or data
        alternatives = result.get("alternatives") or []
        content = ""
        if alternatives:
            msg = (alternatives[0] or {}).get("message") or {}
            content = (msg.get("text") or "").strip()
        if not content:
            content = "(пустой ответ YandexGPT)"
        usage = result.get("usage") or {}
        total = usage.get("totalTokens") or usage.get("total_tokens")
        tokens = int(total) if total is not None else 0
        return LLMResponse(
            event_id="",
            content=content,
            model=self._model_uri,
            tokens_used=tokens,
            latency_ms=latency,
            timestamp=datetime.now(UTC),
        )

    def is_available(self) -> bool:
        if not self._folder_id:
            return False
        if self._auth == "api_key":
            return bool(self._api_key)
        return bool(self._iam_token)
