"""Настройка корневого логирования: ANSI-подсветка строк HTTP-клиента ``primp`` (голубой)."""

from __future__ import annotations

import logging
import os
import sys


ANSI_CYAN = "\033[96m"
ANSI_BRIGHT_CYAN = "\033[1;96m"
ANSI_RESET = "\033[0m"


def _stderr_supports_color() -> bool:
    if os.environ.get("ISKRA_NO_LOG_COLORS", "").strip().lower() in ("1", "true", "yes"):
        return False
    try:
        return sys.stderr.isatty()
    except ValueError:
        return False


def _enable_windows_ansi_if_needed() -> None:
    if sys.platform != "win32":
        return
    try:
        import colorama

        colorama.just_fix_windows_console()
        return
    except ImportError:
        pass

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        STD_ERROR_HANDLE = -12
        h = kernel32.GetStdHandle(STD_ERROR_HANDLE)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(h, ctypes.byref(mode)) == 0:
            return
        kernel32.SetConsoleMode(h, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)
    except Exception:
        pass


class PrimpHighlightFormatter(logging.Formatter):
    """Строки логгера ``primp`` (ответы Bing и т.п.) — голубые."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        name = record.name or ""
        if name == "primp" or name.startswith("primp."):
            return f"{ANSI_BRIGHT_CYAN}{base}{ANSI_RESET}"
        return base


def configure_root_logging(level: int, fmt: str, *, color_primp: bool = True) -> None:
    """Один потоковый handler на stderr; при ``color_primp`` и TTY — подсветка ``primp``."""
    root = logging.root
    root.handlers.clear()
    root.setLevel(level)

    handler = logging.StreamHandler(sys.stderr)
    use_fmt: logging.Formatter
    if color_primp and _stderr_supports_color():
        _enable_windows_ansi_if_needed()
        use_fmt = PrimpHighlightFormatter(fmt)
    else:
        use_fmt = logging.Formatter(fmt)
    handler.setFormatter(use_fmt)
    root.addHandler(handler)
