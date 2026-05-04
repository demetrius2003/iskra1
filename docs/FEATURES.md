# Что реально умеет Iskra-1 (текущая реализация)

Краткий обзор поведения системы **по коду**, без планов на будущее. Поля конфигурации и краевые случаи — в [CONFIG_SCHEMA.md](CONFIG_SCHEMA.md).

Для **живой демонстрации** одного документа мало: часть функций включается только при нужных ключах в **`config.yaml`** (например **`tools.web_search.enabled`**, уровень **`agency`**). В конце файла — раздел **«Чеклист для демонстрации»** с таблицей «что показать → как».

---

## Главный цикл


- Демон работает **асинхронно**: на каждом **тике** выбирается тип события, собирается промпт, вызывается LLM, результат уходит в память, состояние и каналы вывода.
- Между тиками процесс **спит** случайное время: базовый интервал из **`trigger.interval.min_seconds`** … **`max_seconds`**, сглаженный переменной **`interval.modulated_by`** (например `restlessness`: чем выше модулятор в состоянии, тем **короче** пауза). На результат накладывается **`general.tick_jitter`** (случайный множитель около 1.0).
- При старте проверяется **`general.preflight`**: память, LLM, пути, agency и т.д.; в лог пишется блок с версией **`iskra.__version__`**.

---

## Триггеры (что за «мысль» в этом тике)

На каждом тике движок случайно выбирает **один** зарегистрированный тип триггера с вероятностью пропорциональной **весу**, **если не запланирован принудительный тик саморефлексии** (см. строку **`self_reflection`** в таблице). Вес = **`base_weight`** × (1 + **`modulation_strength`** × значение переменной **`modulated_by`** в состоянии), если модулятор задан.

| Тип (`trigger.types`) | Контекст для промпта |
|------------------------|----------------------|
| **`new_topic`** | Одна случайная строка из **объединённого пула тем** (см. ниже), категория записи `topic_pool`. |
| **`recall_memory`** | До **`memory.recall.default_n`** воспоминаний из памяти (важность, свежесть, стохастический или детерминированный выбор по **`selection`**). **Семантический поиск по вектору** включается только если в **`recall`** передан непустой **`context`** (например из **`[MEMORY_REQUEST]`**); сам триггер **`recall_memory`** вызывает recall без текста контекста. |
| **`continue_context`** | Одна запись категории **`last_context`** (продолжение последней линии рассуждения). |
| **`meta_reflection`** | Пустой контекст — «философия процесса мышления» через промпт **`meta_reflection`**. |
| **`self_reflection`** | Не выбирается из общей лотереи весов: **следующий** тик после каждых **`general.self_reflection_every_n_ticks`** успешных тиков принудительно получает этот тип (отдельный промпт **`self_reflection`**, в контекст подмешиваются воспоминания). |

Обычные типы из **`trigger.types`** регистрируются в `iskra/triggers/`. Тип **`self_reflection`** задаётся циклом **`MainLoop`**, но для него всё равно нужен шаблон **`intent.user_prompts.self_reflection`**.

---
## Пул случайных тем (`new_topic`)

- Источник тем: **`trigger.random_topic_pool`** (список в YAML) **плюс**, если задан **`trigger.random_topic_pool_file`**, все строки из этого файла в **конце** списка (инлайн и файл можно комбинировать; дубликаты не удаляются).
- Файл — YAML: корневой **список строк** или объект с ключом вроде **`topics`**. Путь относительный: сначала текущий каталог процесса, иначе каталог **`config.yaml`**.
- Эталонный большой список в репозитории: **[`data/random_topic_pool.yaml`](../data/random_topic_pool.yaml)**.

---

## Состояние (State Engine)

- Переменные состояния задаются в **`state.variables`**: для каждой — OU-подобный дрейф (**`mu`**, **`theta`**, **`sigma`**) и границы **`clamp_min`** / **`clamp_max`** (для **`valence`** / **`arousal`** обычно диапазон настроения).
- **`state.impulses`** — скачки при событиях (например **`user_message`** при появлении внешнего текста).
- **`state.feedback`** — после ответа LLM для каждого правила: если **`condition`** выполняется, к указанным переменным прибавляются дельты из полей правила (любые числовые поля кроме **`condition`**).
- Поддерживаемые **`condition`** (см. **`evaluate_condition`** в **`state_engine.py`**): **`ends_with_question_mark`**; **`length_lt_N`**, **`length_gt_N`**; **`trigger_type_eq_<имя>`**. Неизвестное условие даёт предупреждение в лог и не срабатывает.

---

## Intent Generator (промпты)

