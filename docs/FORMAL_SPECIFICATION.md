# Формализованная Спецификация Iskra-1

**Версия документа:** 1.1  
**Дата:** 12 апреля 2026  
**Комплект документации:** 1.0.0 (файл `VERSION` в корне репозитория)  
**Статус:** Утверждена для реализации MVP  
**Основание:** ТЕХНИЧЕСКОЕ ЗАДАНИЕ v2.1 (`docs/ТЕХНИЧЕСКОЕ ЗАДАНИЕ.txt`)

---

## 0. Терминология

| Термин            | Определение                                                                 |
|-------------------|-----------------------------------------------------------------------------|
| Тик               | Одна итерация основного цикла MainLoop                                     |
| Искра (Spark)     | Единичное событие порождения мысли                                         |
| Дрейф             | Изменение переменной состояния под действием OU-процесса                   |
| Импульс           | Мгновенный сдвиг переменной состояния от события                           |
| Обратная связь    | Импульс, порождённый анализом ответа LLM                                   |
| Decay             | Постепенное снижение importance у записей памяти                           |
| Snapshot          | Неизменяемая копия всех переменных состояния на момент времени              |
| Protocol          | Python typing.Protocol — структурный интерфейс без наследования            |
| Адаптер           | Реализация Protocol для конкретного бэкенда (LLM, память, вывод)           |
| Seed memories     | Начальные воспоминания, загружаемые из файла при первом запуске             |

---

## 1. Среда выполнения

### 1.1. Требования к системе

| Параметр            | Значение                                      |
|---------------------|-----------------------------------------------|
| Python              | >= 3.12                                       |
| ОС                  | Windows 10+, Linux, macOS                     |
| Архитектура         | x86_64 или arm64                              |
| Оперативная память  | >= 512 МБ (без LLM), >= 8 ГБ (с Ollama)      |
| Дисковое пространство | >= 100 МБ для данных                        |

### 1.2. Зависимости (requirements.txt)

```
pyyaml>=6.0
pydantic>=2.0
jinja2>=3.1
```

Опциональные:
```
httpx>=0.27          # для OllamaAdapter и облачных API
rich>=13.0           # для ConsoleOutput с форматированием
```

### 1.3. Точка входа

```
python -m iskra [--config PATH]
```

Аргументы CLI:

| Аргумент     | Тип    | По умолчанию   | Описание                        |
|--------------|--------|-----------------|---------------------------------|
| `--config`   | string | `config.yaml`   | Путь к файлу конфигурации       |

Файл: `iskra/__main__.py`

---

## 2. Структура пакета

```
iskra/
├── __init__.py
├── __main__.py                 # CLI-точка входа
├── models.py                   # Все dataclass'ы и type aliases
├── core/
│   ├── __init__.py
│   ├── config.py               # Pydantic-модели + load_config()
│   ├── state_engine.py         # OUStateEngine
│   ├── trigger_engine.py       # DefaultTriggerEngine
│   ├── intent_generator.py     # Jinja2IntentGenerator
│   └── main_loop.py            # MainLoop
├── memory/
│   ├── __init__.py
│   ├── protocol.py             # MemoryStore Protocol
│   └── sqlite_store.py         # SQLiteMemoryStore
├── llm/
│   ├── __init__.py
│   ├── protocol.py             # LLMAdapter Protocol
│   ├── mock_adapter.py         # MockAdapter
│   └── ollama_adapter.py       # OllamaAdapter
├── output/
│   ├── __init__.py
│   ├── protocol.py             # OutputChannel Protocol
│   ├── console_output.py       # ConsoleOutput
│   └── file_output.py          # FileOutput
├── triggers/
│   ├── __init__.py
│   ├── protocol.py             # TriggerType Protocol
│   ├── new_topic.py            # NewTopicTrigger
│   ├── recall_memory.py        # RecallMemoryTrigger
│   ├── continue_context.py     # ContinueContextTrigger
│   └── meta_reflection.py      # MetaReflectionTrigger
└── event_log.py                # EventLog (JSONL writer)
```

---

## 3. Модели данных (iskra/models.py)

Все структуры данных, передаваемые между компонентами.

### 3.1. StateSnapshot

```python
StateSnapshot = dict[str, float]
```

Пример: `{"curiosity": 0.62, "restlessness": 0.41, "nostalgia": 0.18}`

Инвариант: все значения ∈ [0.0, 1.0].

### 3.2. SparkEvent

```python
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

@dataclass(frozen=True)
class SparkEvent:
    id: str = field(default_factory=lambda: str(uuid4()))
    trigger_type: str = ""
    state_snapshot: dict[str, float] = field(default_factory=dict)
    memory_context: list["MemoryRecord"] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict = field(default_factory=dict)
```

Инварианты:
- `id` — UUID v4, уникален в пределах сессии.
- `trigger_type` — одно из зарегистрированных имён триггеров.
- `state_snapshot` — frozen-копия, не изменяется после создания.

### 3.3. MemoryRecord

```python
@dataclass
class MemoryRecord:
    id: str
    timestamp: datetime
    category: str
    content: str
    importance: float
    last_recall: datetime
    recall_count: int
    decay_rate: float
```

Инварианты:
- `id` — UUID v4, уникален глобально.
- `importance` ∈ [min_importance, 1.0] (min_importance из конфигурации, по умолчанию 0.01).
- `recall_count` >= 0.
- `decay_rate` > 0.
- `content` — непустая строка.

### 3.4. IntentPayload

```python
@dataclass(frozen=True)
class IntentPayload:
    event_id: str
    system_prompt: str
    user_prompt: str
    trigger_type: str
    timestamp: datetime
```

