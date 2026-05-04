# Config Schema (Схема конфигурации)

**Версия документа:** 1.7.0  
**Дата:** 28 апреля 2026  
**Комплект документации:** 1.7.0 (файл `VERSION` в корне репозитория)  
**Поле `schema_version` в YAML:** `1` (см. также `CONFIG_SCHEMA_VERSION` в `VERSION`). С **0.6.0** добавлены **`tools.web_search`** (тег **`[WEB_SEARCH]`**, DuckDuckGo + сводка LLM; зависимость **`duckduckgo-search`**, см. § tools — не путать с одноимённым пакетом **`iskra`** на PyPI). С **0.5.0** добавлены **`emotion_classifier`**, эмоциональные поля памяти и состояния (`valence`, `arousal`). Ранее: секции **`memory.v2`**, **`agency`**, **`intent.user_prompts.self_reflection`**, адаптеры **`gigachat`** / **`yandexgpt`** (с **0.4.x**). При расширении схемы возможен рост `schema_version` (см. [VERSIONING.md](VERSIONING.md)).

Начальные воспоминания (`memory.initial_memories_file`): повторное применение одного и того же файла подавляется маркером `data/.iskra_seed_marker.json` (хеш содержимого и абсолютный путь к YAML).

## Назначение

Вся настройка Iskra-1 определяется одним файлом `config.yaml`. Это означает:
- Никаких хардкод-значений в коде.
- Полный контроль над поведением без перекомпиляции.
- Разные «личности» — разные конфиг-файлы.

С **0.5.0** добавлены эмоции и углублённая рефлексия: переменные состояния **`valence`** / **`arousal`**, поля памяти **`emotional_valence`** / **`arousal`**, секция **`emotion_classifier`** (лексикон для классификации текста ответа LLM), в **`memory.recall`** — веса эмоционального recall; **`general.self_reflection_insight`** — сохранение инсайта плановой рефлексии. Подробнее: [STATE_ENGINE.md](STATE_ENGINE.md), [MEMORY_SYSTEM.md](MEMORY_SYSTEM.md).

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
  backend: "sqlite"              # "sqlite" | "lance"
  settings: { ... }
  decay: { ... }
  recall: { ... }
  v2: { ... }                   # расширенный режим (Lance + эмбеддинги) — см. § ниже

# ─── Agency (уровень прав модели на память) ─────────────────
agency:
  level: 1                       # 0 read | 1 suggest | 2 co-manage | 3 full

# ─── Intent Generator ──────────────────────────────────────
intent:
  system_prompt_template: "..."
  user_prompts: { ... }        # включая optional self_reflection при general.self_reflection_every_n_ticks

# ─── LLM Adapter ───────────────────────────────────────────
llm:
  adapter: "ollama"
  settings: { ... }

# ─── Инструменты (опционально) ─────────────────────────────
tools:
  web_search:
    enabled: false
    max_results: 5
    summary_max_tokens: 300
    max_per_tick: 1
    max_per_hour: 5
    memory_importance: 0.8
    memory_category: web_research
    log_snippet_count: true
    log_snippet_previews: false
    log_snippet_preview_chars: 240
    # log_summary_preview_chars: 320

# ─── Output Channel ────────────────────────────────────────
output:
  channel: "console"
  settings: { ... }

# ─── Logging & Metrics ─────────────────────────────────────
logging:
  level: "INFO"
  highlight_primp_logs: true
  event_log:
    enabled: true
    path: "data/events.jsonl"

# ─── General ────────────────────────────────────────────────
general:
  decay_every_n_ticks: 10
  consolidation_every_n_ticks: null
  self_reflection_every_n_ticks: null
  self_reflection_recall_n: 5
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
- По умолчанию значения клампятся в **[0.0, 1.0]** (`clamp_min` / `clamp_max` можно задать явно).
- `initial` и `mu` должны лежать внутри `[clamp_min, clamp_max]` (например валентность **[-1, 1]** для линии «память + agency»).
- `theta` > 0 (рекомендуется 0.01–0.20)
- `sigma` > 0 (рекомендуется 0.01–0.20)
- Хотя бы одна переменная обязательна

