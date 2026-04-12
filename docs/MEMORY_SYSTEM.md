# Система памяти

## Принцип

Память — это то, что отличает организм от рефлекса. Даже у улитки есть простейшая ассоциативная память: «тут было больно → не ползу сюда». Iskra-1 начинает с минимальной реализации и оставляет чёткий путь к усложнению.

## Уровень 0 — MVP (SQLite / JSON-файл)

Простейшее хранилище записей:

```
┌────────────────────────────────────────────────────────────────┐
│ Memory Record                                                  │
├──────────────┬─────────────────────────────────────────────────┤
│ id           │ UUID                                            │
│ timestamp    │ когда записано                                  │
│ category     │ строка-тег (свободная таксономия)               │
│ content      │ текст воспоминания                              │
│ importance   │ 0.0–1.0 (определяет вероятность «всплытия»)     │
│ last_recall  │ когда последний раз извлекалось                 │
│ recall_count │ сколько раз извлекалось                         │
│ decay_rate   │ скорость «забывания» (снижение importance)      │
└──────────────┴─────────────────────────────────────────────────┘
```

### Операции и формулы:

#### store(category, content, importance) → str

Сохранить новую запись. Возвращает `id` (UUID).

```python
record = MemoryRecord(
    id=str(uuid4()),
    timestamp=datetime.utcnow(),
    category=category,
    content=content,
    importance=clamp(importance, 0.0, 1.0),
    last_recall=datetime.utcnow(),
    recall_count=0,
    decay_rate=config.memory.decay.base_rate  # по умолчанию 0.01
)
```

#### recall(category?, n?, context?) → list[MemoryRecord]

Извлечь `n` записей (по умолчанию 3). Алгоритм:

**Шаг 1.** Отфильтровать по `category` (если задана). Если записей 0 → вернуть `[]`.

**Шаг 2.** Для каждой записи `r` вычислить `score`:
```
hours_since = (now - r.last_recall).total_seconds() / 3600.0
recency = 1.0 / (1.0 + hours_since)
score = r.importance * importance_weight + recency * recency_weight
```
Где `importance_weight = 0.7`, `recency_weight = 0.3` (из конфигурации).

**Шаг 3.** Стохастический выбор (roulette-wheel selection):
```python
selected = random.choices(records, weights=[r.score for r in records], k=min(n, len(records)))
```
Это даёт элемент неожиданности: не всегда выбираются top-N, иногда «всплывает» что-то неожиданное.

Альтернатива (настраиваемая): `selection: "top_n"` — жёсткий выбор N записей с наибольшим score.

**Шаг 4.** Обновить метаданные:
```python
for record in selected:
    record.last_recall = datetime.utcnow()
    record.recall_count += 1
```

#### decay() → None

Периодически (каждые N тиков, из конфигурации) снизить `importance` у всех записей. Моделирует забывание.

**Формула:**
```
hours_since = (now - record.last_recall).total_seconds() / 3600.0
protection = 1.0 / (1.0 + record.recall_count / recall_protection)
effective_rate = record.decay_rate * protection
new_importance = record.importance * (1.0 - effective_rate * hours_since / 24.0)
record.importance = max(min_importance, new_importance)
```

Где:
- `recall_protection = 1.5` — чем чаще вспоминали, тем медленнее забывается.
- `min_importance = 0.01` — полностью не забываем никогда (воспоминание можно извлечь, но с низкой вероятностью).

**Пример поведения decay:**

| recall_count | protection | effective_rate (при base_rate=0.01) |
|-------------|------------|-------------------------------------|
| 0           | 1.00       | 0.0100 (обычная скорость)           |
| 1           | 0.60       | 0.0060 (замедленное)                |
| 3           | 0.33       | 0.0033 (значительно замедленное)    |
| 10          | 0.13       | 0.0013 (почти не забывается)        |

Часто вспоминаемые записи практически не забываются — как «Маша-память» у человека.

### Начальное наполнение (seed memories):

При первом запуске пользователь может загрузить «стартовые воспоминания» из YAML-файла (путь задаётся в `config.memory.initial_memories_file`). Они составят «личность» системы.

```yaml
memories:
  - category: "self"
    content: "Я — Iskra-1, экспериментальная система искусственной интенции."
    importance: 0.9
  - category: "philosophy"
    content: "Между запросами у LLM нет ничего — только потенциал."
    importance: 0.8
```

### SQLite-схема (MVP):

```sql
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    importance REAL NOT NULL DEFAULT 0.5,
    last_recall TEXT NOT NULL,
    recall_count INTEGER NOT NULL DEFAULT 0,
    decay_rate REAL NOT NULL DEFAULT 0.01
);

CREATE INDEX idx_memories_category ON memories(category);
CREATE INDEX idx_memories_importance ON memories(importance DESC);
```

## Уровень 1 — Категоризированная память

Добавляются **именованные коллекции** (аналог того, что в переписке называлось «Маша-память»):

- Каждая коллекция — это пространство имён внутри одного хранилища.
- Пользователь создаёт коллекции под свои нужды: `people`, `hobbies`, `ideas`, `conversations`, ...
- Trigger Engine может целенаправленно обращаться к конкретной коллекции.

## Уровень 2 — Векторная память (семантический поиск)

Замена (или дополнение) SQLite на **векторную базу** (Chroma, FAISS, LanceDB):

- Записи превращаются в эмбеддинги.
- `recall()` ищет не по категории, а по **смыслу**: «найди что-нибудь похожее на текущий контекст».
- Это даёт **ассоциативность**: система может «вспомнить» нечто неожиданное, связанное по смыслу, а не по тегу.

## Уровень 3 — Граф связей

Записи связываются друг с другом направленными рёбрами:
- «это воспоминание вызвало то воспоминание»
- «этот человек связан с этим хобби»

Граф позволяет делать **цепочки ассоциаций** — ближе к тому, как работает человеческая память.

## Интерфейс (абстракция)

```python
class MemoryStore(Protocol):
    def store(self, category: str, content: str, importance: float) -> str: ...
    def recall(self, category: str | None, n: int, context: str | None) -> list[MemoryRecord]: ...
    def decay(self) -> None: ...
```

Любая реализация (SQLite, Chroma, граф, что угодно) подключается через этот интерфейс.