Инвариант: `event_id` совпадает с `SparkEvent.id`.

### 3.5. LLMResponse

```python
@dataclass(frozen=True)
class LLMResponse:
    event_id: str
    content: str
    model: str
    tokens_used: int
    latency_ms: int
    timestamp: datetime
```

Инварианты:
- `content` — непустая строка (даже MockAdapter возвращает непустой шаблон).
- `tokens_used` >= 0 (для MockAdapter = 0).
- `latency_ms` >= 0.

### 3.6. EventLogEntry

```python
@dataclass
class EventLogEntry:
    event_id: str
    timestamp: str               # ISO 8601 UTC
    trigger_type: str
    state_before: dict[str, float]
    state_after: dict[str, float]
    memory_ids_recalled: list[str]
    prompt_system: str
    prompt_user: str
    llm_response: str
    llm_model: str
    llm_tokens: int
    llm_latency_ms: int
    memory_id_stored: str | None
    output_channel: str
    errors: list[str]
```

Сериализуется в JSON через `dataclasses.asdict()`. Одна запись = одна строка в JSONL.

---

## 4. Протоколы (интерфейсы)

Каждый компонент определяет Protocol. Реализации подключаются через фабрику в `MainLoop.__init__`.

### 4.1. StateEngine Protocol

Файл: неявный (реализация — `iskra/core/state_engine.py`)

```python
class StateEngine(Protocol):
    def tick(self, elapsed_seconds: float) -> None: ...
    def apply_impulse(self, event_type: str) -> None: ...
    def apply_feedback(self, trigger_type: str, llm_response: str) -> None: ...
    def snapshot(self) -> StateSnapshot: ...
    def get(self, name: str) -> float: ...
```

| Метод            | Предусловия                     | Постусловия                                         | Ошибки      |
|------------------|---------------------------------|------------------------------------------------------|-------------|
| `tick`           | `elapsed_seconds >= 0`          | Все переменные обновлены по OU; все ∈ [0.0, 1.0]    | Нет         |
| `apply_impulse`  | `event_type` в конфиге          | Переменные сдвинуты; все ∈ [0.0, 1.0]               | Нет (ignore)|
| `apply_feedback` | —                               | Переменные сдвинуты по правилам feedback             | Нет         |
| `snapshot`       | —                               | Возвращает новый dict (не ссылку на внутренний)      | Нет         |
| `get`            | `name` — существующая переменная | Возвращает float ∈ [0.0, 1.0]                       | KeyError    |

### 4.2. TriggerType Protocol

Файл: `iskra/triggers/protocol.py`

```python
class TriggerType(Protocol):
    name: str
    base_weight: float

    def compute_weight(self, state: StateSnapshot) -> float: ...
    def generate_context(self, memory: "MemoryStore") -> list["MemoryRecord"]: ...
```

| Метод              | Предусловия | Постусловия                    | Ошибки                    |
|--------------------|-------------|--------------------------------|---------------------------|
| `compute_weight`   | —           | Возвращает float > 0           | Нет                       |
| `generate_context` | —           | Возвращает list[MemoryRecord]  | Любое → ловится вызывающим|

### 4.3. MemoryStore Protocol

Файл: `iskra/memory/protocol.py`

```python
class MemoryStore(Protocol):
    def store(self, category: str, content: str, importance: float) -> str: ...
    def recall(self, category: str | None = None, n: int = 3,
               context: str | None = None) -> list[MemoryRecord]: ...
    def decay(self) -> None: ...
    def count(self) -> int: ...
```

| Метод    | Предусловия                                  | Постусловия                                      | Ошибки               |
|----------|----------------------------------------------|--------------------------------------------------|----------------------|
| `store`  | `content` непуста, `importance` ∈ [0.0, 1.0] | Запись сохранена, возвращён UUID                  | sqlite3.Error → лог  |
| `recall` | `n >= 1`                                      | Возвращает <= n записей; обновлены last_recall    | Ошибка → `[]`        |
| `decay`  | —                                             | importance у всех записей уменьшена (или на min)  | Ошибка → лог         |
| `count`  | —                                             | Возвращает int >= 0                               | Ошибка → 0           |

### 4.4. LLMAdapter Protocol

Файл: `iskra/llm/protocol.py`

```python
class LLMAdapter(Protocol):
    async def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse: ...
    def is_available(self) -> bool: ...
```

| Метод          | Предусловия       | Постусловия                | Ошибки                              |
|----------------|--------------------|----------------------------|--------------------------------------|
| `complete`     | Промпты непусты    | Возвращает LLMResponse     | Timeout, RateLimit, NetworkError     |
| `is_available` | —                  | Возвращает bool            | Нет (ловит внутри)                   |

Исключения, определяемые в `iskra/llm/protocol.py`:

```python
class LLMError(Exception): ...
class LLMTimeoutError(LLMError): ...
class LLMRateLimitError(LLMError): ...
class LLMNetworkError(LLMError): ...
```

### 4.5. OutputChannel Protocol

Файл: `iskra/output/protocol.py`

```python
class OutputChannel(Protocol):
    name: str

    async def emit(self, event_id: str, thought: str, trigger_type: str,
                   state_snapshot: StateSnapshot, timestamp: datetime) -> None: ...
```

| Метод  | Предусловия   | Постусловия           | Ошибки                  |
|--------|---------------|-----------------------|-------------------------|
| `emit` | `thought` непуст | Мысль выведена       | Ошибка → fallback console|

---

## 5. Алгоритмы

### 5.1. OU-дрейф (State Engine)

**Вызов:** `StateEngine.tick(elapsed_seconds)`