Пример **bipolar** переменной:

```yaml
state:
  variables:
    emotional_valence:
      clamp_min: -1.0
      clamp_max: 1.0
      initial: 0.0
      mu: 0.0
      theta: 0.05
      sigma: 0.06
```

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

- **`trigger.random_topic_pool`** — список строк (можно оставить пустым, если темы только из файла).
- **`trigger.random_topic_pool_file`** — опционально, путь к YAML с темами. После загрузки конфигурации строки из файла **добавляются в конец** после элементов `random_topic_pool` (инлайн и файл можно комбинировать).
- Относительный путь разрешается сначала от **текущего рабочего каталога**, если файл там найден; иначе — от **каталога**, в котором лежит загружаемый `config.yaml`.

Форматы файла тем:

```yaml
topics:
  - "квантовая запутанность"
  - "история письменности"
```

или корневой YAML-массив:

```yaml
- "тема один"
- "тема два"
```

Эталонный репозиторий держит большой список в [`data/random_topic_pool.yaml`](../data/random_topic_pool.yaml), а в [`config.yaml`](../config.yaml) задаёт только `random_topic_pool_file`.

Пример только инлайна (как раньше):

```yaml
trigger:
  random_topic_pool:
    - "квантовая запутанность"
    - "история письменности"
```

---

### emotion_classifier

Лексикон для оценки эмоций текста ответа LLM (см. [`emotion_lexicon.yaml`](../emotion_lexicon.yaml)).

```yaml
emotion_classifier:
  lexicon_file: "emotion_lexicon.yaml"
  lexicon_custom_file: null    # дополнительный YAML (те же ключи); множества объединяются с основным файлом
  max_input_chars: null       # или целое 64…500000 — только первые N символов ответа попадают в классификатор
  valence_blend: 0.12
  arousal_blend: 0.14
```

---

### memory

```yaml
memory:
  backend: "sqlite"            # "sqlite" | "lance" (lance — расширенный store; см. § «Расширенная память и agency»)
  settings:
    # Для sqlite:
    db_path: "data/memory.db"

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

**Инвариант конфигурации (MVP расширенного режима):** поддерживаемые сочетания: `backend: sqlite` с `memory.v2.enabled: false` (поведение как в 0.3.x) и `backend: lance` с `memory.v2.enabled: true`. Иные комбинации при реализации дают ошибку валидации, пока не оговорены отдельно.

---

### Расширенная память и agency (утверждено; код — 0.4+)

Дополнительные ключи под [MEMORY_AND_AGENCY.md](MEMORY_AND_AGENCY.md). Установка зависимостей: `pip install iskra[memory]` (LanceDB, NetworkX, sentence-transformers).

```yaml
memory:
  backend: "sqlite"                    # переключение на "lance" при включённом v2 — см. инвариант выше
  # ... settings, recall, decay, initial_memories_file — как раньше ...

  v2:
    enabled: false
    db_path: "data/memory_v2"        # каталог/путь хранилища Lance (точная семантика — в реализации)
    embeddings_model: "sentence-transformers/all-MiniLM-L6-v2"
    graph_enabled: true               # граф ассоциаций (NetworkX), JSON рядом с Lance
    graph_edges_path: null          # по умолчанию: <db_path>/memory_graph.json
    recall_graph_extra: 0           # добавить до N соседей по графу к recall (0 = выкл.)
    graph_link_increment: 1.0      # вклад в вес ребра при каждом link / теге links
    graph_max_edge_weight: 1000.0   # потолок веса; при consolidate рёбра суммируются (см. repoint)
    embeddings_backend: sentence_transformers  # или hash — без PyTorch (см. QUICKSTART)
    hash_embedding_dim: 384        # только для embeddings_backend: hash

