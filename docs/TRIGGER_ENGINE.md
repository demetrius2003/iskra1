# Trigger Engine (Генератор событий)

## Что это

Trigger Engine — это **сердцебиение** Iskra-1. Это демон, который работает непрерывно и на каждом «тике» решает: породить мысль или промолчать. Именно он превращает пассивную систему в активную — даёт ей ту самую «искру».

## Аналогия из биологии

У улитки нервная система генерирует спонтанную активность даже без внешних стимулов. Нейроны «шумят». Иногда этот шум складывается в паттерн, который запускает действие. Trigger Engine — это тот самый нейронный шум.

## Минимальная реализация (v0.01)

### Интервал между тиками

Бесконечный цикл с **переменным интервалом** между итерациями. Интервал модулируется переменной `restlessness` из State Engine.

**Параметры (из конфигурации):**
```
min_interval = 180   # секунд (3 мин)
max_interval = 900   # секунд (15 мин)
modulated_by = "restlessness"
tick_jitter  = 0.1   # ±10% случайный разброс
```

**Формула вычисления интервала:**
```
base = max_interval - (max_interval - min_interval) * state[modulated_by]
interval = base * (1.0 + uniform(-tick_jitter, +tick_jitter))
```

| restlessness | base (сек) | диапазон с jitter ±10%  |
|--------------|------------|-------------------------|
| 0.0          | 900        | 810–990 (13.5–16.5 мин) |
| 0.3          | 684        | 616–752 (10–12.5 мин)   |
| 0.5          | 540        | 486–594 (8–10 мин)      |
| 0.8          | 324        | 292–356 (5–6 мин)       |
| 1.0          | 180        | 162–198 (2.7–3.3 мин)   |

Jitter нужен, чтобы мысли не приходили ровно через N секунд — это было бы слишком механистично.

### Решение: породить мысль или нет?

На каждом тике Trigger Engine вызывает метод `evaluate(state_snapshot)`.

**MVP:** всегда порождает мысль (вероятность = 1.0). Это нужно, чтобы на начальном этапе видеть результат каждого тика.

**Будущее:** добавить «тихие» периоды (аналог сна, концентрации). Вероятность срабатывания:
```
fire_probability = sigmoid(restlessness * 5 - 2)
# restlessness=0.0 → ~12%, restlessness=0.5 → ~73%, restlessness=1.0 → ~95%
```

### Выбор типа события

Стохастический выбор из реестра зарегистрированных типов с весами, модулированными состоянием.

**Реестр типов (MVP):**

| Тип                | base_weight | modulated_by   | modulation_strength |
|--------------------|-------------|----------------|---------------------|
| `new_topic`        | 0.30        | `curiosity`    | 1.0                 |
| `recall_memory`    | 0.30        | `nostalgia`    | 1.0                 |
| `continue_context` | 0.25        | —              | 0.0                 |
| `meta_reflection`  | 0.15        | `restlessness` | 0.5                 |

**Формула итогового веса:**
```
w_i = base_weight_i * (1.0 + modulation_strength_i * state[modulated_by_i])
```
Если `modulated_by` не задан, `w_i = base_weight_i`.

**Нормализация в вероятности:**
```
p_i = w_i / sum(w_j for all j)
```

**Пример расчёта** при `curiosity=0.8, nostalgia=0.1, restlessness=0.5`:
```
w_new_topic   = 0.30 * (1 + 1.0 * 0.8) = 0.30 * 1.8 = 0.540
w_recall      = 0.30 * (1 + 1.0 * 0.1) = 0.30 * 1.1 = 0.330
w_continue    = 0.25 * 1.0              = 0.250
w_meta        = 0.15 * (1 + 0.5 * 0.5) = 0.15 * 1.25 = 0.1875
sum = 1.3075

p_new_topic   = 0.540  / 1.3075 = 41.3%
p_recall      = 0.330  / 1.3075 = 25.2%
p_continue    = 0.250  / 1.3075 = 19.1%
p_meta        = 0.1875 / 1.3075 = 14.3%
```

При высокой curiosity система с наибольшей вероятностью выберет новую тему.

**Выбор:** стандартный weighted random choice (roulette-wheel selection):
```python
import random

def weighted_choice(types: list[TriggerType], state: dict) -> TriggerType:
    weights = [t.compute_weight(state) for t in types]
    return random.choices(types, weights=weights, k=1)[0]
```

### Алгоритм evaluate() (полный псевдокод)

```python
def evaluate(self, state: dict[str, float]) -> SparkEvent | None:
    # 1. Решение: порождать ли мысль? (MVP: всегда да)
    # if random.random() > fire_probability(state):
    #     return None

    # 2. Выбрать тип триггера
    trigger_type = weighted_choice(self.registered_types, state)

    # 3. Получить контекст
    try:
        context = trigger_type.generate_context(self.memory_store)
    except Exception:
        context = []

    # 4. Сформировать событие
    return SparkEvent(
        id=str(uuid4()),
        trigger_type=trigger_type.name,
        state_snapshot=dict(state),
        memory_context=context,
        timestamp=datetime.utcnow(),
        metadata={}
    )
```

## Расширяемость

### Добавление нового типа триггера

Пользователь пишет класс, реализующий интерфейс:

```python
class TriggerType(Protocol):
    name: str
    base_weight: float
    def compute_weight(self, state: State) -> float: ...
    def generate_context(self, memory: MemoryStore) -> str: ...
```

Регистрирует его в конфигурации — и Trigger Engine начинает его использовать. Никакой правки ядра.

### Примеры будущих типов триггеров:
- `rss_reader` — прочитал заголовок новости → думает о ней.
- `time_aware` — утром бодрее, ночью задумчивее.
- `weather_aware` — подключён к API погоды, дождь → меланхолия.
- `social_trigger` — кто-то написал в Telegram → отвлёкся.

## Выход

Trigger Engine не общается с LLM напрямую. Он порождает **событие** (тип + контекст из памяти + текущее состояние) и передаёт его в Intent Generator.
