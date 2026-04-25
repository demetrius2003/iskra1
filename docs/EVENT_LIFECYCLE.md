# Event Lifecycle (Жизненный цикл события)

## Назначение

Этот документ описывает полный путь одного «импульса» от зарождения до выхода. Младшая модель (или новый разработчик) должна прочитать этот файл и точно знать: какие функции вызываются, в каком порядке, какие данные передаются между компонентами, и что происходит при ошибках.

---

## Обзор потока

```
                         Основной цикл (MainLoop)
                                  │
          ┌───────────────────────┼───────────────────────┐
          ▼                       │                       │
   ┌─────────────┐                │               ┌──────────────┐
   │ State Engine │  ◄─ feedback ─┘               │   External   │
   │   .tick()    │                                │   Events     │
   └──────┬──────┘                                └──────┬───────┘
          │ snapshot                                      │ impulse
          ▼                                              │
   ┌─────────────┐                                       │
   │   Trigger    │ ◄────────────────────────────────────┘
   │   Engine     │
   │  .evaluate() │
   └──────┬──────┘
          │ SparkEvent (или None)
          ▼
   ┌──────────────┐
   │   Memory     │
   │   Store      │
   │  .recall()   │
   └──────┬──────┘
          │ memories: list[MemoryRecord]
          ▼
   ┌──────────────┐
   │   Intent     │
   │   Generator  │
   │  .generate() │
   └──────┬──────┘
          │ (system_prompt, user_prompt)
          ▼
   ┌──────────────┐
   │    LLM       │
   │   Adapter    │
   │  .complete() │
   └──────┬──────┘
          │ response: str
          ▼
   ┌──────────────┐
   │   Output     │
   │   Channel    │
   │  .emit()     │
   └──────┬──────┘
          │
          ▼
   ┌──────────────┐
   │  Post-       │
   │  Processing  │
   │  (feedback + │
   │   store)     │
   └──────────────┘
```

---

## Фазы жизненного цикла

### Фаза 0: Тик основного цикла

**Кто:** `MainLoop` (главный управляющий цикл, `iskra/core/main_loop.py`)

**Что:** Просыпается после `sleep(interval)`, где `interval` вычислен на предыдущем тике.

**Внешний ввод (файл):** если задан `general.external_input_file` и в файле есть непустой UTF-8 текст, **после** проверки кулдауна/доступности LLM (и до выбора триггера) вызывается `apply_impulse("user_message")`, текст читается и передаётся в `SparkEvent.metadata["external_input"]` и в Jinja2 как `external_input`. После **успешного** `emit` файл по умолчанию очищается. Подробно: [CONFIG_SCHEMA.md](CONFIG_SCHEMA.md) § `general`, [INTENT_GENERATOR.md](INTENT_GENERATOR.md).

```python
while self.running:
    elapsed = time.monotonic() - self.last_tick_time

    # Фаза 1: обновить состояние
    self.state_engine.tick(elapsed)

    # Фаза 2: проверить триггер
    event = self.trigger_engine.evaluate(self.state_engine.snapshot())

    if event is not None:
        # Фазы 3–7
        self._process_event(event)

    # Вычислить следующий интервал
    interval = self.trigger_engine.next_interval(self.state_engine.snapshot())
    self.last_tick_time = time.monotonic()
    await asyncio.sleep(interval)
```

---

### Фаза 1: Обновление состояния (State Engine)

**Вход:**
```python
elapsed: float  # секунды с последнего тика
```

**Действие:** Для каждой переменной применить OU-дрейф + обработать очередь внешних событий (если есть). См. `STATE_ENGINE.md`.

**Выход:**
```python
StateSnapshot = dict[str, float]
# Пример: {"curiosity": 0.62, "restlessness": 0.41, "nostalgia": 0.18}
```

**Ошибки:** невозможны (чистые вычисления).

---

### Фаза 2: Оценка триггера (Trigger Engine)

**Вход:**
```python
state: StateSnapshot
```