- **`intent.system_prompt_template`** и **`intent.user_prompts`**: шаблоны **Jinja2**.
- В системный шаблон передаются **`state`** (словарь переменных) и **`external_input`**.
- Пользовательский шаблон выбирается по **`event.trigger_type`** (ключ в **`user_prompts`**); если ключа нет — **`default`**.
- В пользовательский шаблон передаются **`context`** (строка из контекста триггера), **`memories`** / **`memory_lines`** (списки; в **`memory_lines`** добавлены подписи valence/arousal записей).

---

## Конфигурация YAML

- **`schema_version`** — версия схемы (см. **`VERSION`** / **`CONFIG_SCHEMA_VERSION`**).
- Подстановка **`${VAR}`** только в **строковых значениях** YAML — подтягивает переменные окружения.

---

## Память

### Режимы бэкенда

- **`memory.backend: sqlite`** — один файл SQLite, без векторов и без графа в ядре (базовый режим).
- **`memory.backend: lance`** — LanceDB (**`memory.v2.enabled: true`**), векторное поле, опционально граф ассоциаций (NetworkX + JSON sidecar). Зависимости: **`pip install ".[memory]"`** из корня репозитория.

### Эмбеддинги (только Lance)

- **`memory.v2.embeddings_backend: sentence_transformers`** — реальные векторы через **`sentence-transformers`** и PyTorch; модель задаётся **`embeddings_model`**.
- **`hash`** — детерминированный вектор без смысла (без PyTorch), для миграций и отладки.

### Recall

- Параметры **`memory.recall`**: число записей (**`default_n`**), веса **`importance_weight`** / **`recency_weight`**, режим **`selection`**: **`stochastic`** (взвешенная случайная выборка) или **`top_n`** (жадный топ по счёту).
- **`emotion_enabled`** и веса **`emotion_valence_alignment_weight`**, **`emotion_nostalgia_positive_weight`**: при подборе воспоминаний к счёту добавляется бонус за согласованность **эмоции записи** с текущими **`valence`** и **`nostalgia`** в состоянии (триггер **`recall_memory`** передаёт **`state`** в **`recall`** даже без текстового **`context`**).
- Семантический отбор по вектору включается только при непустом аргументе **`context`** у **`recall`** (например запрос из **`[MEMORY_REQUEST]`**). Триггер **`recall_memory`** вызывает **`recall(..., context=None)`**.

### Граф ассоциаций (Lance)

- Файл графа по умолчанию лежит рядом с Lance: **`memory_graph.json`** внутри каталога **`memory.v2.db_path`**; иначе задайте **`memory.v2.graph_edges_path`**.
- **`graph_link_increment`** и **`graph_max_edge_weight`**: усиление связи при **`link_memories`** и при поле **`links:`** в **`[MEMORY_UPDATE]`** (до потолка).
- **`recall_graph_extra`**: к результату recall добавляются соседи по графу (приоритет рёбер по убыванию веса).

### Запись после ответа

- Успешный ответ сохраняется с категорией **`trigger_type`** (или **`self_reflection_insight.category`**, если включён инсайт для тика **`self_reflection`**).
- Отдельно обновляется категория **`last_context`** (цепочка для **`continue_context`**).

### Забывание

- **`memory.decay`** — периодически снижается **`importance`** записей (**`base_rate`**, **`min_importance`**, **`recall_protection`**). Вызов привязан к счётчику успешных тиков (**`general.decay_every_n_ticks`**).

### Начальное наполнение

- **`memory.initial_memories_file`** — YAML с начальными воспоминаниями при старте (если файл задан и проходит preflight).

---

## Agency (теги в тексте ответа модели)

Парсер реагирует на строки вида **`[MEMORY_REQUEST]`**, **`[MEMORY_SAVE]`**, **`[MEMORY_UPDATE]`**, **`[MEMORY_DELETE]`** (с полями по схеме в CONFIG_SCHEMA). В **`[MEMORY_UPDATE]`** можно указывать **`links:`** (UUID через запятую) — ядро вызывает **`link_memories`** и усиливает рёбра графа.

Политика задаётся **`agency.level`** (0…3): уровень 0 — только запросы чтения; **`DELETE`** только при уровне ≥ 3; уровень 2 ограничивает снижение **`importance`** при UPDATE через **`l2_importance_floor`**.

Текст ответа для пользователя/вывода может очищаться от строк-тегов (**`strip_tag_lines`**).

---

## Веб-поиск (выход «в интернет»)

- **Не произвольный серфинг**: только если включено **`tools.web_search.enabled`** и установлен пакет **`duckduckgo-search`** (`pip install ".[web]"` из этого репозитория или `duckduckgo-search` в тот же Python).
- Запрос задаётся спецстрокой в тексте:
  - от модели в ответе LLM, или
  - во **внешнем тексте** из **`general.external_input_file`** до основного вызова модели (если там есть `[WEB_SEARCH]`).
