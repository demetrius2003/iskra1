"""Console output — Rich (цвета) или plain."""

from __future__ import annotations

import re
import sys
from datetime import datetime

from iskra.models import StateSnapshot

_HTTP_URL_RE = re.compile(r"https?://[^\s<>\[\]]+", re.IGNORECASE)

_STYLE_BORDER = "bold bright_cyan"
_STYLE_TIME = "dim white"
_STYLE_BRACKET = "dim"
_STYLE_MIND_LABEL = "bold white"
_STYLE_TRIGGER = "bold magenta"
_STYLE_ID = "dim"
_STYLE_STATE_LABEL = "bold bright_blue"
_STYLE_STATE_KEY = "bold cyan"
_STYLE_STATE_EQ = "dim white"
_STYLE_STATE_VAL = "bright_green"
_STYLE_THOUGHT = "yellow"
_STYLE_URL = "underline bright_cyan"


def _url_core_and_trailer(raw: str) -> tuple[str, str]:
    core = raw.rstrip(".,;:!?)]}\"'")
    return core, raw[len(core) :]


def _try_print_rich(
    *,
    line_top: str,
    line_mid: str,
    ts_str: str,
    show_ts: bool,
    show_trigger_type: bool,
    trigger_type: str,
    event_id: str,
    show_state: bool,
    state_snapshot: StateSnapshot,
    thought: str,
    rich_console: object,
) -> bool:
    try:
        from rich.console import Console
        from rich.text import Text
    except ImportError:
        return False

    if not isinstance(rich_console, Console):
        return False

    def append_thought(text_obj: Text, body: str, *, style: str) -> None:
        pos = 0
        for m in _HTTP_URL_RE.finditer(body):
            if m.start() > pos:
                text_obj.append(body[pos : m.start()], style=style)
            raw_u = m.group(0)
            core, trailer = _url_core_and_trailer(raw_u)
            if core:
                text_obj.append(core, style=_STYLE_URL)
            if trailer:
                text_obj.append(trailer, style=style)
            pos = m.end()
        if pos < len(body):
            text_obj.append(body[pos:], style=style)

    out = Text()

    out.append(line_top + "\n", style=_STYLE_BORDER)
    if show_ts:
        out.append("[", style=_STYLE_BRACKET)
        out.append(ts_str, style=_STYLE_TIME)
        out.append("] ", style=_STYLE_BRACKET)
    out.append("Мысль", style=_STYLE_MIND_LABEL)
    if show_trigger_type:
        out.append(" ", style=_STYLE_MIND_LABEL)
        out.append("(", style=_STYLE_TRIGGER)
        out.append(trigger_type, style=_STYLE_TRIGGER)
        out.append(")", style=_STYLE_TRIGGER)
    out.append(f"  id={event_id[:8]}…", style=_STYLE_ID)
    out.append("\n")

    out.append(line_mid + "\n", style=_STYLE_BORDER)

    if show_state and state_snapshot:
        out.append("Состояние: ", style=_STYLE_STATE_LABEL)
        first = True
        for k, v in sorted(state_snapshot.items()):
            if not first:
                out.append(" ")
            first = False
            out.append(k, style=_STYLE_STATE_KEY)
            out.append("=", style=_STYLE_STATE_EQ)
            out.append(f"{float(v):.2f}", style=_STYLE_STATE_VAL)
        out.append("\n")

    out.append("\n")
    append_thought(out, thought, style=_STYLE_THOUGHT)
    out.append("\n")
    out.append(line_top + "\n", style=_STYLE_BORDER)

    rich_console.print(out)
    return True


class ConsoleOutput:
    name = "console"

    def __init__(self, settings: dict) -> None:
        self._use_rich = bool(settings.get("use_rich", True))
        self._show_state = bool(settings.get("show_state", True))
        self._show_trigger = bool(settings.get("show_trigger_type", True))
        self._show_ts = bool(settings.get("show_timestamp", True))
        self._rich_console: object | None = None

    def _get_rich_console(self) -> object | None:
        if self._rich_console is not None:
            return self._rich_console
        try:
            from rich.console import Console

            self._rich_console = Console(stderr=False, highlight=False)
        except ImportError:
            self._rich_console = False  # sentinel: пробовали и не вышло
        return self._rich_console

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

        if self._use_rich:
            rc = self._get_rich_console()
            if rc not in (None, False):
                ok = _try_print_rich(
                    line_top=line_top,
                    line_mid=line_mid,
                    ts_str=ts_str,
                    show_ts=self._show_ts,
                    show_trigger_type=self._show_trigger,
                    trigger_type=trigger_type,
                    event_id=event_id,
                    show_state=self._show_state,
                    state_snapshot=state_snapshot,
                    thought=thought,
                    rich_console=rc,
                )
                if ok:
                    return

        parts: list[str] = [line_top]
        mt = f"Мысль ({trigger_type})" if self._show_trigger else "Мысль"
        if self._show_ts:
            parts.append(f"[{ts_str}] {mt}  id={event_id[:8]}…")
        else:
            parts.append(mt)
        parts.append(line_mid)
        if self._show_state and state_snapshot:
            state_s = " ".join(f"{k}={v:.2f}" for k, v in sorted(state_snapshot.items()))
            parts.append(f"Состояние: {state_s}")
        parts.append("")
        parts.append(thought)
        parts.append(line_top)
        print("\n".join(parts), file=sys.stdout)
