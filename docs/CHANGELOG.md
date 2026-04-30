# Changelog

Все существенные изменения пакета `iskra` и публичного API описываются здесь. Формат по мотивам [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/); нумерация — [SemVer](https://semver.org/lang/ru/). Версия прод дублируется в [VERSION](../VERSION) (`PRODUCT_VERSION`).

## [Unreleased]

### Исправлено

- **LanceDB:** при старте не падает с `Table 'memories' already exists`, если `list_tables()` возвращает объект ответа (не список имён) — таблица корректно обнаруживается и открывается.

### Добавлено

- **`memory.v2.embeddings_backend`:** `sentence_transformers` (по умолчанию) или **`hash`** — Lance без PyTorch (`hash_embedding_dim`, по умолчанию 384); эталонный `config.yaml` на Windows/Python без рабочего torch — `hash`.
- **Миграция:** `iskra migrate --dummy-embeddings` и `--hash-dim` — перенос без PyTorch (хеш-векторы); при `embeddings_backend: hash` в конфиге миграция тоже использует хеш; при ошибке загрузки `torch` сообщение подсказывает Python 3.12 или флаги/конфиг.

### Документация

- [QUICKSTART.md](QUICKSTART.md) § **4c**: Windows, PyTorch, WinError 1114 / c10.dll (VC++ Redistributable, CPU wheel, Python 3.12, импорт torch до PyQt).

### Изменено

- **Preflight:** повторный вызов `validate_cross_config`; проверка `memory.initial_memories_file` (файл есть и читается); для Lance — проба эмбеддингов, запись в `memory.v2.db_path`, при `graph_enabled` — наличие sidecar-графа и путей JSON; для `general.external_input_file` — каталог и чтение файла, если он уже есть.
- **Preflight (лог):** явные строки про SQLite vs Lance/LanceDB, `v2.db_path`, модель эмбеддингов, граф (пути, веса рёбер), `recall_graph_extra`, **agency**, саморефлексию, консолидацию; рамки `========== Iskra-1 предстарт ==========` в логе.

## [0.4.4] — 2026-04-25

### Добавлено

- **Граф памяти:** взвешенные рёбра в JSON (`[u, v]` или `[u, v, w]`); повторный `link_memories` / тег `links` увеличивает вес; `recall_graph_extra` подмешивает соседей в порядке убывания веса; при `consolidate` / `repoint` веса сливаются (до `memory.v2.graph_max_edge_weight`).
- Конфиг: `memory.v2.graph_link_increment`, `memory.v2.graph_max_edge_weight`.
- Extra **`dev`**: зависимость `networkx` — unit-тесты графа в CI без `iskra[memory]`.

## [0.4.3] — 2026-04-25

### Добавлено

- **Плановая саморефлексия:** `general.self_reflection_every_n_ticks`, `general.self_reflection_recall_n`; после каждых N успешных тиков следующий тик создаётся как `trigger_type: self_reflection` с воспоминаниями из `memory.recall`; обязателен `intent.user_prompts.self_reflection` (`validate_cross_config`).
- CI: workflow **tests** — `pip install -e ".[dev]"`, `pytest tests` (Lance-тесты skip без `lancedb`; тесты графа идут за счёт `networkx` в `dev`).

## [0.4.2] — 2026-04-26

### Добавлено

- **Agency L2–L3:** `agency.l2_importance_floor`; при уровне 2 значение `importance` в `[MEMORY_UPDATE]` не ниже пола; **`[MEMORY_DELETE]`** только при **уровне 3**.
- **Состояние:** `state.variables.*.clamp_min` / `clamp_max` (по умолчанию 0…1); OU и импульсы/feedback клампятся в этот интервал (валентность −1…1 и т.д.).
- **Консолидация памяти:** `general.consolidation_every_n_ticks`; для Lance — `consolidate()` (слияние записей с одинаковым текстом, перенос рёбер графа); SQLite — no-op.
- `MemoryStore.delete_memory`, обновлены протокол и документация ([QUICKSTART](QUICKSTART.md) § 4b, [MEMORY_AND_AGENCY](MEMORY_AND_AGENCY.md)).

## [0.4.1] — 2026-04-26

### Добавлено

- Граф ассоциаций между записями (NetworkX): файл рядом с Lance (`memory.v2.graph_edges_path` или по умолчанию `memory_graph.json`), `MemoryStore.link_memories`, поле `links` в `[MEMORY_UPDATE]`.
- `memory.v2.recall_graph_extra`: до N соседей по графу подмешиваются к результату `recall`.
- Модуль `iskra.memory.memory_graph`, тесты `test_memory_graph`, расширены `test_lance_store`.

## [0.4.0] — 2026-04-26

### Добавлено

- Расширенная память: `memory.backend: lance`, блок `memory.v2`, LanceDB + эмбеддинги (`sentence-transformers`), векторный recall при непустом `context`.
- Секция `agency.level` (0–3); парсинг тегов `[MEMORY_REQUEST]` / `[MEMORY_UPDATE]` / `[MEMORY_SAVE]` в ответе LLM и исполнение в `MainLoop` (текст без тегов уходит в вывод и в обычное сохранение мысли).
- `MemoryStore.update_importance` (SQLite и Lance).
- CLI: `iskra migrate` / `python -m iskra migrate --config …` — перенос SQLite → Lance (исходный файл не удаляется).
- Зависимости: extra `iskra[memory]` (`lancedb`, `networkx`, `sentence-transformers`).

## [0.3.0] — 2026-04-25

### Добавлено

- Публичный API: реэкспорты в `iskra`, список `__all__`, документ [docs/PUBLIC_API.md](PUBLIC_API.md).
- Консольная команда: `iskra` (entry point на `iskra.cli:main` в [pyproject.toml](../pyproject.toml)).
- [docs/CHANGELOG.md](CHANGELOG.md) (этот файл).
- [project.urls] и [keywords] в [pyproject](../pyproject.toml) для публикации на PyPI.
- Предстартовая **самодиагностика** (`general.preflight`, по умолчанию `true`): проверка памяти, путей журнала/файла вывода, доступности LLM (для `mock` — явное сообщение «без сети»; для GigaChat — OAuth; для Ollama — `/api/tags`). CLI выходит с кодом 1 при сбое.
- **Внешний ввод из файла** (`general.external_input_file`): перед тиком (если LLM готов) читается непустой UTF-8; текст в промптах Jinja2 как `external_input`, импульс `user_message` к состоянию; по умолчанию файл **очищается после** успешного ответа и вывода (повтор иначе).

### Изменено

- [**Совместимость:**] `load_config()` больше **не** вызывает `sys.exit`; при ошибке выбрасываются исключения. CLI (`python -m iskra`, `iskra`) обрабатывает их и выходит с кодом 1. Потребителям библиотеки не нужно менять логику, кроме случаев, если они **ожидали** завершения процесса при неверном конфиге.
- `iskra.__main__` делегирует в `iskra.cli`.

### Документация и исправления

- Подстановка `${VAR}` в `config.yaml` только в **значениях** YAML после разбора; плейсхолдеры в **комментариях** не требуют переменных окружения.
- **Фаза 0** памяти/agency: [CONFIG_SCHEMA.md](CONFIG_SCHEMA.md), [TODO_MEMORY_AGENCY.md](TODO_MEMORY_AGENCY.md); комплект документов **1.4.0**; удалены вводящие в заблуждение вспомогательные `docs/` про отдельный downstream-репозиторий; правила — [PUBLIC_API.md](PUBLIC_API.md) § «Внешний репозиторий».

### Для сопровождения

- Чеклист «Iskra1 как библиотека» закрыт; актуальные планы — [TODO_MEMORY_AGENCY.md](TODO_MEMORY_AGENCY.md), раздел «Внешний репозиторий» в [PUBLIC_API.md](PUBLIC_API.md).

## [0.2.0] — ранее

- Исполняемое ядро, `python -m iskra`, тесты, адаптеры LLM, память и т.д. (см. [ROADMAP.md](ROADMAP.md), [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)).

[Unreleased]: https://github.com/PLACEHOLDER/Iskra1/compare/v0.4.2...HEAD
[0.4.2]: https://github.com/PLACEHOLDER/Iskra1/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/PLACEHOLDER/Iskra1/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/PLACEHOLDER/Iskra1/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/PLACEHOLDER/Iskra1/compare/v0.2.0...v0.3.0
