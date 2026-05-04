"""Контракт строки ``events.jsonl`` (схема + round-trip с EventLogEntry)."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from iskra.event_log_schema import EventLogLineModel, validate_event_log_line_json
from iskra.models import EventLogEntry


def test_validate_event_log_line_roundtrip() -> None:
    entry = EventLogEntry(
        event_id="e1",
        timestamp="2026-04-28T12:00:00Z",
        trigger_type="new_topic",
        state_before={"curiosity": 0.5},
        state_after={"curiosity": 0.52},
        memory_ids_recalled=[],
        prompt_system="sys",
        prompt_user="usr",
        llm_response="hello",
        llm_model="mock",
        llm_tokens=3,
        llm_latency_ms=10,
        memory_id_stored="550e8400-e29b-41d4-a716-446655440000",
        output_channel="console",
        errors=[],
    )
    line = json.dumps(asdict(entry), ensure_ascii=False)
    parsed = validate_event_log_line_json(line)
    assert parsed.event_id == entry.event_id
    assert parsed.llm_response == "hello"
    assert parsed.memory_id_stored == entry.memory_id_stored


def test_validate_event_log_line_rejects_extra_keys() -> None:
    payload = {
        "event_id": "x",
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "trigger_type": "",
        "state_before": {},
        "state_after": {},
        "memory_ids_recalled": [],
        "prompt_system": "",
        "prompt_user": "",
        "llm_response": "",
        "llm_model": "",
        "llm_tokens": 0,
        "llm_latency_ms": 0,
        "memory_id_stored": None,
        "output_channel": "",
        "errors": [],
        "unexpected": 1,
    }
    with pytest.raises(ValidationError):
        EventLogLineModel.model_validate(payload)