- Формат строки: **`[WEB_SEARCH]`** и далее запрос в свободной форме или поля **`query:`** / **`запрос:`** / **`исследование:`** (см. `parse_web_search_queries` в коде).
- Цепочка: **DuckDuckGo** (текстовые сниппеты) → краткая **сводка тем же LLM-адаптером** → сохранение в память с категорией из конфига (по умолчанию **`web_research`**) и лимитами **`max_per_tick`**, **`max_per_hour`**, **`max_results`**.
- В конфиге **`tools.web_search`**: опции подробного лога сниппетов и сводки (**`log_snippet_*`**, **`log_summary_preview_chars`**); текст сводки классифицируется эмоциями так же, как ответ модели.

Трафик к поисковику идёт из процесса Python (не из «магии» модели самой по себе).


---

## Внешний текст: файл ввода (**`incoming.txt`** и любой другой путь)

Имя файла не зашито в коде — задаётся **`general.external_input_file`** (в эталонном **[`config.yaml`](../config.yaml)** часто **`data/incoming.txt`**).

- Перед тиком читается **UTF-8**; непустое содержимое попадает в промпты Jinja как **`external_input`** и в **`event.metadata`**, плюс импульс **`user_message`** в состоянии (**`state.impulses`**).
- **`general.external_input_max_chars`** — обрезка длинного текста.
- **`general.external_input_clear_after_use`**: при **`true`** после **успешного** ответа и вывода файл **очищается** (иначе тот же текст повторится на следующем тике).
- Preflight проверяет, что путь читаем/каталог доступен для создания файла.

Если во внешнем тексте есть **`[WEB_SEARCH]`** и включён **`tools.web_search`**, поиск может выполниться **до** основного вызова LLM на этом тике (отдельная логика в **`MainLoop`**).

### Webhook → тот же файл

- **`py -m iskra webhook`**: HTTP-сервер на **`127.0.0.1`** (порт из **`--port`**), пути **`/`** и **`/hook`**.
- **POST**: тело **`text/plain`** (UTF-8) или **`application/json`** с полем **`text`**, **`content`** или **`message`** — текст **перезаписывает** целевой файл (**`--target`** или **`general.external_input_file`** из конфига).
- **GET** на **`/`** или **`/hook`** — короткая справка в ответе.

---

## Эмоции в тексте и памяти

- **`emotion_classifier`**: лексиконы (базовый и пользовательский YAML), максимальная длина текста для классификации.
- По тексту ответа LLM оцениваются **`emotional_valence`** и **`arousal`** записи; при наличии **`valence`** / **`arousal`** в состоянии они **подмешиваются** к переменным состояния (**`valence_blend`**, **`arousal_blend`**).
- В промпт recall попадают пометки по эмоциям выбранных воспоминаний.

---

## Плановая саморефлексия

- **`general.self_reflection_every_n_ticks`**: когда счётчик успешных тиков кратен N, помечается **следующий** тик как **`self_reflection`** с подстановкой до **`self_reflection_recall_n`** воспоминаний (нужен шаблон **`intent.user_prompts.self_reflection`**).
- **`general.self_reflection_insight`**: опционально ответ этого тика сохраняется в память отдельной категорией (**`self_insight`** по умолчанию), а не только как обычная запись триггера.

---

## Консолидация Lance

- **`general.consolidation_every_n_ticks`**: раз в N успешных тиков вызывается слияние дублей по **одинаковому тексту** и перенос рёбер графа. Для SQLite — пустая операция.

---

## Миграция памяти

- **`py -m iskra migrate --config …`**: перенос записей из SQLite (**`memory.settings.db_path`**) в Lance (**`memory.v2`**). Флаги **`--dummy-embeddings`** / **`--hash-dim`** — если без рабочего PyTorch.

---

## LLM-адаптеры

Реализованы в **`iskra.llm`**: **`mock`**, **`ollama`**, **`gigachat`**, **`yandexgpt`** (имена в **`llm.adapter`** + блок **`llm.settings`**). Общие **`temperature`**, **`max_tokens`**, **`retry`**, **`cooldown_on_rate_limit_seconds`**.

Повторные запросы при сетевых ошибках и rate limit — по конфигу адаптера.

---

## Вывод и журнал

- Каналы вывода в коде: **`console`** и **`file`** (`output.channel`). Настройки — в **`output.settings.<channel>`** (для консоли типичны **`use_rich`**, **`show_state`**, **`show_trigger_type`**, **`show_timestamp`** — см. эталонный **`config.yaml`**).
- Уровень и формат корневого лога: **`logging.level`**, **`logging.format`**.
- **`logging.highlight_primp_logs`**: в TTY подсветка строк логгера **`primp`** (HTTP при веб-поиске).
- Журнал **`logging.event_log`**: append-only **JSONL** (путь из конфига, например **`data/events.jsonl`**). При **`rotate_mb`** файл переименовывается в цепочку **`.1` … `.10`** при превышении размера.

