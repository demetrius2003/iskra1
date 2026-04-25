"""Pydantic models and YAML config loading."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# --- Nested config models ---


class StateVariableConfig(BaseModel):
    initial: float = Field(ge=0.0, le=1.0)
    mu: float = Field(ge=0.0, le=1.0)
    theta: float = Field(gt=0.0)
    sigma: float = Field(gt=0.0)


class FeedbackRuleConfig(BaseModel):
    """condition + arbitrary float fields (variable deltas)."""

    model_config = ConfigDict(extra="allow")
    condition: str

    def deltas(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for k, v in self.model_dump().items():
            if k == "condition":
                continue
            if isinstance(v, (int, float)):
                out[k] = float(v)
        return out


class StateConfig(BaseModel):
    variables: dict[str, StateVariableConfig]
    impulses: dict[str, dict[str, float]] = Field(default_factory=dict)
    feedback: dict[str, FeedbackRuleConfig] = Field(default_factory=dict)

    @field_validator("variables")
    @classmethod
    def at_least_one_variable(cls, v: dict[str, StateVariableConfig]) -> dict[str, StateVariableConfig]:
        if len(v) == 0:
            raise ValueError("At least one state variable required")
        return v


class TriggerIntervalConfig(BaseModel):
    min_seconds: int = Field(ge=1)
    max_seconds: int = Field(ge=1)
    modulated_by: str | None = None

    @model_validator(mode="after")
    def max_ge_min(self) -> TriggerIntervalConfig:
        if self.max_seconds < self.min_seconds:
            raise ValueError("trigger.interval.max_seconds must be >= min_seconds")
        return self


class TriggerTypeConfig(BaseModel):
    base_weight: float = Field(gt=0.0)
    modulated_by: str | None = None
    modulation_strength: float = 0.0
    context_source: str | None = None


class TriggerConfig(BaseModel):
    interval: TriggerIntervalConfig
    types: dict[str, TriggerTypeConfig]
    random_topic_pool: list[str] = Field(default_factory=list)


class MemoryRecallConfig(BaseModel):
    default_n: int = Field(ge=1, default=3)
    importance_weight: float = Field(ge=0.0, le=1.0, default=0.7)
    recency_weight: float = Field(ge=0.0, le=1.0, default=0.3)
    selection: str = "stochastic"


class MemoryDecayConfig(BaseModel):
    enabled: bool = True
    base_rate: float = Field(ge=0.0, default=0.01)
    min_importance: float = Field(ge=0.0, le=1.0, default=0.01)
    recall_protection: float = Field(ge=1.0, default=1.5)


class MemoryConfig(BaseModel):
    backend: str = "sqlite"
    settings: dict = Field(default_factory=dict)
    recall: MemoryRecallConfig = Field(default_factory=MemoryRecallConfig)
    decay: MemoryDecayConfig = Field(default_factory=MemoryDecayConfig)
    initial_memories_file: str | None = None


class IntentConfig(BaseModel):
    system_prompt_template: str
    user_prompts: dict[str, str]
    max_response_tokens: int = 500


class LLMRetryConfig(BaseModel):
    max_attempts: int = Field(ge=1, default=3)
    backoff_base_seconds: float = Field(ge=0.1, default=1.0)


class LLMConfig(BaseModel):
    adapter: str = "mock"
    settings: dict = Field(default_factory=dict)
    temperature: float = Field(ge=0.0, le=2.0, default=0.9)
    max_tokens: int = Field(ge=1, default=500)
    retry: LLMRetryConfig = Field(default_factory=LLMRetryConfig)
    cooldown_on_rate_limit_seconds: int = 300


class OutputConfig(BaseModel):
    channel: str = "console"
    settings: dict = Field(default_factory=dict)


class EventLogConfig(BaseModel):
    enabled: bool = True
    path: str = "data/events.jsonl"
    rotate_mb: int = 100


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    event_log: EventLogConfig = Field(default_factory=EventLogConfig)


class GeneralConfig(BaseModel):
    decay_every_n_ticks: int = Field(ge=1, default=10)
    tick_jitter: float = Field(ge=0.0, le=1.0, default=0.1)
    data_dir: str = "data"
    pid_file: str = "data/iskra.pid"
    preflight: bool = True
    """Перед стартом: проверка памяти, путей, доступности LLM (mock пропускает сеть)."""
    external_input_file: str | None = None
    """Путь к UTF-8 файлу: перед тиком читаем непустой текст — в промпт (Jinja: ``external_input``) и импульс ``user_message``; пусто = ничего не делаем."""
    external_input_max_chars: int = Field(8000, ge=1, le=500_000)
    external_input_clear_after_use: bool = True
    """После успешного ответа и вывода очистить файл (иначе тот же текст повторится на следующем тике)."""


class IskraConfig(BaseModel):
    schema_version: int = 1
    state: StateConfig
    trigger: TriggerConfig
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    intent: IntentConfig
    llm: LLMConfig = Field(default_factory=LLMConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    general: GeneralConfig = Field(default_factory=GeneralConfig)


def _substitute_env_in_str(raw: str) -> str:
    def replace_env(match: re.Match[str]) -> str:
        var = match.group(1)
        value = os.environ.get(var)
        if value is None:
            raise ValueError(f"Environment variable {var} is not set")
        return value

    return re.sub(r"\$\{(\w+)\}", replace_env, raw)


def _deep_substitute_env(obj: object) -> object:
    """Apply ``${VAR}`` only inside YAML *values* (comments in the file are not parsed)."""
    if isinstance(obj, str):
        return _substitute_env_in_str(obj)
    if isinstance(obj, dict):
        return {k: _deep_substitute_env(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_substitute_env(x) for x in obj]
    return obj


def validate_cross_config(cfg: IskraConfig) -> None:
    """Cross-field checks from FORMAL_SPEC §7.3."""
    var_names = set(cfg.state.variables.keys())
    mod = cfg.trigger.interval.modulated_by
    if mod is not None and mod not in var_names:
        raise ValueError(f"trigger.interval.modulated_by '{mod}' not in state.variables")
    for tname, tcfg in cfg.trigger.types.items():
        if tcfg.modulated_by is not None and tcfg.modulated_by not in var_names:
            raise ValueError(
                f"trigger.types.{tname}.modulated_by '{tcfg.modulated_by}' not in state.variables"
            )
    for rule_name, rule in cfg.state.feedback.items():
        for vn in rule.deltas():
            if vn not in var_names:
                raise ValueError(
                    f"state.feedback.{rule_name} references unknown variable '{vn}'"
                )
    if "default" not in cfg.intent.user_prompts:
        raise ValueError('intent.user_prompts must contain key "default"')
    if cfg.trigger.random_topic_pool is not None and len(cfg.trigger.random_topic_pool) == 0:
        if "new_topic" in cfg.trigger.types:
            raise ValueError("random_topic_pool must be non-empty when new_topic trigger is used")


def load_config(path: str | Path) -> IskraConfig:
    """Load and validate ``config.yaml``. Raises on error (no ``sys.exit``).

    * ``FileNotFoundError`` — path is not a file
    * ``yaml.YAMLError`` — invalid YAML
    * ``pydantic.ValidationError`` — invalid model
    * ``ValueError`` — cross-field checks, empty config, env substitution, etc.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Config file not found: {p}")
    raw = p.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if data is None:
        raise ValueError("Configuration YAML is empty or null")
    data = cast(Any, _deep_substitute_env(data))
    cfg = IskraConfig.model_validate(data)
    validate_cross_config(cfg)
    return cfg
