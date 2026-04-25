"""Stable symbols exported from ``iskra`` (library contract)."""

import iskra


def test_all_exports_match_module() -> None:
    for name in iskra.__all__:
        assert hasattr(iskra, name), f"missing: {name}"


def test_version() -> None:
    assert iskra.__version__
    major, minor, patch = iskra.__version__.split(".")
    int(major)
    int(minor)
    int(patch)