**Действие:**
1. Для каждого зарегистрированного типа триггера вычислить взвешенную вероятность `w_i = trigger_i.compute_weight(state)`.
2. Нормализовать: `p_i = w_i / sum(all w)`.
3. Стохастически выбрать один тип (weighted random choice).
4. Вызвать `trigger_i.generate_context(memory_store)` для получения контекста.

**Выход:**
```python
@dataclass
class SparkEvent:
    id: str                           # UUID события
    trigger_type: str                 # "new_topic", "recall_memory", ...
    state_snapshot: dict[str, float]  # копия состояния на момент события
    memory_context: list[str]         # извлечённые воспоминания (может быть [])
    timestamp: datetime               # UTC
    metadata: dict                    # произвольные данные от триггера
```

Если на этом тике решено промолчать — возвращается `None`, цикл переходит к `sleep`.

**Ошибки:** если `memory_store.recall()` упал — ловим, ставим `memory_context = []`, продолжаем. Мысль без воспоминаний лучше, чем падение.

---

### Фаза 3: Извлечение контекста из памяти (Memory Store)

> Примечание: эта фаза вызывается изнутри Trigger Engine на фазе 2 (при generate_context). Выделяем отдельно для ясности.

**Вход:**
```python
category: str | None      # None = любая категория
n: int                    # сколько записей вернуть (по умолчанию 3)
context: str | None       # подсказка для семантического поиска (будущее)
```

**Действие:**
1. Отфильтровать записи по `category` (если задана).
2. Для каждой записи вычислить `score`:
   ```
   recency = 1.0 / (1.0 + hours_since_last_recall)
   score = importance * 0.7 + recency * 0.3
   ```
3. Стохастический выбор: `n` записей с вероятностью пропорциональной `score` (roulette-wheel selection), а не жёсткий top-N. Это даёт элемент неожиданности.
4. Обновить `last_recall` и `recall_count` у выбранных записей.

**Выход:**
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

**Ошибки:** при ошибке доступа к БД — вернуть `[]`.

---

### Фаза 4: Генерация намерения (Intent Generator)

**Вход:**
```python
event: SparkEvent
```

**Действие:**
1. Загрузить шаблон system prompt из конфигурации.
2. Подставить значения `state_snapshot` в шаблон.
3. Загрузить шаблон user prompt по `event.trigger_type`.
4. Подставить `event.memory_context` и метаданные.
5. Вернуть пару промптов.

**Выход:**
```python
@dataclass
class IntentPayload:
    event_id: str       # тот же UUID, что у SparkEvent
    system_prompt: str
    user_prompt: str
    trigger_type: str   # для логирования и обратной связи
    timestamp: datetime
```

**Ошибки:** если шаблон не найден для данного `trigger_type` — использовать дефолтный шаблон и записать warning в лог.

---

### Фаза 5: Вызов LLM (LLM Adapter)

**Вход:**
```python
system_prompt: str
user_prompt: str
```

**Действие:**
1. Проверить `is_available()`. Если нет — пропустить, записать в лог.
2. Отправить промпт в LLM.
3. Дождаться ответа (таймаут из конфигурации, по умолчанию 60 секунд).
4. При ошибке: retry до 3 раз с экспоненциальным backoff (1с, 2с, 4с).

**Выход:**
```python
@dataclass
class LLMResponse:
    event_id: str         # тот же UUID
    content: str          # текстовый ответ
    model: str            # какая модель ответила
    tokens_used: int      # для учёта расхода
    latency_ms: int       # для метрик
    timestamp: datetime
```

**Ошибки:**
- Таймаут → лог + пропуск (мысль «не дозрела»).
- Rate limit (429) → Trigger Engine переходит в тихий режим на `cooldown_seconds` из конфигурации.
- Другая ошибка → лог + пропуск.

---

### Фаза 6: Вывод (Output Channel)

**Вход:**
```python
event_id: str
thought: str        # текст мысли (content из LLMResponse)
trigger_type: str
state_snapshot: dict[str, float]
timestamp: datetime
```

