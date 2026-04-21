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
