"""GigaChat (Сбер) — OAuth2 + chat/completions."""

from __future__ import annotations

import base64
import time
from pathlib import Path
from urllib.parse import urlencode
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx

from iskra.core.config import LLMConfig
from iskra.llm.protocol import LLMNetworkError, LLMRateLimitError, LLMTimeoutError
from iskra.models import LLMResponse

_DEFAULT_OAUTH = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
_DEFAULT_API_BASE = "https://gigachat.devices.sberbank.ru/api/v1"


def _resolve_gigachat_verify(settings: dict[str, Any]) -> bool | str:
    """
    Как в langchain_community GigaChat: путь к russian_trusted_root_ca.cer
    передаётся в httpx как verify=<path>. При verify_ssl: false — проверка отключена.
    Относительные пути — от текущего рабочего каталога процесса.
    """
    if not bool(settings.get("verify_ssl", True)):
        return False
    bundle = settings.get("ca_bundle_file") or settings.get("ca_bundle")
    if not bundle:
        return True
    p = Path(str(bundle).strip()).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    p = p.resolve()
    if not p.is_file():
        raise ValueError(
            "gigachat: не найден файл CA (ca_bundle_file). Скачайте russian_trusted_root_ca.cer "
            f"с портала Сбера для GigaChat и укажите путь; ожидался файл: {p}"
        )
    return str(p)


class GigaChatAdapter:
    """
    Настройки (config.llm.settings.gigachat):
      client_id, client_secret — либо одно поле credentials_base64 (уже Base64 от id:secret)
      scope — по умолчанию GIGACHAT_API_PERS
      oauth_url, api_base — опционально
      model — по умолчанию GigaChat
      verify_ssl — false только если нужен обход проверки сертификата (небезопасно)
      ca_bundle_file (или ca_bundle) — путь к russian_trusted_root_ca.cer для проверки цепочки
    """

    def __init__(self, settings: dict[str, Any], llm_config: LLMConfig) -> None:
        self._llm_config = llm_config
        self._oauth_url = str(settings.get("oauth_url", _DEFAULT_OAUTH)).rstrip("/")
        self._api_base = str(settings.get("api_base", _DEFAULT_API_BASE)).rstrip("/")
        self._scope = str(settings.get("scope", "GIGACHAT_API_PERS"))
        self._model = str(settings.get("model", "GigaChat"))
        self._timeout = float(settings.get("timeout_seconds", 120))
        self._verify: bool | str = _resolve_gigachat_verify(settings)

        cred_b64 = settings.get("credentials_base64")
        if cred_b64:
            self._basic = str(cred_b64).strip()
        else:
            cid = str(settings.get("client_id", "")).strip()
            csec = str(settings.get("client_secret", "")).strip()
            if not cid or not csec:
                raise ValueError(
                    "gigachat: задайте client_id + client_secret или credentials_base64"
                )
            raw = f"{cid}:{csec}".encode("utf-8")
            self._basic = base64.standard_b64encode(raw).decode("ascii")

        self._access_token: str | None = None
        self._token_deadline: float = 0.0  # time.time() до которого токен валиден (с запасом)
        self._token_lock: Any = None  # asyncio.Lock, lazy

    def _ensure_lock(self) -> None:
        import asyncio

        if self._token_lock is None:
            self._token_lock = asyncio.Lock()

    async def _fetch_token(self) -> None:
        rq_uid = str(uuid4())
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": rq_uid,
            "Authorization": f"Basic {self._basic}",
        }
        body = urlencode({"scope": self._scope})
        try:
            async with httpx.AsyncClient(timeout=self._timeout, verify=self._verify) as client:
                resp = await client.post(self._oauth_url, headers=headers, content=body)
                if resp.status_code == 429:
                    raise LLMRateLimitError("gigachat oauth rate limit")
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException as e:
            raise LLMTimeoutError(str(e)) from e
        except LLMRateLimitError:
            raise
        except httpx.HTTPStatusError as e:
            raise LLMNetworkError(f"gigachat oauth HTTP {e.response.status_code}: {e.response.text}") from e
        except httpx.HTTPError as e:
            raise LLMNetworkError(str(e)) from e

        token = data.get("access_token")
        if not token:
            raise LLMNetworkError("gigachat oauth: no access_token in response")
        self._access_token = token
        exp = data.get("expires_at")
        if isinstance(exp, (int, float)):
            exp_f = float(exp)
            if exp_f > 1e12:
                exp_f /= 1000.0
            self._token_deadline = exp_f - 60.0
        else:
            self._token_deadline = time.time() + 25 * 60

    async def _ensure_token(self) -> None:
        self._ensure_lock()
        assert self._token_lock is not None
        async with self._token_lock:
            if self._access_token and time.time() < self._token_deadline:
                return
            await self._fetch_token()

    async def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        await self._ensure_token()
        assert self._access_token is not None
        url = f"{self._api_base}/chat/completions"
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self._llm_config.temperature,
            "max_tokens": self._llm_config.max_tokens,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self._timeout, verify=self._verify) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 401:
                    async with self._token_lock:
                        self._access_token = None
                        self._token_deadline = 0.0
                    await self._ensure_token()
                    headers["Authorization"] = f"Bearer {self._access_token}"
                    resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 429:
                    raise LLMRateLimitError("gigachat chat rate limit")
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException as e:
            raise LLMTimeoutError(str(e)) from e
        except LLMRateLimitError:
            raise
        except httpx.HTTPStatusError as e:
            raise LLMNetworkError(f"gigachat chat HTTP {e.response.status_code}") from e
        except httpx.HTTPError as e:
            raise LLMNetworkError(str(e)) from e

        latency = int((time.monotonic() - t0) * 1000)
        choices = data.get("choices") or []
        content = ""
        if choices:
            msg = (choices[0] or {}).get("message") or {}
            content = (msg.get("content") or "").strip()
        if not content:
            content = "(пустой ответ GigaChat)"
        usage = data.get("usage") or {}
        tokens = int(usage.get("total_tokens", 0) or 0)
        model_name = str(data.get("model", self._model))
        return LLMResponse(
            event_id="",
            content=content,
            model=model_name,
            tokens_used=tokens,
            latency_ms=latency,
            timestamp=datetime.now(UTC),
        )

    def is_available(self) -> bool:
        return bool(self._basic)

    async def preflight_oauth(self) -> None:
        """Предстартовая проверка: получение токена OAuth. Рейз при сетевой/авторизационной ошибке."""
        await self._ensure_token()
