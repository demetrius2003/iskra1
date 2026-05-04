"""Схема одной строки ``events.jsonl`` для валидации и внешних инструментов."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class EventLogLineModel(BaseModel):
    """Структура JSON-строки лога (как ``dataclasses.asdict(EventLogEntry)`` при записи)."""

    model_config = ConfigDict(extra="forbid")

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


def validate_event_log_line_json(line: str) -> EventLogLineModel:
    """Разобрать и проверить одну строку JSONL."""
    return EventLogLineModel.model_validate_json(line.strip())


def validate_event_log_line_dict(data: object) -> EventLogLineModel:
    """Проверить уже загруженный объект (например ``json.loads``)."""
    return EventLogLineModel.model_validate(data)
