# Config Schema (Схема конфигурации)

**Версия документа:** 1.1  
**Дата:** 12 апреля 2026  
**Комплект документации:** 1.0.1 (файл `VERSION` в корне репозитория)  
**Поле `schema_version` в YAML:** `1` (см. также `CONFIG_SCHEMA_VERSION` в `VERSION`)

## Назначение

Вся настройка Iskra-1 определяется одним файлом `config.yaml`. Это означает:
- Никаких хардкод-значений в коде.
- Полный контроль над поведением без перекомпиляции.
- Разные «личности» — разные конфиг-файлы.

Файл валидируется при запуске через Pydantic-модель. Если в конфиге ошибка — система не запускается и печатает понятное сообщение.

**Каноническая копия для репозитория:** эталонный `config.yaml` в **корне проекта** (рядом с `VERSION`). Ниже в разделе «Полный эталонный файл» тот же текст для удобства чтения; при расхождении править сначала корневой `config.yaml`, затем дублировать сюда.

---

## Полная схема

### Корневая структура

```yaml
# Iskra-1 Configuration
# Версия схемы конфигурации
schema_version: 1

# ─── State Engine ───────────────────────────────────────────
state:
  variables: { ... }
  impulses: { ... }
  feedback: { ... }

# ─── Trigger Engine ─────────────────────────────────────────
trigger:
  interval: { ... }
  types: { ... }

# ─── Memory Store ───────────────────────────────────────────
memory:
  backend: "sqlite"
  settings: { ... }
  decay: { ... }
  recall: { ... }

# ─── Intent Generator ──────────────────────────────────────
intent:
  system_prompt_template: "..."
  user_prompts: { ... }

# ─── LLM Adapter ───────────────────────────────────────────
llm:
  adapter: "ollama"
  settings: { ... }

# ─── Output Channel ────────────────────────────────────────
output:
  channel: "console"
  settings: { ... }

# ─── Logging & Metrics ─────────────────────────────────────
logging:
  level: "INFO"
  event_log:
    enabled: true
    path: "data/events.jsonl"

# ─── General ────────────────────────────────────────────────
general:
  decay_every_n_ticks: 10
  tick_jitter: 0.1
```

---

## Детальное описание каждой секции

### state.variables

Определяет все переменные внутреннего состояния. Система работает с произвольным их количеством.

```yaml
state:
  variables:
    curiosity:
      initial: 0.5       # начальное значение при запуске
      mu: 0.5            # точка притяжения (среднее)
      theta: 0.05        # скорость возврата к среднему
      sigma: 0.08        # сила случайных колебаний
    restlessness:
      initial: 0.3
      mu: 0.3
      theta: 0.03
      sigma: 0.06
    nostalgia:
      initial: 0.2
      mu: 0.2
      theta: 0.04
      sigma: 0.05
```

**Ограничения:**
- `initial`, `mu` ∈ [0.0, 1.0]
- `theta` > 0 (рекомендуется 0.01–0.20)
- `sigma` > 0 (рекомендуется 0.01–0.20)
- Хотя бы одна переменная обязательна

### state.impulses

Таблица мгновенных сдвигов переменных при внешних событиях.

```yaml
state:
  impulses:
    user_message:
      curiosity: +0.15
      restlessness: +0.10
      nostalgia: 0.0
    user_silence_1h:
      curiosity: -0.05
      restlessness: -0.10
      nostalgia: +0.10
    system_startup:
      curiosity: +0.20
      restlessness: +0.20
      nostalgia: 0.0
```

Пользователь может добавлять произвольные типы событий. Если для переменной не указан импульс — считается 0.

### state.feedback

Правила обратной связи от результатов LLM.

```yaml
state:
  feedback:
    response_has_question:
      condition: "ends_with_question_mark"
      curiosity: +0.05
      restlessness: +0.03
      nostalgia: 0.0
    response_short:
      condition: "length_lt_50"
      curiosity: -0.03
      restlessness: -0.05
      nostalgia: 0.0
    response_long:
      condition: "length_gt_500"
      curiosity: +0.03
      restlessness: -0.03
      nostalgia: 0.0
    trigger_was_recall:
      condition: "trigger_type_eq_recall_memory"
      curiosity: 0.0
      restlessness: 0.0
      nostalgia: -0.08
    trigger_was_new_topic:
      condition: "trigger_type_eq_new_topic"
      curiosity: -0.05
      restlessness: 0.0
      nostalgia: +0.03
    trigger_was_meta:
      condition: "trigger_type_eq_meta_reflection"
      curiosity: 0.0
      restlessness: -0.05
      nostalgia: 0.0
```