**Для каждой переменной x с параметрами (mu, theta, sigma):**

```
dt = elapsed_seconds / 60.0
noise = random.gauss(0.0, 1.0)
dx = theta * (mu - x) * dt + sigma * sqrt(dt) * noise
x = clamp(x + dx, 0.0, 1.0)
```

Где `clamp(v, lo, hi) = max(lo, min(hi, v))`.

**Порядок применения на каждом тике:**
1. OU-дрейф (для всех переменных).
2. Импульсы из очереди внешних событий (FIFO).
3. Обратная связь от предыдущего LLM-ответа (если был).

### 5.2. Вычисление интервала до следующего тика (Trigger Engine)

```
modulator = state[config.trigger.interval.modulated_by]
base = max_seconds - (max_seconds - min_seconds) * modulator
jitter_factor = 1.0 + random.uniform(-tick_jitter, +tick_jitter)
interval = base * jitter_factor
```

Результат: `interval` в секундах, float.

### 5.3. Вычисление весов триггеров (Trigger Engine)

Для каждого зарегистрированного типа `i`:

```
if trigger_i.modulated_by is None:
    w_i = trigger_i.base_weight
else:
    w_i = trigger_i.base_weight * (1.0 + trigger_i.modulation_strength * state[trigger_i.modulated_by])
```

Нормализация:

```
total = sum(w_i for all i)
p_i = w_i / total
```

Выбор: `random.choices(triggers, weights=[w_i, ...], k=1)[0]`.

### 5.4. Recall из памяти (Memory Store)

**Вход:** `category: str | None`, `n: int`, `context: str | None` (игнорируется на MVP).

**Алгоритм:**

```
1. records = SELECT * FROM memories [WHERE category = ?]
2. Если len(records) == 0: return []

3. Для каждой записи r:
   hours_since = (now - r.last_recall).total_seconds() / 3600.0
   recency = 1.0 / (1.0 + hours_since)
   r.score = r.importance * importance_weight + recency * recency_weight

4. Если selection == "stochastic":
     selected = random.choices(records, weights=[r.score], k=min(n, len(records)))
   Если selection == "top_n":
     selected = sorted(records, key=score, reverse=True)[:n]

5. Для каждой selected:
     UPDATE memories SET last_recall = now, recall_count = recall_count + 1
     WHERE id = selected.id

6. return selected
```

### 5.5. Decay (Memory Store)

**Вызов:** каждые `decay_every_n_ticks` тиков.

**Для каждой записи r:**

```
hours_since = (now - r.last_recall).total_seconds() / 3600.0
protection = 1.0 / (1.0 + r.recall_count / recall_protection)
effective_rate = r.decay_rate * protection
new_importance = r.importance * (1.0 - effective_rate * hours_since / 24.0)
r.importance = max(min_importance, new_importance)
```

### 5.6. Compute importance (постобработка)

**Вход:** `SparkEvent`, `LLMResponse`.

```
base = 0.5
if len(response.content) > 300: base += 0.1
if "?" in response.content:     base += 0.1
if event.trigger_type == "meta_reflection": base += 0.15
importance = min(1.0, base)
```

### 5.7. Feedback (State Engine)

**Вызов:** `apply_feedback(trigger_type, llm_response)`

**Алгоритм:**

```
for rule_name, rule in config.state.feedback.items():
    if evaluate_condition(rule.condition, trigger_type, llm_response):
        for var_name, delta in rule.impulses.items():
            variables[var_name] = clamp(variables[var_name] + delta, 0.0, 1.0)
```

**evaluate_condition(condition, trigger_type, response) → bool:**

| Condition pattern              | Логика                                          |
|-------------------------------|-------------------------------------------------|
| `ends_with_question_mark`     | `response.rstrip().endswith("?")`               |
| `length_lt_N`                 | `len(response) < N`                             |
| `length_gt_N`                 | `len(response) > N`                             |
| `trigger_type_eq_X`           | `trigger_type == X`                             |

Парсинг condition:
```python
import re

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
    return False
```

### 5.8. Шаблонизация промптов (Intent Generator)

**Движок:** Jinja2.

**System prompt:**
```
template = jinja2.Template(config.intent.system_prompt_template)
system_prompt = template.render(state=state_snapshot)
```

**User prompt:**
```
template_str = config.intent.user_prompts.get(trigger_type,
               config.intent.user_prompts["default"])
template = jinja2.Template(template_str)
user_prompt = template.render(
    context=context_string,
    memories=[m.content for m in event.memory_context]
)
```

Где `context_string` зависит от типа триггера:
- `new_topic` → случайный элемент из `random_topic_pool`.
- `recall_memory` → `memory_context[0].content` (первое воспоминание).
- `continue_context` → `memory_context[0].content` (последний ответ LLM из Memory Store, категория `"last_context"`).
- `meta_reflection` → пустая строка (контекст не нужен).

---

## 6. Реализации адаптеров (MVP)

### 6.1. MockAdapter

Файл: `iskra/llm/mock_adapter.py`

Не делает сетевых запросов. Возвращает шаблонный ответ из конфигурации.

```python
class MockAdapter:
    def __init__(self, config: dict):
        self.template = config.get("response_template",
                                    "[MOCK] Thought registered.")
        self.latency_ms = config.get("latency_ms", 100)

    async def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        await asyncio.sleep(self.latency_ms / 1000.0)
        return LLMResponse(
            event_id="",      # заполняется вызывающим
            content=self.template.format(
                trigger_type="unknown",
                user_prompt=user_prompt[:100]
            ),
            model="mock",
            tokens_used=0,
            latency_ms=self.latency_ms,
            timestamp=datetime.utcnow()
        )

    def is_available(self) -> bool:
        return True
```