**Действие:** зависит от реализации.

| Канал          | Действие                                             |
|----------------|------------------------------------------------------|
| `ConsoleOutput`| Напечатать с форматированием (rich) в stdout          |
| `FileOutput`   | Дозаписать в файл `thoughts.log`                     |
| `TelegramOutput`| Отправить сообщение в указанный чат                 |
| `WebSocketOutput`| Пушнуть в веб-интерфейс                           |

**Формат вывода (консоль, MVP):**
```
═══════════════════════════════════════════════════════
🔥 [2026-04-11 03:42:17] Мысль #47 (new_topic)
───────────────────────────────────────────────────────
Состояние: curiosity=0.72 restlessness=0.38 nostalgia=0.15

А что если гравитация — это не сила, а побочный эффект
термодинамики пространства-времени? Энтропийная гравитация
Верлинде предполагает именно это...
═══════════════════════════════════════════════════════
```

**Ошибки:** при ошибке канала (сеть для Telegram, и т.д.) — fallback на ConsoleOutput.

---

### Фаза 7: Постобработка (Feedback Loop)

Эта фаза замыкает цикл: мысли влияют на состояние и сохраняются в памяти.

**Шаг 7a: Обратная связь в State Engine**
```python
state_engine.apply_feedback(
    trigger_type=event.trigger_type,
    llm_response=response.content
)
```
Применяет импульсы по таблице из `STATE_ENGINE.md` (раздел «Модификация от внутренних событий»).

**Шаг 7b: Сохранение в Memory Store**

Каждый ответ LLM сохраняется дважды:

```python
# 1. Основная запись — по типу триггера (для recall_memory и аналитики)
memory_store.store(
    category=event.trigger_type,
    content=response.content,
    importance=compute_importance(event, response)
)

# 2. Метка последнего контекста — для ContinueContextTrigger
memory_store.store(
    category="last_context",
    content=response.content,
    importance=0.9
)
```

Вторая запись (`last_context`) позволяет `ContinueContextTrigger` работать через обычный `recall(category="last_context", n=1)` — без специальных зависимостей на MainLoop. Со временем записей `last_context` накапливается несколько; стохастический recall иногда может извлечь не самую свежую, что создаёт эффект «возврата к старой мысли» — поведение, аналогичное человеческому.

Функция `compute_importance` на MVP:
```python
def compute_importance(event: SparkEvent, response: LLMResponse) -> float:
    base = 0.5
    if len(response.content) > 300:
        base += 0.1  # длинные мысли — важнее
    if "?" in response.content:
        base += 0.1  # мысли с вопросами — важнее (стимулируют развитие)
    if event.trigger_type == "meta_reflection":
        base += 0.15  # саморефлексия — редкая и ценная
    return min(1.0, base)
```

**Шаг 7c: Decay (забывание)**

Каждые N тиков (настраиваемый параметр, по умолчанию каждые 10 тиков):
```python
memory_store.decay()
```

Формула decay для каждой записи:
```
new_importance = importance * (1.0 - decay_rate * hours_since_last_recall / 24.0)
new_importance = max(0.01, new_importance)  # не забываем полностью
```

**Шаг 7d: Запись в EventLog**

