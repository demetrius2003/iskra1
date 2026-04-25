"""Config loading and validation."""

from pathlib import Path

import pytest

from iskra.core.config import IskraConfig, load_config, validate_cross_config


def test_load_minimal() -> None:
    root = Path(__file__).resolve().parent
    cfg = load_config(root / "minimal.yaml")
    assert isinstance(cfg, IskraConfig)
    assert cfg.llm.adapter == "mock"
    assert "default" in cfg.intent.user_prompts


def test_load_config_missing_file() -> None:
    with pytest.raises(FileNotFoundError, match="Config file not found"):
        load_config("/nonexistent/iskra/config-does-not-exist.yaml")


def test_load_config_does_not_substitute_in_yaml_comments(tmp_path: Path) -> None:
    """``${VAR}`` in ``#`` comments must not be expanded (PyYAML drops comments)."""
    root = Path(__file__).resolve().parent
    base = (root / "minimal.yaml").read_text(encoding="utf-8")
    p = tmp_path / "with_comment.yaml"
    p.write_text(
        '# Example: secrets via ${NOT_A_REAL_VAR} in real values only\n' + base,
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert isinstance(cfg, IskraConfig)


def test_validate_modulated_by_unknown() -> None:
    from iskra.core.config import StateConfig, StateVariableConfig, TriggerConfig, TriggerIntervalConfig, TriggerTypeConfig

    state = StateConfig(
        variables={"x": StateVariableConfig(initial=0.5, mu=0.5, theta=0.1, sigma=0.1)},
        impulses={},
        feedback={},
    )
    trig = TriggerConfig(
        interval=TriggerIntervalConfig(min_seconds=1, max_seconds=10, modulated_by="nope"),
        types={"t": TriggerTypeConfig(base_weight=1.0)},
        random_topic_pool=["a"],
    )
    from iskra.core.config import IntentConfig

    cfg = IskraConfig(
        schema_version=1,
        state=state,
        trigger=trig,
        intent=IntentConfig(system_prompt_template="x", user_prompts={"default": "d"}),
    )
    with pytest.raises(ValueError, match="modulated_by"):
        validate_cross_config(cfg)