**Поддерживаемые условия (MVP):**
- `ends_with_question_mark` — ответ заканчивается на `?`
- `length_lt_N` — длина ответа < N символов
- `length_gt_N` — длина ответа > N символов
- `trigger_type_eq_X` — тип триггера равен X

---

### trigger.interval

Параметры интервалов между тиками.

```yaml
trigger:
  interval:
    min_seconds: 180       # минимум 3 минуты
    max_seconds: 900       # максимум 15 минут
    modulated_by: "restlessness"  # какая переменная модулирует
```

**Формула:**
```
interval = max_seconds - (max_seconds - min_seconds) * state[modulated_by]
```

При `restlessness = 0.0` → 900с (15 мин), при `restlessness = 1.0` → 180с (3 мин).

### trigger.types

Реестр типов триггеров с базовыми весами и модуляторами.

```yaml
trigger:
  types:
    new_topic:
      base_weight: 0.30
      modulated_by: "curiosity"
      modulation_strength: 1.0   # множитель: weight *= (1 + strength * state_var)
      context_source: "random_topic_pool"
    recall_memory:
      base_weight: 0.30
      modulated_by: "nostalgia"
      modulation_strength: 1.0
      context_source: "memory_store"
    continue_context:
      base_weight: 0.25
      modulated_by: null         # не модулируется
      modulation_strength: 0.0
      context_source: "last_event"
    meta_reflection:
      base_weight: 0.15
      modulated_by: "restlessness"
      modulation_strength: 0.5
      context_source: null       # не нужен контекст
```

**Формула итогового веса:**
```
if modulated_by is null:
    weight = base_weight
else:
    weight = base_weight * (1.0 + modulation_strength * state[modulated_by])
```

Все веса нормализуются в вероятности: `p_i = w_i / sum(all w)`.

**Пул случайных тем (для `new_topic`):**

```yaml
trigger:
  random_topic_pool:
    - "квантовая запутанность"
    - "история письменности"
    - "эволюция кошачьих"
    - "фрактальная геометрия"
    - "философия сознания"
    - "археология Месопотамии"
    - "теория музыки"
    - "вулканология"
    - "криптография"
    - "нейропластичность"
    # ... пользователь дополняет свои темы
```

---

### memory

```yaml
memory:
  backend: "sqlite"            # "sqlite" | "json" | "chroma" (будущее)
  settings:
    # Для sqlite:
    db_path: "data/memory.db"
    # Для json:
    # file_path: "data/memory.json"

  recall:
    default_n: 3               # сколько записей возвращать по умолчанию
    importance_weight: 0.7     # вес importance в формуле score
    recency_weight: 0.3       # вес recency в формуле score
    selection: "stochastic"    # "stochastic" | "top_n"

  decay:
    enabled: true
    base_rate: 0.01            # decay_rate по умолчанию для новых записей
    min_importance: 0.01       # ниже не забываем (никогда не удаляем)
    recall_protection: 1.5     # множитель: часто вспоминаемые = медленнее забываются

  initial_memories_file: "data/seed_memories.yaml"  # опционально
```

**Формат файла начальных воспоминаний (`seed_memories.yaml`):**
```yaml
memories:
  - category: "self"
    content: "Я — Iskra-1, экспериментальная система искусственной интенции."
    importance: 0.9
  - category: "philosophy"
    content: "Между запросами у LLM нет ничего — только потенциал."
    importance: 0.8
  - category: "observation"
    content: "У кота есть намерение, которое рождается изнутри."
    importance: 0.7
```

---

### intent

```yaml
intent:
  system_prompt_template: |
    Ты — живое существо с внутренним миром. Прямо сейчас у тебя
    спонтанно возникла мысль. Это НЕ запрос от человека. Это ТВОЁ
    собственное желание. Реагируй естественно: развей мысль, запиши
    её, задай себе вопрос, выскажи эмоцию — что угодно, что ощущается
    органичным в данный момент.

    Твоё текущее состояние:
    {% for var_name, var_value in state.items() %}
    - {{ var_name }}: {{ "%.2f"|format(var_value) }}
    {% endfor %}

  user_prompts:
    new_topic: >
      Тебе вдруг стало интересно: {{ context }}
    recall_memory: >
      Ты вдруг вспомнил: "{{ context }}"
    continue_context: >
      Ты продолжаешь думать о: {{ context }}
    meta_reflection: >
      Ты задумался о том, как устроено твоё собственное мышление.
    default: >
      У тебя возникла мысль: {{ context }}

  max_response_tokens: 500     # передаётся в LLM Adapter
```