Каждый полный цикл записывается в лог для метрик и отладки:
```python
@dataclass
class EventLogEntry:
    event_id: str
    timestamp: datetime
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

Хранилище лога: JSON Lines файл (`events.jsonl`), одна строка на событие. Формат легко парсится, легко анализируется скриптами.

---

## Полная последовательность вызовов (псевдокод)

```python
async def process_tick(self):
    t0 = time.monotonic()
    elapsed = t0 - self.last_tick_time

    # 1. Drift state
    self.state_engine.tick(elapsed)
    state_before = self.state_engine.snapshot()

    # 2. Evaluate trigger
    event = self.trigger_engine.evaluate(state_before)
    if event is None:
        self.last_tick_time = t0
        return

    # 3. Memory is already populated inside trigger_engine.evaluate()
    # (via generate_context → memory_store.recall)

    # 4. Generate intent
    intent = self.intent_generator.generate(event)

    # 5. Call LLM
    try:
        response = await self.llm_adapter.complete(
            intent.system_prompt, intent.user_prompt
        )
    except LLMUnavailableError:
        self.event_log.record_error(event.id, "llm_unavailable")
        self.last_tick_time = t0
        return

    # 6. Output
    await self.output_channel.emit(
        event_id=event.id,
        thought=response.content,
        trigger_type=event.trigger_type,
        state_snapshot=state_before,
        timestamp=event.timestamp
    )

    # 7a. Feedback to state
    self.state_engine.apply_feedback(event.trigger_type, response.content)
    state_after = self.state_engine.snapshot()

    # 7b. Store in memory
    importance = compute_importance(event, response)
    memory_id = self.memory_store.store(
        category=event.trigger_type,
        content=response.content,
        importance=importance
    )
    self.memory_store.store(
        category="last_context",
        content=response.content,
        importance=0.9
    )

    # 7c. Periodic decay
    self.tick_count += 1
    if self.tick_count % self.config.decay_every_n_ticks == 0:
        self.memory_store.decay()

    # 7d. Log
    self.event_log.record(EventLogEntry(
        event_id=event.id,
        timestamp=event.timestamp,
        trigger_type=event.trigger_type,
        state_before=state_before,
        state_after=state_after,
        memory_ids_recalled=[m.id for m in event.memory_context],
        prompt_system=intent.system_prompt,
        prompt_user=intent.user_prompt,
        llm_response=response.content,
        llm_model=response.model,
        llm_tokens=response.tokens_used,
        llm_latency_ms=response.latency_ms,
        memory_id_stored=memory_id,
        output_channel=self.output_channel.name,
        errors=[]
    ))

    self.last_tick_time = time.monotonic()
```

---

## Обработка ошибок — сводная таблица

| Фаза         | Ошибка                    | Реакция                                   |
|--------------|---------------------------|--------------------------------------------|
| State tick   | —                         | Невозможна (чистая математика)             |
| Trigger eval | Memory recall failed      | `memory_context = []`, продолжить          |
| Trigger eval | No triggers registered    | Лог warning, пропустить тик                |
| Intent gen   | Template not found        | Использовать дефолтный шаблон              |
| LLM call     | Timeout (> 60s)           | Лог, пропустить мысль                      |
| LLM call     | Rate limit (429)          | Тихий режим на `cooldown_seconds`          |
| LLM call     | Network error             | Retry 3x с backoff, потом пропустить       |
| LLM call     | `is_available() == False` | Пропустить, попробовать на следующем тике  |
| Output       | Channel error             | Fallback на ConsoleOutput                  |
| Memory store | DB write error            | Лог warning, не падать                     |
| Event log    | Write error               | stderr warning, не падать                  |

**Золотое правило:** Iskra-1 **никогда не падает** из-за ошибки в одном компоненте. Мысль может быть потеряна, но демон продолжает работать. Стабильность важнее полноты.

---

## Метрики (извлекаемые из EventLog)

Из `events.jsonl` можно вычислить:

| Метрика                           | Формула                                    |
|-----------------------------------|--------------------------------------------|
| Мыслей в час                      | `count(events) / hours`                    |
| Среднее время отклика LLM         | `avg(llm_latency_ms)`                      |
| Разнообразие типов триггеров      | Энтропия Шеннона по `trigger_type`         |
| Средняя длина мысли               | `avg(len(llm_response))`                   |
| Использование памяти              | `% событий, где memory_ids_recalled != []` |
| Частота ошибок                    | `% событий с непустым errors`              |
| Дрейф состояния                   | Дисперсия `state_before` по скользящему окну|
| Стоимость за час                  | `sum(llm_tokens) * price_per_token`        |
