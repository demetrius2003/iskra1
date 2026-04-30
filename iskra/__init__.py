"""Iskra-1 — autonomous inner loop for LLMs.

Stable API for downstream packages is defined in
``__all__`` and documented in ``docs/PUBLIC_API.md``."""

from iskra.core.config import IskraConfig, load_config, validate_cross_config
from iskra.core.main_loop import MainLoop
from iskra.core.preflight import PreflightError, preflight
from iskra.event_log import EventLog
from iskra.llm import create_llm_adapter
from iskra.llm.protocol import (
    LLMAdapter,
    LLMError,
    LLMNetworkError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from iskra.memory import create_memory_store
from iskra.memory.protocol import MemoryStore
from iskra.models import (
    EventLogEntry,
    IntentPayload,
    LLMResponse,
    MemoryRecord,
    SparkEvent,
    StateSnapshot,
)
from iskra.output import create_output_channel
from iskra.output.protocol import OutputChannel
from iskra.triggers import create_trigger_types
from iskra.triggers.protocol import TriggerType

__version__ = "0.4.4"

__all__ = [
    "__version__",
    "EventLog",
    "EventLogEntry",
    "IntentPayload",
    "IskraConfig",
    "LLMResponse",
    "LLMAdapter",
    "LLMError",
    "LLMNetworkError",
    "LLMRateLimitError",
    "LLMTimeoutError",
    "MainLoop",
    "MemoryRecord",
    "PreflightError",
    "MemoryStore",
    "OutputChannel",
    "SparkEvent",
    "StateSnapshot",
    "TriggerType",
    "create_llm_adapter",
    "create_memory_store",
    "create_output_channel",
    "create_trigger_types",
    "load_config",
    "preflight",
    "validate_cross_config",
]
