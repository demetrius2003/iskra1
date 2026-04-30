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


def test_memory_backend_v2_invariant() -> None:
    from iskra.core.config import MemoryConfig, MemoryV2Config

    with pytest.raises(ValueError, match="v2.enabled"):
        MemoryConfig(backend="sqlite", v2=MemoryV2Config(enabled=True))
    with pytest.raises(ValueError, match="v2.enabled"):
        MemoryConfig(backend="lance", v2=MemoryV2Config(enabled=False))


def test_memory_v2_embeddings_backend_invalid() -> None:
    from iskra.core.config import MemoryV2Config

    with pytest.raises(ValueError, match="embeddings_backend"):
        MemoryV2Config(embeddings_backend="nope")


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


def test_validate_self_reflection_requires_user_prompt() -> None:
    from iskra.core.config import GeneralConfig, IntentConfig, MemoryConfig, StateConfig, TriggerConfig, TriggerIntervalConfig, TriggerTypeConfig
    from iskra.core.config import StateVariableConfig

    state = StateConfig(
        variables={"x": StateVariableConfig(initial=0.5, mu=0.5, theta=0.1, sigma=0.1)},
        impulses={},
        feedback={},
    )
    trig = TriggerConfig(
        interval=TriggerIntervalConfig(min_seconds=1, max_seconds=10, modulated_by=None),
        types={"t": TriggerTypeConfig(base_weight=1.0)},
        random_topic_pool=[],
    )
    gen = GeneralConfig(self_reflection_every_n_ticks=10)
    cfg = IskraConfig(
        schema_version=1,
        state=state,
        trigger=trig,
        memory=MemoryConfig(),
        intent=IntentConfig(system_prompt_template="s", user_prompts={"default": "d"}),
        general=gen,
    )
    with pytest.raises(ValueError, match="self_reflection"):
        validate_cross_config(cfg)

    cfg_ok = cfg.model_copy(
        update={
            "intent": IntentConfig(
                system_prompt_template="s",
                user_prompts={"default": "d", "self_reflection": "x"},
            )
        }
    )
    validate_cross_config(cfg_ok)