agency:
  level: 1                           # 0 = read-only | 1 = suggest | 2 = co-manage | 3 = full
  l2_importance_floor: 0.12          # при level=2: MEMORY_UPDATE importance не ниже этого (L1 и L3 без пола)
```

Смысл уровней — в [MEMORY_AND_AGENCY.md](MEMORY_AND_AGENCY.md) §5. **Исполнение в коде:** при **L0** из тегов выполняется только эффект `[MEMORY_REQUEST]` (recall в лог); при **L1** `[MEMORY_SAVE]` и `[MEMORY_UPDATE]` **не** изменяют хранилище — в лог пишется строка «предложение»; запись и обновление (включая `links`) — с **L2**; `[MEMORY_DELETE]` — только при **L3**.

#### Протокол тегов в тексте ответа модели

Тег занимает **одну строку** (или сегмент до перевода строки): префикс в квадратных скобках, затем поля в виде `ключ: значение`, разделённые запятой и пробелом `", "`. Значения:

- Строки — в **двойных кавычках**; внутри строки кавычка как `\"`.
- Числа — без кавычек (`importance: 0.9`).
- UUID записи (`id`) — без кавычек в каноническом виде `8-4-4-4-12` **или** в двойных кавычках.

Парсер обязан разбирать поля с учётом кавычек (запятые внутри строки не разделяют поля).

| Тег | Назначение | Формат (после префикса) | Пример |
|-----|------------|-------------------------|--------|
| `[MEMORY_REQUEST]` | Семантический/ключевой запрос к store | `query: "<строка>"` | `[MEMORY_REQUEST] query: "root_console"` |
| `[MEMORY_UPDATE]` | Изменить запись и/или рёбра графа | поля через `", "`; минимум `id`; опционально `importance` и/или `links` (UUID через запятую) | `[MEMORY_UPDATE] id: …, links: 6ba7b810-9dad-11d1-80b4-00c04fd430c8` |
| `[MEMORY_SAVE]` | Новая запись | минимум `content`; опционально `importance` и др. | `[MEMORY_SAVE] content: "текст", importance: 0.8` |
| `[MEMORY_DELETE]` | Удалить запись | только при **agency.level ≥ 3**; `id:` UUID | `[MEMORY_DELETE] id: 550e8400-e29b-41d4-a716-446655440000` |

Для **Lance**: раз в `general.consolidation_every_n_ticks` успешных тиков вызывается `consolidate()` — слияние дублей с одинаковым текстом (оставляется запись с максимальным `importance`). SQLite: no-op.

Спонтанный текст без тегов — как в текущем Iskra-1. Дополнительные ключи в тегах могут добавляться в следующих версиях схемы; неизвестные ключи при строгой валидации — предупреждение или ошибка (решение при реализации).

#### Миграция SQLite → Lance

Однократная команда:

```bash
python -m iskra migrate --config config.yaml
```

Флаги: `--dummy-embeddings` — без `sentence-transformers`/PyTorch, псевдо-векторы из хеша (для сломанного `torch` на Windows или Python без поддерживаемых колёс); `--hash-dim N` — размерность (8…4096, по умолчанию 384).

Копирует записи из `memory.settings.db_path`, пишет Lance в `memory.v2.db_path`, считает эмбеддинги (или хеш-векторы), **не удаляет** исходный SQLite.

---

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
    self_reflection: >
      Плановая пауза: оглянись на недавние воспоминания.
      {% for m in memories %}- {{ m }}
      {% endfor %}
    default: >
      У тебя возникла мысль: {{ context }}

  max_response_tokens: 500     # передаётся в LLM Adapter