Шаблоны используют синтаксис Jinja2. Переменные:
- `{{ state }}` — dict переменных состояния
- `{{ context }}` — строка контекста от триггера
- `{{ memories }}` — список извлечённых воспоминаний

---

### llm

```yaml
llm:
  adapter: "ollama"               # "mock" | "ollama" | "openai" | "grok" | "anthropic"
  settings:
    # ─── Mock ─────────────────────────
    # mock:
    #   response_template: "Мысль зафиксирована: {user_prompt}"
    #   latency_ms: 100            # имитация задержки

    # ─── Ollama ───────────────────────
    ollama:
      base_url: "http://localhost:11434"
      model: "llama3:8b"
      timeout_seconds: 60

    # ─── OpenAI ───────────────────────
    # openai:
    #   api_key: "${ISKRA_OPENAI_KEY}"   # из переменных окружения
    #   model: "gpt-4o-mini"
    #   base_url: "https://api.openai.com/v1"
    #   timeout_seconds: 30

    # ─── Grok ─────────────────────────
    # grok:
    #   api_key: "${ISKRA_GROK_KEY}"
    #   model: "grok-3"
    #   base_url: "https://api.x.ai/v1"
    #   timeout_seconds: 30

    # ─── Anthropic ────────────────────
    # anthropic:
    #   api_key: "${ISKRA_ANTHROPIC_KEY}"
    #   model: "claude-sonnet-4-20250514"
    #   timeout_seconds: 30

  temperature: 0.9                 # высокая — для спонтанности
  max_tokens: 500
  retry:
    max_attempts: 3
    backoff_base_seconds: 1.0      # 1s, 2s, 4s
  cooldown_on_rate_limit_seconds: 300  # 5 мин тишины при 429
```

**Переменные окружения:** значения, начинающиеся с `${...}`, подставляются из `os.environ` при загрузке.

---

### output

```yaml
output:
  channel: "console"              # "console" | "file" | "telegram" | "multi"
  settings:
    console:
      use_rich: true              # красивое форматирование через rich
      show_state: true            # показывать переменные состояния
      show_trigger_type: true
      show_timestamp: true

    file:
      path: "data/thoughts.log"
      format: "text"              # "text" | "json"

    # telegram:
    #   bot_token: "${ISKRA_TG_TOKEN}"
    #   chat_id: "123456789"
    #   send_state: false

    # multi — несколько каналов одновременно
    # multi:
    #   channels: ["console", "file"]
```

---

### logging

```yaml
logging:
  level: "INFO"                   # "DEBUG" | "INFO" | "WARNING" | "ERROR"
  format: "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
  event_log:
    enabled: true
    path: "data/events.jsonl"     # полный лог всех событий
    rotate_mb: 100                # ротация при достижении 100 МБ
```

---

### general

```yaml
general:
  decay_every_n_ticks: 10         # запуск decay каждые N тиков
  tick_jitter: 0.1                # случайный разброс ±10% к интервалу
  data_dir: "data"                # директория для всех данных
  pid_file: "data/iskra.pid"      # для предотвращения двойного запуска
```

---

## Полный эталонный файл config.yaml

Содержимое совпадает с **`config.yaml` в корне репозитория**.

