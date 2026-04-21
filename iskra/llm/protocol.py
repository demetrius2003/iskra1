"""LLM adapter protocol and errors."""

from typing import Protocol

from iskra.models import LLMResponse


class LLMError(Exception):
    pass


class LLMTimeoutError(LLMError):
    pass


class LLMRateLimitError(LLMError):
    pass


class LLMNetworkError(LLMError):
    pass


class LLMAdapter(Protocol):
    async def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse: ...
    def is_available(self) -> bool: ...
