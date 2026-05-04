# Обновление с 0.4.x до 0.5.x

Краткий чеклист для существующих установок и кастомных `config.yaml`.

## Состояние (state)

Добавьте OU-переменные **`valence`** (диапазон −1…1 через `clamp_min` / `clamp_max`) и **`arousal`** (0…1), если их ещё нет. Они используются для эмоциональной окраски после ответа LLM и для модификаторов **`memory.recall`** при **`emotion_enabled: true`** (по умолчанию включено).

Если вы сознательно не хотите эмоций в recall, задайте:

```yaml
memory:
  recall:
    emotion_enabled: false
```

Расширьте блок **`state.feedback`** под те же переменные, если нужны импульсы от длины ответа и триггеров (см. эталонный [`config.yaml`](../config.yaml)).

## Память

- SQLite / Lance: новые колонки **`emotional_valence`**, **`arousal`** подставляются при создании таблицы или миграцией (`py -m iskra migrate` при переходе на Lance).
- Если каталог Lance создан до 0.5.0 и схема конфликтует — удалите каталог **`memory.v2.db_path`** или выполните миграцию заново из SQLite.

## Триггер new_topic и пул тем

С длинными списками тем используйте внешний файл:

```yaml
trigger:
  random_topic_pool_file: "data/random_topic_pool.yaml"
  random_topic_pool: []
```

Темы из файла добавляются **после** инлайн-списка. Подробности — [CONFIG_SCHEMA.md](CONFIG_SCHEMA.md).

## Классификатор эмоций

- **`emotion_classifier.lexicon_custom_file`** — свой YAML с теми же ключами, что основной [`emotion_lexicon.yaml`](../emotion_lexicon.yaml); слова **добавляются** к базовому лексикону (объединение множеств).
- **`emotion_classifier.max_input_chars`** — при необходимости ограничить длину текста ответа LLM перед классификацией.

## Отладка без LLM и без памяти

```bash
py -m iskra --dry-run --config config.yaml
```

Один проход: выбранный триггер и промпты пишутся в лог уровня **INFO**; сеть и запись в хранилище не выполняются.

## Прочее

- **`intent.user_prompts.self_reflection`** — нужен, если включён `general.self_reflection_every_n_ticks`.
- **`general.self_reflection_insight`** — опционально сохраняет формулировку наблюдения в память при плановой рефлексии.

Полная история изменений — [CHANGELOG.md](CHANGELOG.md).
