"""Console output — Rich or plain."""

from __future__ import annotations

import sys
from datetime import datetime

from iskra.models import StateSnapshot


class ConsoleOutput:
    name = "console"

    def __init__(self, settings: dict) -> None:
        self._use_rich = bool(settings.get("use_rich", True))
        self._show_state = bool(settings.get("show_state", True))
        self._show_trigger = bool(settings.get("show_trigger_type", True))
        self._show_ts = bool(settings.get("show_timestamp", True))

    async def emit(
        self,
        event_id: str,
        thought: str,
        trigger_type: str,
        state_snapshot: StateSnapshot,
        timestamp: datetime,
    ) -> None:
        ts_str = timestamp.strftime("%Y-%m-%d %H:%M:%S") if self._show_ts else ""
        line_top = "═" * 55
        line_mid = "─" * 55
        parts: list[str] = [line_top]
        if self._show_ts:
            parts.append(f"[{ts_str}] Мысль ({trigger_type})  id={event_id[:8]}…")
        else:
            parts.append(f"Мысль ({trigger_type})")
        parts.append(line_mid)
        if self._show_state and state_snapshot:
            state_s = " ".join(f"{k}={v:.2f}" for k, v in sorted(state_snapshot.items()))
            parts.append(f"Состояние: {state_s}")
        parts.append("")
        parts.append(thought)
        parts.append(line_top)
        text = "\n".join(parts)

        if self._use_rich:
            try:
                from rich.console import Console

                Console(stderr=False).print(text)
                return
            except Exception:
                pass
        print(text, file=sys.stdout)
