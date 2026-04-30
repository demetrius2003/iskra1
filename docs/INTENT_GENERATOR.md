# Intent Generator (Генератор намерений)

> Авторитетный источник по типам и сигнатурам: [FORMAL_SPECIFICATION.md](FORMAL_SPECIFICATION.md), разделы 3–5.

## Что это

Intent Generator — это мост между внутренним миром Iskra-1 (состояние + триггер + память) и внешним миром (LLM). Он получает **сырое событие** от Trigger Engine и превращает его в **промпт**, который заставляет LLM вести себя так, будто мысль родилась изнутри.

## Аналогия

У улитки между «нейрон выстрелил» и «нога двинулась» есть преобразование сигнала. Intent Generator — это то самое преобразование: из абстрактного внутреннего импульса в конкретное действие.

## Вход

От Trigger Engine приходит событие:

```python
@dataclass(frozen=True)
class SparkEvent:
    id: str                                # UUID v4
    trigger_type: str                      # "new_topic", "recall_memory", ...
    state_snapshot: dict[str, float]       # текущие значения State Engine
    memory_context: list[MemoryRecord]     # извлечённые воспоминания (может быть [])
    timestamp: datetime                    # UTC
    metadata: dict                         # произвольные данные; ядро может записать ``external_input`` (см. ниже)
```

### Внешний ввод из файла (`general.external_input_file`)

Если в конфиге задан путь к файлу и в нём **непустой** UTF-8 текст, `MainLoop` перед триггером кладёт его в `metadata["external_input"]` и вызывает импульс `user_message` (см. [CONFIG_SCHEMA.md](CONFIG_SCHEMA.md) § `general`, [QUICKSTART.md](QUICKSTART.md) §6). **Intent Generator** в шаблоны передаёт это же поле в Jinja как **`external_input`** (строка; пусто, если ввода на этом тике не было). В `config.yaml` обычно используют `{% if external_input %}...{% endif %}` в `system_prompt_template` и в `user_prompts.*`.

### Плановая рефлексия (`self_reflection`)

Если задано `general.self_reflection_every_n_ticks`, ядро **иногда** формирует событие с `trigger_type: "self_reflection"` само (без взвешенного выбора триггера): в `memory_context` попадает до `self_reflection_recall_n` записей из памяти. В Jinja для этого ключа в `user_prompts` список **`memories`** — строки содержимого; **`context`** для этого типа пустой (как у `meta_reflection`).

## Выход

Intent Generator формирует **IntentPayload** — структурированный объект, содержащий пару промптов:

```python
@dataclass(frozen=True)
class IntentPayload:
    event_id: str        # тот же UUID, что у SparkEvent
    system_prompt: str
    user_prompt: str
    trigger_type: str    # для логирования и обратной связи
    timestamp: datetime
```

### 1. System Prompt (задаёт «роль»)

Устанавливает контекст: LLM должна воспринимать входящее сообщение как собственную спонтанную мысль, а не как запрос пользователя. Шаблон использует синтаксис Jinja2.

Шаблон по умолчанию (из `config.yaml`):

```jinja2
Ты — живое существо с внутренним миром. Прямо сейчас у тебя
спонтанно возникла мысль. Это НЕ запрос от человека. Это ТВОЁ
собственное желание. Реагируй естественно: развей мысль, запиши
её, задай себе вопрос, выскажи эмоцию — что угодно.

Твоё текущее состояние:
{% for var_name, var_value in state.items() %}
- {{ var_name }}: {{ "%.2f"|format(var_value) }}
{% endfor %}
```

### 2. User Prompt (сама «мысль»)

Формируется по Jinja2-шаблону, зависящему от типа триггера:

| Тип триггера       | Шаблон промпта                                              |
|--------------------|-------------------------------------------------------------|
| `new_topic`        | `Тебе вдруг стало интересно: {{ context }}`                |
| `recall_memory`    | `Ты вдруг вспомнил: "{{ context }}"`                       |
| `continue_context` | `Ты продолжаешь думать о: {{ context }}`                   |
| `meta_reflection`  | `Ты задумался о том, как устроено твоё собственное мышление`|
| `default`          | `У тебя возникла мысль: {{ context }}`                     |

Переменные в шаблонах (и в **system**, и в **user**):
- `{{ state }}` — dict переменных состояния (в **system** чаще итерируют `state.items()`);
- `{{ context }}` — строка контекста от триггера (тема, воспоминание, прошлый ответ);
- `{{ memories }}` — список извлечённых воспоминаний;
- `{{ external_input }}` — текст из `general.external_input_file` на **этом** тике, либо пустая строка, если ввода не было.

Если шаблон для конкретного `trigger_type` не найден — используется `default`.

## Расширяемость

### Пользовательские шаблоны

Все шаблоны определяются в `config.yaml` (секция `intent`). Пользователь может:
- Переопределить любой шаблон промпта.
- Добавить шаблоны для новых типов триггеров.
- Менять system prompt (например, добавить «личность» или «характер»).

### Цепочки мыслей

В будущем Intent Generator может порождать не один промпт, а **цепочку**: мысль → реакция на мысль → развитие → вывод. Это ближе к внутреннему монологу человека.

## Интерфейс

```python
class IntentGenerator(Protocol):
    def generate(self, event: SparkEvent) -> IntentPayload:
        """Формирует IntentPayload из события."""
        ...
```

Реализация на MVP — `Jinja2IntentGenerator` (использует Jinja2 для рендеринга шаблонов из конфигурации). Подключается как плагин — можно сделать несколько генераторов для разных «характеров» системы.