---

## Дополнительные команды CLI

| Команда | Назначение |
|---------|------------|
| **`py -m iskra`** / **`run`** | Основной цикл. **`--dry-run`** — один проход: промпты в лог, без LLM и без записи в память/events. |
| **`migrate`** | SQLite → Lance (см. выше). |
| **`dashboard`** | Статический HTML (Chart.js) по JSONL за окно **`--hours`**; опции **`--events`**, **`-o`**. |
| **`summary`** | Текстовое резюме событий за окно; те же переопределения путей. |
| **`webhook`** | Локальный HTTP-приёмник текста во внешний файл. |

---

## Прочее

- **`general.pid_file`**: при старте основного цикла проверка «уже запущен другой процесс» по PID.
- **`general.decay_every_n_ticks`**: периодический проход decay по памяти (частота не совпадает с интервалом тиков — см. код **`MainLoop`**).
- Базовая **важность** новой записи зависит от типа триггера и эвристик по тексту ответа (**`MainLoop._compute_importance`**).

---

## Чеклист для демонстрации

Используйте как список «что показать живьём»; для каждого пункта должны быть включены соответствующие ключи в **`config.yaml`** и зависимости (**`[memory]`**, **`duckduckgo-search`** и т.д.).

| Что показать | Как воспроизвести кратко |
|--------------|---------------------------|
| Случайный интервал тиков | Понаблюдать паузы между записями в логе; изменить **`min_seconds` / `max_seconds`**, **`modulated_by`**, **`tick_jitter`**. |
| Случайный тип мысли | Лог **`trigger_type`** в консоли (**`show_trigger_type`**) или поля в **`events.jsonl`**. |
| Пул тем **`new_topic`** | Файл **`trigger.random_topic_pool_file`** (напр. **`data/random_topic_pool.yaml`**) + при желании инлайн **`random_topic_pool`**. |
| Внешний текст (**`incoming.txt`**) | Записать UTF-8 в **`general.external_input_file`** (часто **`data/incoming.txt`**); увидеть блок **`external_input`** в промпте / реакцию **`user_message`** в состоянии. |
| Webhook | **`py -m iskra webhook --config …`**, затем **POST** на **`http://127.0.0.1:<port>/`** — текст попадает в тот же файл ввода. |
| Lance + эмбеддинги | **`memory.backend: lance`**, **`sentence_transformers`** или **`hash`**; preflight пишет про БД и эмбеддинги. |
| Семантический recall | Модель с **`[MEMORY_REQUEST]`** и запросом **`query:`** (нужен Lance и вектора). |
| Граф | **`memory.v2.graph_enabled`**, рёбра через **`[MEMORY_UPDATE]` `links:`** или sidecar JSON; **`recall_graph_extra`**. |
| Agency | Ответ модели со строками **`[MEMORY_SAVE]`** / **`UPDATE`** / **`DELETE`** при разных **`agency.level`**. |
| **`[WEB_SEARCH]`** | Включить **`tools.web_search.enabled`**, установить **`duckduckgo-search`**; строка в ответе модели или во входном файле. |
| Саморефлексия | **`self_reflection_every_n_ticks`** > 0; дождаться тика **`self_reflection`**; опционально **`self_reflection_insight`**. |
| Консолидация | **`consolidation_every_n_ticks`** на Lance; следить за логом **`consolidate`**. |
| Эмоции и состояние | Лексиконы **`emotion_classifier`**; переменные **`valence` / `arousal`** в **`state`**; колонки в памяти. |
| Обратная связь **`feedback`** | Ответ с **`?`**, короткий/длинный текст — срабатывание условий **`state.feedback`**. |
| Preflight + версия | Строка **`Iskra-1 предстарт (v…)`** в логе при **`preflight: true`**. |
| **`--dry-run`** | Один проход промптов в лог без LLM и без изменения памяти/events. |
| **`migrate`** | **`py -m iskra migrate`** с реальной SQLite и целевым Lance (демо на копии данных). |
| Дашборд / резюме | **`py -m iskra dashboard`** и **`summary`** после накопления **`events.jsonl`**. |

Подробные контракты и примеры YAML — **[CONFIG_SCHEMA.md](CONFIG_SCHEMA.md)**, **[QUICKSTART.md](QUICKSTART.md)**, **[MEMORY_AND_AGENCY.md](MEMORY_AND_AGENCY.md)**.
