"""Dataclasses shared across components."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

StateSnapshot = dict[str, float]


@dataclass(frozen=True)
class SparkEvent:
    id: str = field(default_factory=lambda: str(uuid4()))
    trigger_type: str = ""
    state_snapshot: dict[str, float] = field(default_factory=dict)
    memory_context: list[MemoryRecord] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryRecord:
    id: str
    timestamp: datetime
    category: str
    content: str
    importance: float
    last_recall: datetime
    recall_count: int
    decay_rate: float
    emotional_valence: float = 0.0  # [-1, 1] приятность переживания
    arousal: float = 0.5  # [0, 1] интенсивность / возбуждённость


@dataclass(frozen=True)
class IntentPayload:
    event_id: str
    system_prompt: str
    user_prompt: str
    trigger_type: str
    timestamp: datetime


@dataclass(frozen=True)
class LLMResponse:
    event_id: str
    content: str
    model: str
    tokens_used: int
    latency_ms: int
    timestamp: datetime


@dataclass
class EventLogEntry:
    event_id: str
    timestamp: str
    trigger_type: str
    state_before: dict[str, float]
    state_after: dict[str, float]
    memory_ids_recalled: list[str]
    prompt_system: str
    prompt_user: str
    llm_response: str
    llm_model: str
    llm_tokens: int
    llm_latency_ms: int
    memory_id_stored: str | None
    output_channel: str
    errors: list[str]
