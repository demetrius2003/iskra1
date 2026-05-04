"""Подсветка primp в логах."""

import logging

from iskra.logging_support import PrimpHighlightFormatter


def test_primp_formatter_wraps_name() -> None:
    fmt = PrimpHighlightFormatter("%(name)s: %(message)s")
    rec = logging.LogRecord(
        name="primp",
        level=logging.INFO,
        pathname="x",
        lineno=1,
        msg="response: https://example.com 200",
        args=(),
        exc_info=None,
    )
    out = fmt.format(rec)
    assert "response:" in out
    assert "\033[" in out


def test_other_logger_plain() -> None:
    fmt = PrimpHighlightFormatter("%(name)s: %(message)s")
    rec = logging.LogRecord(
        name="iskra.core.main_loop",
        level=logging.INFO,
        pathname="x",
        lineno=1,
        msg="web_search: ok",
        args=(),
        exc_info=None,
    )
    out = fmt.format(rec)
    assert "\033[" not in out