### 6.2. OllamaAdapter

Файл: `iskra/llm/ollama_adapter.py`

Зависимость: `httpx`.

```python
class OllamaAdapter:
    def __init__(self, config: dict, llm_config: LLMConfig):
        self.base_url = config["base_url"]
        self.model = config["model"]
        self.timeout = config.get("timeout_seconds", 60)
        self.temperature = llm_config.temperature
        self.max_tokens = llm_config.max_tokens

    async def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "stream": False,
                    "options": {
                        "temperature": self.temperature,
                        "num_predict": self.max_tokens
                    }
                }
            )
            resp.raise_for_status()
            data = resp.json()

        latency = int((time.monotonic() - t0) * 1000)
        return LLMResponse(
            event_id="",
            content=data["message"]["content"],
            model=self.model,
            tokens_used=data.get("eval_count", 0),
            latency_ms=latency,
            timestamp=datetime.utcnow()
        )

    def is_available(self) -> bool:
        try:
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False
```

**Обработка ошибок (в MainLoop, не в адаптере):**
- `httpx.TimeoutException` → `LLMTimeoutError`
- `httpx.HTTPStatusError` с кодом 429 → `LLMRateLimitError`
- Прочие `httpx` ошибки → `LLMNetworkError`

**Retry-логика (в MainLoop):**
```python
for attempt in range(config.llm.retry.max_attempts):
    try:
        response = await adapter.complete(system, user)
        break
    except LLMRateLimitError:
        self.cooldown_until = time.monotonic() + config.llm.cooldown_on_rate_limit_seconds
        raise
    except (LLMTimeoutError, LLMNetworkError):
        if attempt == config.llm.retry.max_attempts - 1:
            raise
        delay = config.llm.retry.backoff_base_seconds * (2 ** attempt)
        await asyncio.sleep(delay)
```

### 6.3. SQLiteMemoryStore

Файл: `iskra/memory/sqlite_store.py`

**Инициализация:**
1. Создать директорию для `db_path` (если не существует).
2. Подключиться к SQLite с `check_same_thread=False`.
3. Выполнить `CREATE TABLE IF NOT EXISTS` (схема из MEMORY_SYSTEM.md).
4. Создать индексы.

**Thread safety:** все операции через один `sqlite3.Connection` с `threading.Lock`. Async-обёртка через `asyncio.to_thread` не требуется на MVP — SQLite вызывается синхронно из async-контекста (операции быстрые, < 10 мс).

### 6.4. ConsoleOutput

Файл: `iskra/output/console_output.py`

Два режима:
- `use_rich = true` → вывод через `rich.console.Console` с панелями и цветами.
- `use_rich = false` → `print()` с ASCII-рамками.

Формат (оба режима):

```
═══════════════════════════════════════════════════════
[2026-04-11 03:42:17] Мысль #47 (new_topic)
───────────────────────────────────────────────────────
Состояние: curiosity=0.72 restlessness=0.38 nostalgia=0.15

<текст мысли>
═══════════════════════════════════════════════════════
```

### 6.5. FileOutput

Файл: `iskra/output/file_output.py`

Два формата:
- `format: "text"` → тот же формат, что ConsoleOutput, дозапись в файл.
- `format: "json"` → одна JSON-строка на мысль (для машинного анализа).

---

## 7. Конфигурация

### 7.1. Загрузка

Файл: `iskra/core/config.py`

**Алгоритм load_config(path):**
1. Прочитать файл как UTF-8 текст.
2. Подставить `${VAR_NAME}` → `os.environ["VAR_NAME"]`. Если переменная не задана и значение не закомментировано → `ValueError` с указанием имени переменной.
3. Парсить YAML через `yaml.safe_load()`.
4. Валидировать через `IskraConfig(**data)`.
5. При ошибке валидации → вывести понятное сообщение, `sys.exit(1)`.

### 7.2. Pydantic-модели

Полная иерархия моделей определена в CONFIG_SCHEMA.md. Здесь фиксируем контракты валидации:

| Модель                | Поле                | Ограничение                          |
|-----------------------|---------------------|--------------------------------------|
| `StateVariableConfig` | `initial`           | `>= 0.0, <= 1.0`                    |
| `StateVariableConfig` | `mu`                | `>= 0.0, <= 1.0`                    |
| `StateVariableConfig` | `theta`             | `> 0.0`                             |
| `StateVariableConfig` | `sigma`             | `> 0.0`                             |
| `StateConfig`         | `variables`         | `len >= 1`                           |
| `TriggerIntervalConfig`| `min_seconds`      | `>= 1`                              |
| `TriggerIntervalConfig`| `max_seconds`      | `>= min_seconds`                    |
| `TriggerTypeConfig`   | `base_weight`       | `> 0.0`                             |
| `MemoryRecallConfig`  | `default_n`         | `>= 1`                              |
| `MemoryRecallConfig`  | `importance_weight` | `>= 0.0, <= 1.0`                    |
| `MemoryRecallConfig`  | `recency_weight`    | `>= 0.0, <= 1.0`                    |
| `MemoryDecayConfig`   | `recall_protection` | `>= 1.0`                            |
| `LLMConfig`           | `temperature`       | `>= 0.0, <= 2.0`                    |
| `LLMConfig`           | `max_tokens`        | `>= 1`                              |
| `LLMRetryConfig`      | `max_attempts`      | `>= 1`                              |
| `GeneralConfig`       | `tick_jitter`       | `>= 0.0, <= 1.0`                    |
| `GeneralConfig`       | `decay_every_n_ticks`| `>= 1`                             |