```

Шаблоны используют синтаксис Jinja2. Переменные:
- `{{ state }}` — dict переменных состояния
- `{{ context }}` — строка контекста от триггера
- `{{ memories }}` — список **строк** содержимого воспоминаний, подмешанных в событие (в т.ч. для `trigger_type: self_reflection`)
- `{{ external_input }}` — внешний ввод с тика (строка; см. § `general`)

Если задано `general.self_reflection_every_n_ticks`, после каждых N **успешных** тиков **следующий** тик создаётся ядром как `SparkEvent` с `trigger_type: self_reflection` (без выбора триггера по весам); в `memory_context` попадает до `self_reflection_recall_n` записей из `memory.recall`. Обязателен ключ **`intent.user_prompts.self_reflection`** (проверка `validate_cross_config`).

---

### llm

```yaml
llm:
  adapter: "ollama"               # реализовано: "mock" | "ollama" | "gigachat" | "yandexgpt" | "yandex_gpt"; в планах/пример YAML: openai | grok | anthropic
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

### tools

Опциональные действия во «внешнем мире». Веб-поиск (с **0.6.0**): строки **`[WEB_SEARCH]`** во входящем файле `general.external_input_file` или в сыром ответе модели → DuckDuckGo (пакет **`duckduckgo-search`**) → краткая сводка тем же LLM-адаптером → запись в память с категорией по умолчанию **`web_research`**.

Установка: **`pip install duckduckgo-search`** или из корня репозитория Iskra-1 **`pip install ".[web]"`** (на PyPI пакет **`iskra`** — другой проект, **`pip install iskra[web]`** не подтягивает этот код и это extra). В конфиге по умолчанию **`enabled: false`**.

Лимиты **`max_per_tick`** и скользящий час **`max_per_hour`** задаются в конфиге; при **`max_per_hour: 0`** почасовой потолок отключён.

Форматы строк (каждая с новой строки):

- `[WEB_SEARCH] парадоксы бесконечности Кантор`
- `[WEB_SEARCH] query: "теорема Гёделя"`
- `[WEB_SEARCH] запрос: "теорема Гёделя"`
- `[WEB_SEARCH] исследование: "…"` — синоним поля запроса

Строки с тегом вырезаются из текста мысли перед выводом и перед подстановкой **`external_input`** в промпты (чтобы не дублировать триггер).

**Логирование:** при **`log_snippet_count: true`** (по умолчанию) в лог INFO попадает строка вида «запрос … сниппетов от поиска=N» — если **N > 0**, поиск реально вернул текстовые фрагменты до сводки LLM. **`log_snippet_previews: true`** (по умолчанию с **0.6.x**) добавляет превью первых **`log_snippet_preview_limit`** сниппетов (сырой текст из выдачи). **`log_summary_preview_chars`** (`null` — выключить) — начало сводки после LLM.

Цвет **`primp`** в консоли: **`logging.highlight_primp_logs: true`** (голубые строки HTTP-поиска Bing и т.д.). Отключить все ANSI в логе: переменная окружения **`ISKRA_NO_LOG_COLORS=1`**.

Если во входящем файле **только** строки `[WEB_SEARCH]` (нет другого текста после вырезания тегов), тик выполняет только поиск и сводку, без основного вызова «мысли».

```yaml
tools:
  web_search:
    enabled: false
    max_results: 5
    summary_max_tokens: 300      # ориентир в промпте сводки (адаптер может игнорировать отдельный потолок)
    max_per_tick: 1
    max_per_hour: 5              # 0 — без почасового лимита
    memory_importance: 0.8
    memory_category: web_research
    log_snippet_count: true
    log_snippet_previews: true
    log_snippet_preview_limit: 5
    log_snippet_preview_chars: 280
    log_summary_preview_chars: 320   # или null — без превью сводки
```

---

### output

```yaml
output:
  channel: "console"              # "console" | "file" | "telegram" | "multi"
  settings:
    console:
      use_rich: true              # Rich: цветные рамки (голубой), тип триггера (пурпур), строка состояния (имена cyan / значения зелёные), текст мысли (жёлтый), URL (ярко-голубой подчёркнутый)
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
  highlight_primp_logs: true      # голубая подсветка строк логгера primp в TTY; выкл.: false или ISKRA_NO_LOG_COLORS=1
  event_log:
    enabled: true
    path: "data/events.jsonl"     # полный лог всех событий
    rotate_mb: 100                # ротация при достижении 100 МБ
```

---

### general

