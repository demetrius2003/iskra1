"""State engine: кламп переменных (в т.ч. bipolar)."""

from iskra.core.config import FeedbackRuleConfig, StateConfig, StateVariableConfig
from iskra.core.state_engine import OUStateEngine


def test_bipolar_valence_clamp() -> None:
    cfg = StateConfig(
        variables={
            "emotional_valence": StateVariableConfig(
                clamp_min=-1.0,
                clamp_max=1.0,
                initial=0.0,
                mu=0.0,
                theta=0.1,
                sigma=0.05,
            ),
        },
        impulses={"pulse": {"emotional_valence": 2.0}},
        feedback={},
    )
    eng = OUStateEngine(cfg)
    eng.apply_impulse("pulse")
    v = eng.snapshot()["emotional_valence"]
    assert -1.0 <= v <= 1.0
    assert v > 0.0


def test_feedback_respects_clamp() -> None:
    cfg = StateConfig(
        variables={
            "x": StateVariableConfig(
                clamp_min=-1.0,
                clamp_max=1.0,
                initial=0.9,
                mu=0.0,
                theta=0.1,
                sigma=0.01,
            ),
        },
        impulses={},
        feedback={
            "big": FeedbackRuleConfig(condition="length_lt_9999", x=-5.0),
        },
    )
    eng = OUStateEngine(cfg)
    eng.apply_feedback("t", "hi")
    assert eng.snapshot()["x"] == -1.0
