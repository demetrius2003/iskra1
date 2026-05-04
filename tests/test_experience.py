"""Дашборд, резюме и разбор JSONL (experience CLI)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from iskra.experience import (
    build_daily_summary_text,
    build_dashboard_html,
    load_events_last_hours,
    write_dashboard,
    write_daily_summary,
)


def _sample_row(**kwargs: object) -> str:
    base = {
        "event_id": "e1",
        "timestamp": "2026-04-28T12:00:00Z",
        "trigger_type": "new_topic",
        "state_before": {"curiosity": 0.5},
        "state_after": {"curiosity": 0.52},
        "memory_ids_recalled": [],
        "prompt_system": "s",
        "prompt_user": "u",
        "llm_response": "hello",
        "llm_model": "mock",
        "llm_tokens": 3,
        "llm_latency_ms": 10,
        "memory_id_stored": None,
        "output_channel": "console",
        "errors": [],
    }
    base.update(kwargs)
    return json.dumps(base, ensure_ascii=False)


def test_load_events_last_hours_filters_old(tmp_path: Path) -> None:
    p = tmp_path / "ev.jsonl"
    old_ts = (datetime.now(UTC) - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    p.write_text(
        _sample_row(timestamp=old_ts, trigger_type="old") + "\n"
        + _sample_row(timestamp=new_ts, trigger_type="fresh", event_id="e2")
        + "\n",
        encoding="utf-8",
    )
    rows = load_events_last_hours(p, hours=24.0, now=datetime.now(UTC))
    assert len(rows) == 1
    assert rows[0].trigger_type == "fresh"


def test_dashboard_html_contains_chartjs(tmp_path: Path) -> None:
    p = tmp_path / "ev.jsonl"
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    p.write_text(_sample_row(timestamp=ts) + "\n", encoding="utf-8")
    rows = load_events_last_hours(p, hours=24.0, now=datetime.now(UTC))
    html = build_dashboard_html(rows)
    assert "chart.js" in html.lower() or "chart.umd" in html.lower()
    assert "chartTriggers" in html


def test_summary_text_lists_triggers(tmp_path: Path) -> None:
    p = tmp_path / "ev.jsonl"
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    p.write_text(
        _sample_row(timestamp=ts, trigger_type="new_topic")
        + "\n"
        + _sample_row(timestamp=ts, trigger_type="recall_memory", event_id="x")
        + "\n",
        encoding="utf-8",
    )
    rows = load_events_last_hours(p, hours=24.0, now=datetime.now(UTC))
    text = build_daily_summary_text(rows, window_label="test")
    assert "new_topic" in text
    assert "recall_memory" in text
    assert "Записей в окне: 2" in text


def test_write_dashboard_and_summary_outputs(tmp_path: Path) -> None:
    p = tmp_path / "ev.jsonl"
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    p.write_text(_sample_row(timestamp=ts) + "\n", encoding="utf-8")
    dash_out = tmp_path / "d.html"
    sum_out = tmp_path / "s.txt"
    assert write_dashboard(events_path=p, output_path=dash_out, hours=24.0) == 1
    assert write_daily_summary(events_path=p, output_path=sum_out, hours=24.0) == 1
    assert dash_out.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")
    assert "Iskra-1" in sum_out.read_text(encoding="utf-8")