| Поле | Тип | Описание |
|------|-----|----------|
| `preflight` | `bool`, по умолчанию `true` | Предстарт: кросс-валидация конфига, память (SQLite vs **Lance/LanceDB**: эмбеддинги, `v2.db_path`, граф, `recall_graph_extra`), **agency**, **саморефлексия**, **консолидация** (с подсказкой при SQLite), `initial_memories_file`, `external_input_file`, журнал, вывод, LLM. В лог пишется блок `preflight | ========== Iskra-1 предстарт ==========`. |
| `external_input_file` | `str \| null` | Путь к **UTF-8** файлу с внешним текстом. Если **не** `null` и в файле после `strip()` есть содержимое, на **каждом** тике (после проверки кулдауна и доступности LLM) оно: подмешивается в промпты Jinja2 как `external_input`, вызывается импульс `user_message` к состоянию, копируется в `SparkEvent.metadata["external_input"]`. Подходит для сигнала с Telegram, скрипта, ручного редактора. **Нет** файла или **пусто** — ветка не срабатывает. |
| `external_input_max_chars` | `int` | Максимальная длина текста (по умолчанию 8000); лишнее обрезается. |
| `external_input_clear_after_use` | `bool`, по умолчанию `true` | После **успешного** ответа LLM и `output.emit` — записать в файл пустую строку. Если `false` — файл **не** очищается (риск повторов на следующих тиках). При ошибке LLM/вывода — очистка **не** выполняется, текст остаётся для повторной попытки. |
| `decay_every_n_ticks` | `int ≥ 1` | Каждые N успешных тиков — `memory.decay()`. |
| `consolidation_every_n_ticks` | `int ≥ 1` или `null` | Раз в N успешных тиков — `memory_store.consolidate()` (Lance: дубли по тексту). `null` — выкл. |
| `self_reflection_every_n_ticks` | `int ≥ 1` или `null` | После каждых N успешных тиков **следующий** тик — плановая рефлексия (`self_reflection`). Требует `intent.user_prompts.self_reflection`. `null` — выкл. |
| `self_reflection_recall_n` | `int`, 1…32 | Сколько воспоминаний подмешать в событие плановой рефлексии. |
| `tick_jitter` | `0.0…1.0` | Случайный множитель к интервалу триггера. |
| `data_dir` | `str` | Каталог данных. |
| `pid_file` | `str` | Путь к pid-файлу (двойной запуск). |

```yaml
general:
  preflight: true
  external_input_file: null        # напр. "data/incoming.txt" — непустой UTF-8 подмешивается в тик
  external_input_max_chars: 8000
  external_input_clear_after_use: true
  decay_every_n_ticks: 10
  consolidation_every_n_ticks: null   # напр. 200 — консолидация Lance-памяти
  self_reflection_every_n_ticks: null # напр. 50 — плановая рефлексия
  self_reflection_recall_n: 5
  tick_jitter: 0.1
  data_dir: "data"
  pid_file: "data/iskra.pid"
```

В шаблонах `intent` доступна переменная Jinja2 **`{{ external_input }}`** (строка; пустая, если ввода не было). Полный пример с `{% if external_input %}` — в эталонном [`config.yaml`](../config.yaml) в корне репозитория.

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

  random_topic_pool_file: "data/random_topic_pool.yaml"
  random_topic_pool: []

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
    self_reflection: "Пауза для саморефлексии. {% for m in memories %}- {{ m }}\n{% endfor %}"
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
  preflight: true
  external_input_file: null
  external_input_max_chars: 8000
  external_input_clear_after_use: true
  decay_every_n_ticks: 10
  consolidation_every_n_ticks: null
  self_reflection_every_n_ticks: null
  self_reflection_recall_n: 5
  tick_jitter: 0.1
  data_dir: "data"
  pid_file: "data/iskra.pid"
```

*Примечание.* Раздел `intent` в фрагменте выше упрощён; в корневом `config.yaml` могут быть блоки `{% if external_input %}` в шаблонах — см. актуальный файл.

---

## Pydantic-модель валидации (для реализации)

```python
from pydantic import BaseModel, Field, field_validator, model_validator