### 7.3. Кросс-валидация (после парсинга)

Выполняется в `load_config()` после Pydantic-валидации:

1. `trigger.interval.max_seconds >= trigger.interval.min_seconds` → иначе ошибка.
2. Если `trigger.interval.modulated_by` задан → он должен существовать в `state.variables`.
3. Для каждого `trigger.types[*].modulated_by` (если не null) → должен существовать в `state.variables`.
4. Для каждого `state.feedback[*]` → имена переменных в импульсах должны существовать в `state.variables`.
5. `intent.user_prompts` должен содержать ключ `"default"`.

---

## 8. Основной цикл (MainLoop)

Файл: `iskra/core/main_loop.py`

### 8.1. Инициализация

```python
class MainLoop:
    def __init__(self, config: IskraConfig):
        self.config = config
        self.running = False
        self.tick_count = 0
        self.last_tick_time = 0.0
        self.cooldown_until: float = 0.0

        # Создать компоненты
        self.state_engine = OUStateEngine(config.state)
        self.memory_store = create_memory_store(config.memory)
        self.trigger_types = create_trigger_types(config.trigger)
        self.trigger_engine = DefaultTriggerEngine(config.trigger, self.trigger_types, self.memory_store)
        self.intent_generator = Jinja2IntentGenerator(config.intent)
        self.llm_adapter = create_llm_adapter(config.llm)
        self.output_channel = create_output_channel(config.output)
        self.event_log = EventLog(config.logging.event_log)
```

### 8.2. Запуск

```python
async def run(self):
    self._write_pid_file()
    self._load_seed_memories()
    self.state_engine.apply_impulse("system_startup")
    self.running = True
    self.last_tick_time = time.monotonic()

    interval = self.trigger_engine.next_interval(self.state_engine.snapshot())
    logger.info(f"Iskra-1 запущена. Первый тик через {interval:.0f} секунд.")

    try:
        while self.running:
            await asyncio.sleep(interval)
            await self._process_tick()
            interval = self.trigger_engine.next_interval(self.state_engine.snapshot())
    except asyncio.CancelledError:
        pass
    finally:
        self._cleanup()
```

### 8.3. Обработка одного тика (_process_tick)

Полный алгоритм — см. EVENT_LIFECYCLE.md, раздел «Полная последовательность вызовов». Здесь фиксируем контракт:

**Предусловие:** `self.running == True`.

**Шаги:**
1. `elapsed = time.monotonic() - self.last_tick_time`
2. `self.state_engine.tick(elapsed)`
3. `state_before = self.state_engine.snapshot()`
4. Проверить cooldown: `if time.monotonic() < self.cooldown_until: return`
5. `event = self.trigger_engine.evaluate(state_before)`
6. Если `event is None` → return
7. `intent = self.intent_generator.generate(event)`
8. Вызвать LLM с retry-логикой (см. раздел 6.2)
9. При неудаче → записать ошибку в EventLog, return
10. `await self.output_channel.emit(...)`
11. `self.state_engine.apply_feedback(event.trigger_type, response.content)`
12. `state_after = self.state_engine.snapshot()`
13. `memory_id = self.memory_store.store(category=event.trigger_type, ...)`
14. `self.memory_store.store(category="last_context", content=response.content, importance=0.9)` — для `ContinueContextTrigger`
15. Если `tick_count % decay_every_n_ticks == 0` → `self.memory_store.decay()`
16. `self.event_log.record(EventLogEntry(...))`
17. `self.last_tick_time = time.monotonic()`
18. `self.tick_count += 1`

**Постусловие:** state обновлён, мысль выведена (или ошибка залогирована), EventLog записан.

**Гарантия:** шаги 1–4 выполняются ВСЕГДА. Шаги 5–18 обёрнуты в try/except — необработанное исключение никогда не убивает MainLoop.

### 8.4. Graceful shutdown

```python
def _cleanup(self):
    self.running = False
    self._remove_pid_file()
    logger.info("Iskra-1 остановлена.")
```

Сигналы: `SIGINT` (Ctrl+C) и `SIGTERM` вызывают `asyncio.CancelledError` через установку обработчика в `__main__.py`:

```python
loop = asyncio.get_event_loop()
for sig in (signal.SIGINT, signal.SIGTERM):
    loop.add_signal_handler(sig, main_task.cancel)
```

На Windows `SIGTERM` не поддерживается — используется только `KeyboardInterrupt` (обрабатывается asyncio автоматически).

### 8.5. PID-файл

- При запуске: записать `os.getpid()` в `config.general.pid_file`.
- Если файл уже существует и процесс с таким PID жив → `sys.exit(1)` с сообщением "Already running (PID: N)".
- Если файл существует, но процесс мёртв → перезаписать файл (stale PID).
- При завершении: удалить файл.

---

## 9. Реализации триггеров (MVP)

### 9.1. NewTopicTrigger

```python
class NewTopicTrigger:
    name = "new_topic"

    def __init__(self, config: TriggerTypeConfig, topic_pool: list[str]):
        self.base_weight = config.base_weight
        self.modulated_by = config.modulated_by
        self.modulation_strength = config.modulation_strength
        self.topic_pool = topic_pool

    def compute_weight(self, state: StateSnapshot) -> float:
        if self.modulated_by is None:
            return self.base_weight
        return self.base_weight * (1.0 + self.modulation_strength * state[self.modulated_by])

    def generate_context(self, memory: MemoryStore) -> list[MemoryRecord]:
        topic = random.choice(self.topic_pool)
        return [MemoryRecord(
            id="", timestamp=datetime.utcnow(), category="topic_pool",
            content=topic, importance=0.0, last_recall=datetime.utcnow(),
            recall_count=0, decay_rate=0.0
        )]
```

