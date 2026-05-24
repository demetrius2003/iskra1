"""OU process state engine."""

from __future__ import annotations

import logging
import math
import random
import re

from iskra.core.config import FeedbackRuleConfig, StateConfig
from iskra.models import StateSnapshot

logger = logging.getLogger("iskra.core.state")


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def evaluate_condition(cond: str, trigger_type: str, response: str) -> bool:
    if cond == "ends_with_question_mark":
        return response.rstrip().endswith("?")
    m = re.match(r"length_lt_(\d+)", cond)
    if m:
        return len(response) < int(m.group(1))
    m = re.match(r"length_gt_(\d+)", cond)
    if m:
        return len(response) > int(m.group(1))
    m = re.match(r"trigger_type_eq_(\w+)", cond)
    if m:
        return trigger_type == m.group(1)
    logger.warning("unknown feedback condition: %s", cond)
    return False


class OUStateEngine:
    def __init__(self, config: StateConfig) -> None:
        self._cfg = config
        self._vars: dict[str, float] = {
            name: vc.initial for name, vc in config.variables.items()
        }

    def tick(self, elapsed_seconds: float) -> None:
        if elapsed_seconds < 0:
            return
        dt = elapsed_seconds / 60.0
        sqrt_dt = math.sqrt(dt) if dt > 0 else 0.0
        for name, vc in self._cfg.variables.items():
            x = self._vars[name]
            noise = random.gauss(0.0, 1.0)
            dx = vc.theta * (vc.mu - x) * dt + vc.sigma * sqrt_dt * noise
            self._vars[name] = _clamp(x + dx, vc.clamp_min, vc.clamp_max)

    def apply_impulse(self, event_type: str) -> None:
        impulses = self._cfg.impulses.get(event_type, {})
        for var_name, delta in impulses.items():
            if var_name not in self._vars:
                continue
            vc = self._cfg.variables[var_name]
            self._vars[var_name] = _clamp(
                self._vars[var_name] + float(delta), vc.clamp_min, vc.clamp_max
            )

    def apply_feedback(self, trigger_type: str, llm_response: str) -> None:
        for _rule_name, rule in self._cfg.feedback.items():
            self._apply_rule(rule, trigger_type, llm_response)

    def apply_variable_deltas(self, deltas: dict[str, float]) -> None:
        """Прибавить дельты к переменным состояния с клампом (сенсоры мира, погода и т.д.)."""
        for var_name, delta in deltas.items():
            if var_name not in self._vars:
                continue
            vc = self._cfg.variables[var_name]
            self._vars[var_name] = _clamp(
                self._vars[var_name] + float(delta), vc.clamp_min, vc.clamp_max
            )

    def blend_emotion_toward_sample(
        self,
        sample_valence: float,
        sample_arousal: float,
        *,
        valence_blend: float,
        arousal_blend: float,
    ) -> None:
        """Подтянуть ``valence`` / ``arousal`` к оценке классификатора текста ответа."""
        if "valence" in self._vars and "valence" in self._cfg.variables:
            vc = self._cfg.variables["valence"]
            cur = self._vars["valence"]
            self._vars["valence"] = _clamp(
                cur + valence_blend * (sample_valence - cur), vc.clamp_min, vc.clamp_max
            )
        if "arousal" in self._vars and "arousal" in self._cfg.variables:
            vc = self._cfg.variables["arousal"]
            cur = self._vars["arousal"]
            self._vars["arousal"] = _clamp(
                cur + arousal_blend * (sample_arousal - cur), vc.clamp_min, vc.clamp_max
            )

    def _apply_rule(self, rule: FeedbackRuleConfig, trigger_type: str, llm_response: str) -> None:
        if not evaluate_condition(rule.condition, trigger_type, llm_response):
            return
        for var_name, delta in rule.deltas().items():
            if var_name not in self._vars:
                continue
            vc = self._cfg.variables[var_name]
            self._vars[var_name] = _clamp(
                self._vars[var_name] + float(delta), vc.clamp_min, vc.clamp_max
            )

    def snapshot(self) -> StateSnapshot:
        return dict(self._vars)

    def get(self, name: str) -> float:
        if name not in self._vars:
            raise KeyError(name)
        return self._vars[name]