class StateVariableConfig(BaseModel):
    clamp_min: float = 0.0
    clamp_max: float = 1.0
    initial: float
    mu: float
    theta: float = Field(gt=0.0)
    sigma: float = Field(gt=0.0)

    @model_validator(mode="after")
    def _bounds(self):
        if self.clamp_max <= self.clamp_min:
            raise ValueError("clamp_max must be > clamp_min")
        for label, val in ("initial", self.initial), ("mu", self.mu):
            if not (self.clamp_min <= val <= self.clamp_max):
                raise ValueError(f"{label} out of clamp range")
        return self

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
    random_topic_pool_file: str | None = None  # YAML со списком или ключом topics

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
    consolidation_every_n_ticks: int | None = Field(default=None, ge=1)
    self_reflection_every_n_ticks: int | None = Field(default=None, ge=1)
    self_reflection_recall_n: int = Field(default=5, ge=1, le=32)
    tick_jitter: float = Field(ge=0.0, le=1.0, default=0.1)
    data_dir: str = "data"
    pid_file: str = "data/iskra.pid"
    preflight: bool = True
    external_input_file: str | None = None
    external_input_max_chars: int = Field(8000, ge=1, le=500_000)
    external_input_clear_after_use: bool = True

class AgencyConfig(BaseModel):
    level: int = Field(default=1, ge=0, le=3)
    l2_importance_floor: float = Field(default=0.12, ge=0.0, le=1.0)

class IskraConfig(BaseModel):
    schema_version: int = 1
    state: StateConfig
    trigger: TriggerConfig
    memory: MemoryConfig = MemoryConfig()
    agency: AgencyConfig = AgencyConfig()
    intent: IntentConfig
    llm: LLMConfig = LLMConfig()
    output: OutputConfig = OutputConfig()
    logging: LoggingConfig = LoggingConfig()
    general: GeneralConfig = GeneralConfig()
```

---

## Загрузка конфигурации (псевдокод)

Реализация: `load_config()` в `iskra/core/config.py`. Сначала `yaml.safe_load`, затем **рекурсивная** подстановка `${VAR_NAME}` **только в строковых значениях** (комментарии в YAML в структуру не попадают — плейсхолдеры в `# ...` не ломают запуск). После Pydantic-валидации — при наличии **`trigger.random_topic_pool_file`** читается YAML и строки из файла **дописываются** к `trigger.random_topic_pool`; затем **`validate_cross_config()`** (в т.ч. импульсы состояния, обратная связь, наличие `valence`/`arousal` при `memory.recall.emotion_enabled`, непустой пул для `new_topic`). **Библиотечный** `load_config` с **0.3.0** при ошибке **выбрасывает исключения** (`FileNotFoundError`, `yaml.YAMLError`, `ValidationError`, `ValueError` и т.д.). CLI (`iskra` / `python -m iskra`) ловит их и печатает в `stderr` (см. [PUBLIC_API.md](PUBLIC_API.md)).

```python
import re
import yaml
from pathlib import Path

def load_config(path: str = "config.yaml") -> IskraConfig:
    raw = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    data = deep_substitute_env_in_strings(data)  # ${VAR} только в значениях
    cfg = IskraConfig.model_validate(data)
    cfg = merge_random_topic_pool_from_file(cfg, Path(path))
    validate_cross_config(cfg)
    return cfg
```

---

## Запуск

```bash
# С конфигом по умолчанию (config.yaml в текущей директории)
python -m iskra

# С указанием конфига
python -m iskra --config path/to/my_config.yaml

# Отчёты по журналу (см. QUICKSTART §3b)
python -m iskra dashboard --config config.yaml
python -m iskra summary --config config.yaml
python -m iskra webhook --config config.yaml --port 8765

# С переменными окружения для API-ключей
ISKRA_OPENAI_KEY=sk-... python -m iskra --config production.yaml
```