Возвращает pseudo-MemoryRecord с выбранной темой в `content`. Intent Generator использует `memory_context[0].content` как `{{ context }}`.

### 9.2. RecallMemoryTrigger

```python
class RecallMemoryTrigger:
    name = "recall_memory"

    def compute_weight(self, state: StateSnapshot) -> float:
        # аналогично NewTopicTrigger

    def generate_context(self, memory: MemoryStore) -> list[MemoryRecord]:
        return memory.recall(category=None, n=3)
```

### 9.3. ContinueContextTrigger

```python
class ContinueContextTrigger:
    name = "continue_context"

    def __init__(self, config: TriggerTypeConfig):
        self.base_weight = config.base_weight
        self.modulated_by = config.modulated_by
        self.modulation_strength = config.modulation_strength

    def compute_weight(self, state: StateSnapshot) -> float:
        if self.modulated_by is None:
            return self.base_weight
        return self.base_weight * (1.0 + self.modulation_strength * state[self.modulated_by])

    def generate_context(self, memory: MemoryStore) -> list[MemoryRecord]:
        return memory.recall(category="last_context", n=1)
```

Последний ответ LLM сохраняется в Memory Store с `category="last_context"` на шаге 7b постобработки (см. раздел 8.3). Это позволяет `ContinueContextTrigger` работать через стандартный `recall()` — как и все остальные триггеры.

Если записей с `category="last_context"` ещё нет (первый тик) → `memory_context` пуст, Intent Generator использует шаблон `default`.

Побочный эффект: со временем в Memory Store накапливается несколько `last_context` записей. Стохастический recall иногда может извлечь не самую последнюю, а более старую — система «вернётся» к мысли, которую думала час назад. Это поведение аналогично человеческому и считается полезным.

### 9.4. MetaReflectionTrigger

```python
class MetaReflectionTrigger:
    name = "meta_reflection"

    def generate_context(self, memory: MemoryStore) -> list[MemoryRecord]:
        return []  # саморефлексии не нужен контекст
```

---

## 10. EventLog

Файл: `iskra/event_log.py`

### 10.1. Формат

JSON Lines (`.jsonl`): один JSON-объект на строку, без prettify.

```json
{"event_id":"550e8400-...","timestamp":"2026-04-11T03:42:17Z","trigger_type":"new_topic","state_before":{"curiosity":0.72,"restlessness":0.38,"nostalgia":0.15},"state_after":{"curiosity":0.67,"restlessness":0.41,"nostalgia":0.18},"memory_ids_recalled":[],"prompt_system":"...","prompt_user":"...","llm_response":"...","llm_model":"mock","llm_tokens":0,"llm_latency_ms":100,"memory_id_stored":"7c9e6679-...","output_channel":"console","errors":[]}
```

### 10.2. Ротация

При достижении `rotate_mb` МБ:
1. Переименовать `events.jsonl` → `events.jsonl.1` (если `.1` существует → `.2`, и т.д.).
2. Создать новый `events.jsonl`.
3. Максимум 10 ротаций (`.1` до `.10`), после чего старший удаляется.

### 10.3. Запись ошибок

При ошибке на любой фазе (без полного цикла) — записать частичный EventLogEntry с заполненным `errors` и пустыми полями LLM-ответа:

```python
def record_error(self, event_id: str, error_msg: str):
    self.record(EventLogEntry(
        event_id=event_id,
        timestamp=datetime.utcnow().isoformat(),
        trigger_type="",
        state_before={}, state_after={},
        memory_ids_recalled=[], prompt_system="", prompt_user="",
        llm_response="", llm_model="", llm_tokens=0, llm_latency_ms=0,
        memory_id_stored=None, output_channel="",
        errors=[error_msg]
    ))
```

---

## 11. Обработка ошибок — полная таблица

| Фаза                 | Ошибка                           | Код реакции                                          |
|----------------------|----------------------------------|------------------------------------------------------|
| Config load          | Файл не найден                   | `sys.exit(1)` с сообщением                          |
| Config load          | YAML parse error                 | `sys.exit(1)` с сообщением                          |
| Config load          | Pydantic validation error        | `sys.exit(1)` с деталями                             |
| Config load          | `${VAR}` не задана               | `sys.exit(1)` с именем переменной                    |
| Config load          | Кросс-валидация failed           | `sys.exit(1)` с деталями                             |
| PID file             | Already running                  | `sys.exit(1)` с PID                                  |
| State tick           | —                                | Невозможно (чистая математика)                       |
| Trigger evaluate     | Memory recall error              | `memory_context = []`, continue                      |
| Trigger evaluate     | Нет зарегистрированных триггеров | `logger.warning`, пропустить тик                     |
| Intent generate      | Шаблон не найден для trigger_type| Использовать `"default"`, `logger.warning`           |
| Intent generate      | Jinja2 render error              | `logger.error`, пропустить тик                       |
| LLM complete         | Timeout                          | Retry до max_attempts, потом пропустить              |
| LLM complete         | Rate limit (429)                 | `cooldown_until = now + cooldown_seconds`, пропустить|
| LLM complete         | Network error                    | Retry до max_attempts, потом пропустить              |
| LLM complete         | `is_available() == False`        | Пропустить тик, `logger.warning`                     |
| Output emit          | Channel error                    | Fallback на `print()` в stderr                       |
| Memory store         | SQLite write error               | `logger.warning`, continue (мысль потеряна)          |
| Memory decay         | SQLite error                     | `logger.warning`, continue                           |
| EventLog write       | I/O error                        | `sys.stderr.write(...)`, continue                    |

