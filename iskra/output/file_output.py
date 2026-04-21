"""Append thoughts to a log file."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from iskra.models import StateSnapshot


class FileOutput:
    name = "file"

    def __init__(self, settings: dict) -> None:
        self._path = Path(settings.get("path", "data/thoughts.log"))
        self._format = settings.get("format", "text")

    async def emit(
        self,
        event_id: str,
        thought: str,
        trigger_type: str,
        state_snapshot: StateSnapshot,
        timestamp: datetime,
    ) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        ts = timestamp.isoformat()
        if self._format == "json":
            import json

            line = json.dumps(
                {
                    "event_id": event_id,
                    "timestamp": ts,
                    "trigger_type": trigger_type,
                    "state": state_snapshot,
                    "thought": thought,
                },
                ensure_ascii=False,
            )
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        else:
            state_s = " ".join(f"{k}={v:.2f}" for k, v in sorted(state_snapshot.items()))
            block = (
                f"{'═' * 55}\n[{ts}] {trigger_type} id={event_id}\n{state_s}\n\n{thought}\n"
            )
            with self._path.open("a", encoding="utf-8") as f:
                f.write(block + "\n")