```yaml
schema_version: 1

state:
  variables:
    curiosity:
      initial: 0.5
      mu: 0.5
      theta: 0.05
      sigma: 0.08
    restlessness:
      initial: 0.3
      mu: 0.3
      theta: 0.03
      sigma: 0.06
    nostalgia:
      initial: 0.2
      mu: 0.2
      theta: 0.04
      sigma: 0.05

  impulses:
    user_message:
      curiosity: 0.15
      restlessness: 0.10
    user_silence_1h:
      curiosity: -0.05
      restlessness: -0.10
      nostalgia: 0.10
    system_startup:
      curiosity: 0.20
      restlessness: 0.20

  feedback:
    response_has_question:
      condition: "ends_with_question_mark"
      curiosity: 0.05
      restlessness: 0.03
    response_short:
      condition: "length_lt_50"
      curiosity: -0.03
      restlessness: -0.05
    response_long:
      condition: "length_gt_500"
      curiosity: 0.03
      restlessness: -0.03
    trigger_was_recall:
      condition: "trigger_type_eq_recall_memory"
      nostalgia: -0.08
    trigger_was_new_topic:
      condition: "trigger_type_eq_new_topic"
      curiosity: -0.05
      nostalgia: 0.03
    trigger_was_meta:
      condition: "trigger_type_eq_meta_reflection"
      restlessness: -0.05

trigger:
  interval:
    min_seconds: 180
    max_seconds: 900
    modulated_by: "restlessness"

  types:
    new_topic:
      base_weight: 0.30
      modulated_by: "curiosity"
      modulation_strength: 1.0
      context_source: "random_topic_pool"
    recall_memory:
      base_weight: 0.30
      modulated_by: "nostalgia"
      modulation_strength: 1.0
      context_source: "memory_store"
    continue_context:
      base_weight: 0.25
      modulated_by: null
      modulation_strength: 0.0
      context_source: "last_event"
    meta_reflection:
      base_weight: 0.15
      modulated_by: "restlessness"
      modulation_strength: 0.5
      context_source: null

  random_topic_pool:
    - "квантовая запутанность"
    - "история письменности"
    - "эволюция кошачьих"
    - "фрактальная геометрия"
    - "философия сознания"
    - "археология Месопотамии"
    - "теория музыки"
    - "вулканология"
    - "криптография"
    - "нейропластичность"
    - "парадоксы бесконечности"
    - "симбиоз в природе"
    - "история компьютеров"
    - "теория хаоса"
    - "лингвистика жестовых языков"

memory:
  backend: "sqlite"
  settings:
    db_path: "data/memory.db"

  recall:
    default_n: 3
    importance_weight: 0.7
    recency_weight: 0.3
    selection: "stochastic"

  decay:
    enabled: true
    base_rate: 0.01
    min_importance: 0.01
    recall_protection: 1.5

  initial_memories_file: null

intent:
  system_prompt_template: |
    Ты — живое существо с внутренним миром. Прямо сейчас у тебя
    спонтанно возникла мысль. Это НЕ запрос от человека. Это ТВОЁ
    собственное желание. Реагируй естественно: развей мысль, запиши
    её, задай себе вопрос, выскажи эмоцию — что угодно.

    Твоё текущее состояние:
    {% for var_name, var_value in state.items() %}
    - {{ var_name }}: {{ "%.2f"|format(var_value) }}
    {% endfor %}

  user_prompts:
    new_topic: "Тебе вдруг стало интересно: {{ context }}"
    recall_memory: "Ты вдруг вспомнил: \"{{ context }}\""
    continue_context: "Ты продолжаешь думать о: {{ context }}"
    meta_reflection: "Ты задумался о том, как устроено твоё собственное мышление."
    default: "У тебя возникла мысль: {{ context }}"

  max_response_tokens: 500

llm:
  adapter: "mock"
  settings:
    mock:
      response_template: "[MOCK] Мысль зафиксирована. Триггер: {trigger_type}"
      latency_ms: 100
    ollama:
      base_url: "http://localhost:11434"
      model: "llama3:8b"
      timeout_seconds: 60

  temperature: 0.9
  max_tokens: 500
  retry:
    max_attempts: 3
    backoff_base_seconds: 1.0
  cooldown_on_rate_limit_seconds: 300

output:
  channel: "console"
  settings:
    console:
      use_rich: true
      show_state: true
      show_trigger_type: true
      show_timestamp: true
    file:
      path: "data/thoughts.log"
      format: "text"

logging:
  level: "INFO"
  format: "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
  event_log:
    enabled: true
    path: "data/events.jsonl"
    rotate_mb: 100

general:
  decay_every_n_ticks: 10
  tick_jitter: 0.1
  data_dir: "data"
  pid_file: "data/iskra.pid"
```

---

## Pydantic-модель валидации (для реализации)