**Золотое правило:** после успешной загрузки конфигурации MainLoop **никогда не падает** из-за ошибки в одном компоненте.

---

## 12. Логирование

### 12.1. Python logging

Имена логгеров по компонентам:

| Логгер                  | Используется в                |
|-------------------------|-------------------------------|
| `iskra`                 | `__main__.py`                 |
| `iskra.core.main_loop`  | `MainLoop`                    |
| `iskra.core.state`      | `OUStateEngine`               |
| `iskra.core.trigger`    | `DefaultTriggerEngine`        |
| `iskra.core.intent`     | `Jinja2IntentGenerator`       |
| `iskra.memory`          | `SQLiteMemoryStore`           |
| `iskra.llm`             | Все LLM-адаптеры              |
| `iskra.output`          | Все каналы вывода             |
| `iskra.event_log`       | `EventLog`                    |

### 12.2. Уровни логирования

| Уровень   | Когда используется                                      |
|-----------|---------------------------------------------------------|
| `DEBUG`   | Значения переменных на каждом тике, детали OU-расчётов  |
| `INFO`    | Запуск, остановка, каждая сгенерированная мысль         |
| `WARNING` | Пропуск тика, fallback на default шаблон, ошибки recall |
| `ERROR`   | Ошибки LLM, ошибки записи в БД                         |

---

## 13. Фабрики компонентов

Каждый компонент создаётся через фабричную функцию, определяемую в соответствующем `__init__.py`.

### 13.1. create_memory_store

```python
def create_memory_store(config: MemoryConfig) -> MemoryStore:
    if config.backend == "sqlite":
        return SQLiteMemoryStore(config)
    raise ValueError(f"Unknown memory backend: {config.backend}")
```

### 13.2. create_llm_adapter

```python
def create_llm_adapter(config: LLMConfig) -> LLMAdapter:
    adapter_name = config.adapter
    settings = config.settings.get(adapter_name, {})
    if adapter_name == "mock":
        return MockAdapter(settings)
    if adapter_name == "ollama":
        return OllamaAdapter(settings, config)
    raise ValueError(f"Unknown LLM adapter: {adapter_name}")
```

### 13.3. create_output_channel

```python
def create_output_channel(config: OutputConfig) -> OutputChannel:
    channel_name = config.channel
    settings = config.settings.get(channel_name, {})
    if channel_name == "console":
        return ConsoleOutput(settings)
    if channel_name == "file":
        return FileOutput(settings)
    raise ValueError(f"Unknown output channel: {channel_name}")
```

### 13.4. create_trigger_types

```python
def create_trigger_types(config: TriggerConfig) -> list[TriggerType]:
    mapping = {
        "new_topic": lambda cfg: NewTopicTrigger(cfg, config.random_topic_pool),
        "recall_memory": lambda cfg: RecallMemoryTrigger(cfg),
        "continue_context": lambda cfg: ContinueContextTrigger(cfg),
        "meta_reflection": lambda cfg: MetaReflectionTrigger(cfg),
    }
    result = []
    for name, type_config in config.types.items():
        factory = mapping.get(name)
        if factory is None:
            logger.warning(f"Unknown trigger type: {name}, skipping")
            continue
        result.append(factory(type_config))
    return result
```

Все триггеры получают контекст через `generate_context(memory: MemoryStore)` — единый интерфейс. `MemoryStore` передаётся в `evaluate()` Trigger Engine, а не в конструктор триггера.

---

## 14. Инварианты системы

Свойства, которые должны выполняться ВСЕГДА после инициализации:

1. **INV-STATE:** Все переменные состояния ∈ [0.0, 1.0].
2. **INV-MEMORY:** Все importance ∈ [min_importance, 1.0].
3. **INV-MEMORY-2:** recall_count >= 0 для всех записей.
4. **INV-LOOP:** MainLoop не завершается аварийно после успешного `__init__`.
5. **INV-CONFIG:** После загрузки конфигурации все кросс-ссылки (modulated_by → variables, trigger_type → prompts) корректны.
6. **INV-LOG:** Каждый тик с event != None порождает ровно одну запись в EventLog (полную или с ошибками).
7. **INV-PID:** Не более одного экземпляра Iskra-1 на один pid_file.
8. **INV-INTERVAL:** Интервал между тиками ∈ [min_seconds * (1 - jitter), max_seconds * (1 + jitter)].

---

## 15. Тестирование (контракты для тестов)

### 15.1. Unit-тесты

