"""Append-only JSONL event log with optional size-based rotation."""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

from iskra.core.config import EventLogConfig
from iskra.models import EventLogEntry

logger = logging.getLogger("iskra.event_log")


class EventLog:
    def __init__(self, config: EventLogConfig) -> None:
        self._cfg = config
        self._path = Path(config.path)

    def _maybe_rotate(self) -> None:
        if not self._path.is_file():
            return
        max_bytes = self._cfg.rotate_mb * 1024 * 1024
        if self._path.stat().st_size < max_bytes:
            return
        for i in range(9, 0, -1):
            older = self._path.with_name(f"{self._path.name}.{i}")
            newer = self._path.with_name(f"{self._path.name}.{i + 1}")
            if older.is_file():
                if newer.is_file():
                    newer.unlink(missing_ok=True)
                older.rename(newer)
        first = self._path.with_name(f"{self._path.name}.1")
        if first.is_file():
            first.unlink(missing_ok=True)
        self._path.rename(first)

    def record(self, entry: EventLogEntry) -> None:
        if not self._cfg.enabled:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._maybe_rotate()
            line = json.dumps(asdict(entry), ensure_ascii=False)
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as e:
            sys.stderr.write(f"event_log write failed: {e}\n")

    def record_error(self, event_id: str, error_msg: str) -> None:
        from datetime import UTC, datetime

        self.record(
            EventLogEntry(
                event_id=event_id,
                timestamp=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                trigger_type="",
                state_before={},
                state_after={},
                memory_ids_recalled=[],
                prompt_system="",
                prompt_user="",
                llm_response="",
                llm_model="",
                llm_tokens=0,
                llm_latency_ms=0,
                memory_id_stored=None,
                output_channel="",
                errors=[error_msg],
            )
        )