```python
from pydantic import BaseModel, Field, field_validator

class StateVariableConfig(BaseModel):
    initial: float = Field(ge=0.0, le=1.0)
    mu: float = Field(ge=0.0, le=1.0)
    theta: float = Field(gt=0.0)
    sigma: float = Field(gt=0.0)

class ImpulseConfig(BaseModel):
    """Произвольный dict: имя_переменной → величина_сдвига."""
    model_config = {"extra": "allow"}

class FeedbackRuleConfig(BaseModel):
    condition: str
    model_config = {"extra": "allow"}

class StateConfig(BaseModel):
    variables: dict[str, StateVariableConfig]
    impulses: dict[str, dict[str, float]] = {}
    feedback: dict[str, FeedbackRuleConfig] = {}

    @field_validator("variables")
    @classmethod
    def at_least_one_variable(cls, v):
        if len(v) == 0:
            raise ValueError("At least one state variable required")
        return v

class TriggerIntervalConfig(BaseModel):
    min_seconds: int = Field(ge=1)
    max_seconds: int = Field(ge=1)
    modulated_by: str | None = None

class TriggerTypeConfig(BaseModel):
    base_weight: float = Field(gt=0.0)
    modulated_by: str | None = None
    modulation_strength: float = 0.0
    context_source: str | None = None

class TriggerConfig(BaseModel):
    interval: TriggerIntervalConfig
    types: dict[str, TriggerTypeConfig]
    random_topic_pool: list[str] = []

class MemoryRecallConfig(BaseModel):
    default_n: int = Field(ge=1, default=3)
    importance_weight: float = Field(ge=0.0, le=1.0, default=0.7)
    recency_weight: float = Field(ge=0.0, le=1.0, default=0.3)
    selection: str = "stochastic"  # "stochastic" | "top_n"

class MemoryDecayConfig(BaseModel):
    enabled: bool = True
    base_rate: float = Field(ge=0.0, default=0.01)
    min_importance: float = Field(ge=0.0, le=1.0, default=0.01)
    recall_protection: float = Field(ge=1.0, default=1.5)

class MemoryConfig(BaseModel):
    backend: str = "sqlite"
    settings: dict = {}
    recall: MemoryRecallConfig = MemoryRecallConfig()
    decay: MemoryDecayConfig = MemoryDecayConfig()
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
    settings: dict = {}
    temperature: float = Field(ge=0.0, le=2.0, default=0.9)
    max_tokens: int = Field(ge=1, default=500)
    retry: LLMRetryConfig = LLMRetryConfig()
    cooldown_on_rate_limit_seconds: int = 300

class OutputConfig(BaseModel):
    channel: str = "console"
    settings: dict = {}

class EventLogConfig(BaseModel):
    enabled: bool = True
    path: str = "data/events.jsonl"
    rotate_mb: int = 100

class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    event_log: EventLogConfig = EventLogConfig()

class GeneralConfig(BaseModel):
    decay_every_n_ticks: int = Field(ge=1, default=10)
    tick_jitter: float = Field(ge=0.0, le=1.0, default=0.1)
    data_dir: str = "data"
    pid_file: str = "data/iskra.pid"

class IskraConfig(BaseModel):
    schema_version: int = 1
    state: StateConfig
    trigger: TriggerConfig
    memory: MemoryConfig = MemoryConfig()
    intent: IntentConfig
    llm: LLMConfig = LLMConfig()
    output: OutputConfig = OutputConfig()
    logging: LoggingConfig = LoggingConfig()
    general: GeneralConfig = GeneralConfig()
```

---

## Загрузка конфигурации (псевдокод)

```python
import os
import re
import yaml
from pathlib import Path

def load_config(path: str = "config.yaml") -> IskraConfig:
    raw = Path(path).read_text(encoding="utf-8")

    # Подстановка переменных окружения: ${VAR_NAME} → os.environ[VAR_NAME]
    def replace_env(match):
        var = match.group(1)
        value = os.environ.get(var)
        if value is None:
            raise ValueError(f"Environment variable {var} not set")
        return value

    raw = re.sub(r'\$\{(\w+)\}', replace_env, raw)

    data = yaml.safe_load(raw)
    return IskraConfig(**data)
```

---

## Запуск

```bash
# С конфигом по умолчанию (config.yaml в текущей директории)
python -m iskra

# С указанием конфига
python -m iskra --config path/to/my_config.yaml

# С переменными окружения для API-ключей
ISKRA_OPENAI_KEY=sk-... python -m iskra --config production.yaml
```