| Компонент         | Тест                                                            | Ожидание                                        |
|-------------------|-----------------------------------------------------------------|--------------------------------------------------|
| OUStateEngine     | tick(600) с theta=0.05, sigma=0                                 | x сдвигается к mu (детерминированно при sigma=0) |
| OUStateEngine     | apply_impulse("system_startup")                                 | curiosity увеличивается на 0.20                  |
| OUStateEngine     | snapshot() возвращает копию                                     | Мутация snapshot не меняет внутреннее состояние  |
| OUStateEngine     | все переменные clamped после tick/impulse                       | Все значения ∈ [0.0, 1.0]                       |
| TriggerEngine     | evaluate() при одном зарегистрированном типе                    | Всегда возвращает этот тип                       |
| TriggerEngine     | next_interval() при restlessness=0                              | Близко к max_seconds                             |
| TriggerEngine     | next_interval() при restlessness=1                              | Близко к min_seconds                             |
| SQLiteMemoryStore | store → recall возвращает сохранённую запись                    | content совпадает                                |
| SQLiteMemoryStore | recall обновляет recall_count                                   | recall_count == 1 после первого recall           |
| SQLiteMemoryStore | decay снижает importance                                        | importance после decay < importance до           |
| SQLiteMemoryStore | decay не ниже min_importance                                    | importance >= min_importance                     |
| MockAdapter       | complete возвращает LLMResponse                                 | content непуст, model == "mock"                  |
| IntentGenerator   | generate с trigger_type="new_topic"                             | user_prompt содержит тему                        |
| IntentGenerator   | generate с неизвестным trigger_type                             | Использует default шаблон                        |
| evaluate_condition| "ends_with_question_mark" + "Hello?"                            | True                                             |
| evaluate_condition| "length_lt_50" + "short"                                       | True                                             |
| evaluate_condition| "trigger_type_eq_recall_memory" + "recall_memory"               | True                                             |
| compute_importance| response > 300 chars + has "?"                                  | 0.7                                              |
| EventLog          | record → read back from file                                   | JSON парсится, поля совпадают                    |
| Config            | load valid config.yaml                                          | IskraConfig без ошибок                           |
| Config            | load config с theta=0                                           | ValidationError                                  |
| Config            | load config без variables                                       | ValidationError                                  |

### 15.2. Integration-тесты

| Тест                                    | Описание                                                  |
|------------------------------------------|-----------------------------------------------------------|
| Cold start → 3 тика                     | Запуск с mock adapter, дождаться 3 мыслей, проверить лог |
| Decay после 10 тиков                    | Importance записей снизилась                              |
| Feedback loop                            | После recall_memory тика nostalgia снижена               |
| ContinueContext через Memory Store       | После 2 тиков continue_context возвращает ответ 1-го тика|
| Config change → different behavior       | Высокий sigma → большая дисперсия state за 20 тиков      |

### 15.3. Запуск тестов

```bash
python -m pytest tests/ -v
```

---

## 16. Перечень файлов для реализации (приоритет)

Порядок реализации совпадает с зависимостями: нельзя реализовать компонент, зависящий от ещё не реализованного.

| #  | Файл                              | Зависит от          | Примечание                  |
|----|------------------------------------|---------------------|-----------------------------|
| 1  | `iskra/models.py`                  | —                   | Все dataclass'ы             |
| 2  | `iskra/core/config.py`            | models              | Pydantic + load_config      |
| 3  | `iskra/core/state_engine.py`      | config, models      | OUStateEngine               |
| 4  | `iskra/memory/protocol.py`        | models              | MemoryStore Protocol        |
| 5  | `iskra/memory/sqlite_store.py`    | protocol, config    | SQLiteMemoryStore           |
| 6  | `iskra/triggers/protocol.py`      | models              | TriggerType Protocol        |
| 7  | `iskra/triggers/new_topic.py`     | protocol            | NewTopicTrigger             |
| 8  | `iskra/triggers/recall_memory.py` | protocol            | RecallMemoryTrigger         |
| 9  | `iskra/triggers/continue_context.py`| protocol          | ContinueContextTrigger      |
| 10 | `iskra/triggers/meta_reflection.py`| protocol           | MetaReflectionTrigger       |
| 11 | `iskra/core/trigger_engine.py`    | triggers, state     | DefaultTriggerEngine        |
| 12 | `iskra/core/intent_generator.py`  | config, models      | Jinja2IntentGenerator       |
| 13 | `iskra/llm/protocol.py`           | models              | LLMAdapter Protocol         |
| 14 | `iskra/llm/mock_adapter.py`       | protocol            | MockAdapter                 |
| 15 | `iskra/llm/ollama_adapter.py`     | protocol            | OllamaAdapter               |
| 16 | `iskra/output/protocol.py`        | models              | OutputChannel Protocol      |
| 17 | `iskra/output/console_output.py`  | protocol            | ConsoleOutput               |
| 18 | `iskra/output/file_output.py`     | protocol            | FileOutput                  |
| 19 | `iskra/event_log.py`              | models              | EventLog                    |
| 20 | `iskra/core/main_loop.py`         | ВСЕ вышеперечисленные| MainLoop                   |
| 21 | `iskra/__main__.py`               | main_loop, config   | CLI-точка входа             |
| 22 | `config.yaml` (корень репозитория) | —                | Эталонный конфиг            |
| 23 | `tests/`                          | ВСЕ                 | Тесты                       |

---

## Приложение A. Ссылки на исходные документы

Все перечисленные ниже файлы с расширениями `.md` и `.txt` лежат в каталоге **`docs/`** репозитория.

| Документ                    | Что определяет для этой спецификации         |
|-----------------------------|----------------------------------------------|
| ТЕХНИЧЕСКОЕ ЗАДАНИЕ.txt v2.1 | Цели, use-case'ы, acceptance criteria        |
| ARCHITECTURE.md             | Высокоуровневая архитектура                  |
| STATE_ENGINE.md             | OU-модель, формулы дрейфа, таблицы импульсов |
| TRIGGER_ENGINE.md           | Формулы весов, алгоритм evaluate             |
| MEMORY_SYSTEM.md            | Формулы recall/decay, SQLite-схема           |
| INTENT_GENERATOR.md         | Шаблоны промптов, SparkEvent                 |
| GROK_INTEGRATION.md         | LLMAdapter Protocol, адаптеры                |
| EVENT_LIFECYCLE.md          | Полный поток данных, обработка ошибок        |
| CONFIG_SCHEMA.md            | Pydantic-модели, эталонный config.yaml       |
| PSYCHOLOGY_MODEL.md         | Биологическая мотивация архитектуры          |
| TECHNOLOGIES.md             | Технологический ландшафт                     |
