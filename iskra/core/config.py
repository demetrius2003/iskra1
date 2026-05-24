"""Pydantic models and YAML config loading."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# --- Nested config models ---


class StateVariableConfig(BaseModel):
    """OU-переменная; по умолчанию кламп [0, 1]. Для ``clamp_min``/``clamp_max`` см. valence [−1, 1]."""

    clamp_min: float = 0.0
    clamp_max: float = 1.0
    initial: float
    mu: float
    theta: float = Field(gt=0.0)
    sigma: float = Field(gt=0.0)

    @model_validator(mode="after")
    def initial_mu_in_clamp(self) -> StateVariableConfig:
        if self.clamp_max <= self.clamp_min:
            raise ValueError("state variable clamp_max must be > clamp_min")
        for label, val in ("initial", self.initial), ("mu", self.mu):
            if not (self.clamp_min <= val <= self.clamp_max):
                raise ValueError(f"{label} must be within [clamp_min, clamp_max]")
        return self


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
    random_topic_pool_file: str | None = None
    """Путь к YAML с темами; после загрузки конфига строки из файла **добавляются** после ``random_topic_pool``."""


class MemoryRecallConfig(BaseModel):
    default_n: int = Field(ge=1, default=3)
    importance_weight: float = Field(ge=0.0, le=1.0, default=0.7)
    recency_weight: float = Field(ge=0.0, le=1.0, default=0.3)
    selection: str = "stochastic"
    emotion_enabled: bool = True
    emotion_valence_alignment_weight: float = Field(default=0.15, ge=0.0, le=1.0)
    emotion_nostalgia_positive_weight: float = Field(default=0.10, ge=0.0, le=1.0)


class MemoryDecayConfig(BaseModel):
    enabled: bool = True
    base_rate: float = Field(ge=0.0, default=0.01)
    min_importance: float = Field(ge=0.0, le=1.0, default=0.01)
    recall_protection: float = Field(ge=1.0, default=1.5)


class MemoryV2Config(BaseModel):
    """Расширенное хранилище (Lance + эмбеддинги). См. docs/CONFIG_SCHEMA.md."""

    enabled: bool = False
    db_path: str = "data/memory_v2"
    embeddings_backend: str = "sentence_transformers"
    """``sentence_transformers`` (нужен PyTorch) или ``hash`` — псевдо-векторы без ML (Windows/Python без torch)."""
    embeddings_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    hash_embedding_dim: int = Field(default=384, ge=8, le=4096)
    """Размерность при ``embeddings_backend: hash`` (лучше совпадать с целевой моделью, напр. 384)."""
    graph_enabled: bool = True
    """Граф ассоциаций (NetworkX), файл рядом с Lance."""
    graph_edges_path: str | None = None
    """Путь к JSON с рёбрами; по умолчанию ``<db_path>/memory_graph.json``."""
    recall_graph_extra: int = Field(default=0, ge=0, le=32)
    """Добавить до N записей-соседей по графу к результату recall (после основного отбора)."""
    graph_link_increment: float = Field(default=1.0, gt=0.0, le=100.0)
    """На сколько увеличить вес ребра при каждом ``link_memories`` / теге ``links`` (новое ребро = этот инкремент)."""
    graph_max_edge_weight: float = Field(default=1000.0, ge=1.0)
    """Верхняя граница веса ребра (усиление ассоциации, слияние при ``repoint``)."""

    @field_validator("embeddings_backend")
    @classmethod
    def embeddings_backend_known(cls, v: str) -> str:
        allowed = ("sentence_transformers", "hash")
        if v not in allowed:
            raise ValueError(
                f"memory.v2.embeddings_backend must be one of {allowed}, got {v!r}"
            )
        return v


class MemoryConfig(BaseModel):
    backend: str = "sqlite"
    settings: dict = Field(default_factory=dict)
    recall: MemoryRecallConfig = Field(default_factory=MemoryRecallConfig)
    decay: MemoryDecayConfig = Field(default_factory=MemoryDecayConfig)
    initial_memories_file: str | None = None
    v2: MemoryV2Config = Field(default_factory=MemoryV2Config)

    @field_validator("backend")
    @classmethod
    def backend_known(cls, v: str) -> str:
        if v not in ("sqlite", "lance"):
            raise ValueError("memory.backend must be 'sqlite' or 'lance'")
        return v

    @model_validator(mode="after")
    def backend_v2_invariant(self) -> MemoryConfig:
        if self.backend == "sqlite" and self.v2.enabled:
            raise ValueError("memory.v2.enabled must be false when memory.backend is sqlite")
        if self.backend == "lance" and not self.v2.enabled:
            raise ValueError("memory.v2.enabled must be true when memory.backend is lance")
        return self


class AgencyConfig(BaseModel):
    """Уровень прав модели на операции с памятью по тегам (0–3)."""

    level: int = Field(default=1, ge=0, le=3)
    l2_importance_floor: float = Field(default=0.12, ge=0.0, le=1.0)
    """Уровень 2: ``MEMORY_UPDATE`` с ``importance`` не опускает ниже этого значения. Уровни 1 и 3 — без пола."""


class IntentConfig(BaseModel):
    system_prompt_template: str
    user_prompts: dict[str, str]
    max_response_tokens: int = 500


class WebSearchToolConfig(BaseModel):
    """DuckDuckGo-текст + сводка через LLM; зависимость: ``pip install duckduckgo-search`` или ``pip install ".[web]"`` из корня этого проекта."""

    enabled: bool = False
    max_results: int = Field(default=5, ge=1, le=25)
    summary_max_tokens: int = Field(default=300, ge=32, le=8000)
    max_per_tick: int = Field(default=1, ge=0, le=50)
    max_per_hour: int = Field(default=5, ge=0, le=500)
    memory_importance: float = Field(default=0.8, ge=0.0, le=1.0)
    memory_category: str = "web_research"
    log_snippet_count: bool = True
    """В лог INFO: сколько текстовых сниппетов вернул поиск до сводки LLM."""
    log_snippet_previews: bool = True
    """В лог INFO: превью сниппетов (сырой текст из поиска до сводки LLM)."""
    log_snippet_preview_limit: int = Field(default=5, ge=1, le=25)
    """Не более стольких сниппетов выводить превью (остальные только в счётчике)."""
    log_snippet_preview_chars: int = Field(default=280, ge=16, le=4000)
    """Обрезка одной строки превью сниппета для лога."""
    log_summary_preview_chars: int | None = Field(default=320, ge=32, le=4000)
    """Начало сводки LLM в лог INFO; задайте ``null``, чтобы отключить превью сводки."""


class ToolsConfig(BaseModel):
    web_search: WebSearchToolConfig = Field(default_factory=WebSearchToolConfig)


class WorldTimeSensorConfig(BaseModel):
    """Локальное время: импульсы только при смене слота (см. ``time_sensor.compute_slot``)."""

    enabled: bool = False
    check_interval_seconds: int = Field(default=300, ge=10, le=86_400)


class WorldWeatherConfig(BaseModel):
    provider: Literal["openweather", "open_meteo"] = "openweather"
    enabled: bool = False
    api_key: str | None = None
    city: str = "Moscow"
    lat: float | None = None
    lon: float | None = None
    update_interval_seconds: int = Field(default=3600, ge=60, le=86_400)

    @field_validator("api_key", mode="before")
    @classmethod
    def normalize_api_key(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip().strip('"').strip("'")
        for ch in ("\ufeff", "\u200b", "\u200c", "\u200d", "\xa0"):
            s = s.replace(ch, "")
        return s if s else None


class WorldRSSFeedConfig(BaseModel):
    name: str
    url: str
    category: str | None = None


class WorldRSSConfig(BaseModel):
    enabled: bool = False
    update_interval_seconds: int = Field(default=3600, ge=60, le=86_400)
    default_category: str = "news"
    max_items_per_feed: int = Field(default=5, ge=1, le=50)
    save_importance: float = Field(default=0.5, ge=0.0, le=1.0)
    feeds: list[WorldRSSFeedConfig] = Field(default_factory=list)


class WorldConfig(BaseModel):
    """Датчики «мира»: время, погода (OpenWeatherMap), RSS → память и строка для промпта."""

    context_max_chars: int = Field(default=1200, ge=200, le=50_000)
    time_sensor: WorldTimeSensorConfig = Field(default_factory=WorldTimeSensorConfig)
    weather: WorldWeatherConfig = Field(default_factory=WorldWeatherConfig)
    rss: WorldRSSConfig = Field(default_factory=WorldRSSConfig)


class SandboxPythonConfig(BaseModel):
    enabled: bool = True
    interpreter: str = "python"
    timeout_seconds: int = Field(default=30, ge=1, le=3600)
    max_output_bytes: int = Field(default=10_000, ge=256, le=2_000_000)


class SandboxFilesConfig(BaseModel):
    enabled: bool = True
    max_file_size_bytes: int = Field(default=102_400, ge=1024, le=20_000_000)
    allowed_extensions: list[str] = Field(
        default_factory=lambda: [".txt", ".md", ".py", ".json"]
    )
    list_recursive: bool = False


class SandboxConfig(BaseModel):
    """Песочница файлов и Python под ``sandbox.path`` (см. docs/TZ_ISKRA_0.7.0.md)."""

    enabled: bool = False
    path: str = "data/sandbox"
    memory_category: str = "sandbox_result"
    max_tag_ops_per_tick: int = Field(default=8, ge=1, le=100)
    python: SandboxPythonConfig = Field(default_factory=SandboxPythonConfig)
    files: SandboxFilesConfig = Field(default_factory=SandboxFilesConfig)


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
    highlight_primp_logs: bool = True
    """В консоли (TTY) строки логгера ``primp`` (HTTP-запросы поиска) подсвечивать голубым."""
    event_log: EventLogConfig = Field(default_factory=EventLogConfig)


class SelfReflectionInsightConfig(BaseModel):
    """Углублённая саморефлексия — сохранение сформулированного наблюдения в память."""

    enabled: bool = False
    importance: float = Field(default=0.85, ge=0.0, le=1.0)
    category: str = "self_insight"


class EmotionClassifierConfig(BaseModel):
    lexicon_file: str | None = Field(default="emotion_lexicon.yaml")
    lexicon_custom_file: str | None = None
    """Дополнительный YAML с теми же ключами, что основной лексикон; объединяется с ``lexicon_file`` (объединение множеств)."""
    max_input_chars: int | None = Field(default=None)
    """Если задано — классификатор режет текст до N символов (минимум 64 при не-null)."""
    valence_blend: float = Field(default=0.12, ge=0.0, le=1.0)
    arousal_blend: float = Field(default=0.14, ge=0.0, le=1.0)

    @field_validator("max_input_chars")
    @classmethod
    def max_input_chars_bounds(cls, v: int | None) -> int | None:
        if v is None:
            return v
        if not (64 <= v <= 500_000):
            raise ValueError("emotion_classifier.max_input_chars must be null or between 64 and 500000")
        return v


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
    consolidation_every_n_ticks: int | None = Field(default=None, ge=1)
    """Раз в N **успешных** тиков вызывать ``memory_store.consolidate()`` (для Lance — слияние дублей по тексту; SQLite — no-op). ``null`` — выкл."""
    self_reflection_every_n_ticks: int | None = Field(default=None, ge=1)
    """После каждых N успешных тиков **следующий** тик — режим ``self_reflection`` (см. ``intent.user_prompts.self_reflection``). ``null`` — выкл."""
    self_reflection_recall_n: int = Field(default=5, ge=1, le=32)
    """Сколько воспоминаний подмешать в промпт плановой рефлексии."""
    self_reflection_insight: SelfReflectionInsightConfig = Field(
        default_factory=SelfReflectionInsightConfig
    )


class IskraConfig(BaseModel):
    schema_version: int = 1
    state: StateConfig
    trigger: TriggerConfig
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    agency: AgencyConfig = Field(default_factory=AgencyConfig)
    intent: IntentConfig
    llm: LLMConfig = Field(default_factory=LLMConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    world: WorldConfig = Field(default_factory=WorldConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    general: GeneralConfig = Field(default_factory=GeneralConfig)
    emotion_classifier: EmotionClassifierConfig = Field(default_factory=EmotionClassifierConfig)


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


def _resolve_config_relative_path(config_file: Path, user_path: str) -> Path:
    """Относительный путь: сначала от текущего каталога, иначе от каталога с ``config_file``."""
    p = Path(user_path)
    if p.is_absolute():
        return p.resolve()
    cwd_candidate = (Path.cwd() / p).resolve()
    if cwd_candidate.is_file():
        return cwd_candidate
    return (config_file.parent / p).resolve()


def _parse_topics_yaml_document(doc: Any, *, source: Path) -> list[str]:
    if doc is None:
        raise ValueError(f"random_topic_pool_file is empty YAML: {source}")
    raw_items: list[Any]
    if isinstance(doc, list):
        raw_items = doc
    elif isinstance(doc, dict):
        topics = doc.get("topics")
        if topics is None:
            raise ValueError(
                f"random_topic_pool_file must contain a root list or a mapping "
                f"with key 'topics': {source}"
            )
        if not isinstance(topics, list):
            raise ValueError(f"'topics' must be a list in {source}")
        raw_items = topics
    else:
        raise ValueError(
            f"random_topic_pool_file root must be list or mapping, got {type(doc).__name__}: {source}"
        )
    out: list[str] = []
    for i, item in enumerate(raw_items):
        if not isinstance(item, str):
            raise ValueError(
                f"random_topic_pool_file entry #{i} must be string, got {type(item).__name__}: {source}"
            )
        s = item.strip()
        if s:
            out.append(s)
    return out


def _load_topics_yaml_file(path: Path) -> list[str]:
    if not path.is_file():
        raise ValueError(f"random_topic_pool_file not found: {path}")
    raw = path.read_text(encoding="utf-8")
    try:
        doc = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise ValueError(f"random_topic_pool_file invalid YAML ({path}): {e}") from e
    return _parse_topics_yaml_document(doc, source=path)


def _merge_random_topic_pool_from_file(cfg: IskraConfig, config_file: Path) -> IskraConfig:
    rel = cfg.trigger.random_topic_pool_file
    if rel is None or not str(rel).strip():
        return cfg
    path = _resolve_config_relative_path(config_file, str(rel).strip())
    file_topics = _load_topics_yaml_file(path)
    merged = list(cfg.trigger.random_topic_pool) + file_topics
    new_trigger = cfg.trigger.model_copy(update={"random_topic_pool": merged})
    return cfg.model_copy(update={"trigger": new_trigger})


def validate_cross_config(cfg: IskraConfig) -> None:
    """Cross-field checks from FORMAL_SPEC §7.3."""
    var_names = set(cfg.state.variables.keys())
    for impulse_name, deltas in cfg.state.impulses.items():
        for vn in deltas:
            if vn not in var_names:
                raise ValueError(
                    f"state.impulses.{impulse_name} references unknown variable '{vn}'"
                )
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
    if cfg.memory.recall.emotion_enabled:
        for name in ("valence", "arousal"):
            if name not in var_names:
                raise ValueError(
                    f"memory.recall.emotion_enabled requires state.variables.{name}"
                )
    if cfg.trigger.random_topic_pool is not None and len(cfg.trigger.random_topic_pool) == 0:
        if "new_topic" in cfg.trigger.types:
            raise ValueError("random_topic_pool must be non-empty when new_topic trigger is used")
    if cfg.general.self_reflection_every_n_ticks is not None:
        if "self_reflection" not in cfg.intent.user_prompts:
            raise ValueError(
                "general.self_reflection_every_n_ticks requires intent.user_prompts.self_reflection"
            )
    w = cfg.world.weather
    if w.enabled:
        if w.provider == "openweather":
            if not (w.api_key and str(w.api_key).strip()):
                raise ValueError(
                    "world.weather.provider=openweather requires non-empty world.weather.api_key"
                )
        if (w.lat is None) ^ (w.lon is None):
            raise ValueError("world.weather: set both lat and lon, or neither (use city)")
    r = cfg.world.rss
    if r.enabled and not r.feeds:
        raise ValueError("world.rss.enabled requires at least one world.rss.feeds entry")


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
    cfg = _merge_random_topic_pool_from_file(cfg, p)
    validate_cross_config(cfg)
    return cfg
