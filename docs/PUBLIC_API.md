# Публичный API пакета `iskra`

**Версия документа:** 1.3  
**Продукт (SemVer):** см. `iskra.__version__` и [VERSIONING.md](VERSIONING.md)

**Актуальность:** перечень ниже согласован с `iskra.__init__.py` → **`__all__`** (на момент **0.5.0**). Регрессия: `py -m pytest tests/test_public_api.py` — падает, если в коде добавили/убрали публичный символ, а документ или `__all__` не обновили.

Этот документ описывает **стабильный контракт** для внешних проектов (в том числе **Iskra-2+** в отдельном репозитории), которые ставят `iskra` как зависимость и **не** копируют исходники ядра.

## Правила совместимости

- **MAJOR (X.0.0):** снятие или переименование имён из `iskra.__all__`, несовместимые изменения сигнатур публичных функций/классов, смена обязательных полей [CONFIG_SCHEMA](CONFIG_SCHEMA.md) (см. `CONFIG_SCHEMA_VERSION` в [VERSION](../VERSION)).
- **MINOR (0.X.0):** новые **необязательные** поля в конфиге, новые имена **добавляются** в `__all__` без ломки старых импортов, новые модули.
- **PATCH (0.0.X):** исправления багов без изменения контракта.

Импорты **только** из перечня ниже (или с полным путём к тем же модулям) считаются поддерживаемыми. Всё остальное — **внутренний API** и может меняться в minor.

## Стабильные точки импорта

### Корень пакета

```python
from iskra import (
    __version__,  # строка SemVer
    EmotionClassifier,
    # Конфигурация
    IskraConfig,
    load_config,
    validate_cross_config,
    validate_event_log_line_json,
    # Ядро цикла
    MainLoop,
    EventLog,
    # Модели данных
    EventLogEntry,
    EventLogLineModel,
    IntentPayload,
    LLMResponse,
    MemoryRecord,
    SparkEvent,
    StateSnapshot,
    # Фабрики
    create_llm_adapter,
    create_memory_store,
    create_output_channel,
    create_trigger_types,
    PreflightError,
    preflight,
    # Протоколы и типовые исключения LLM
    LLMAdapter,
    LLMError,
    LLMNetworkError,
    LLMRateLimitError,
    LLMTimeoutError,
    MemoryStore,
    OutputChannel,
    TriggerType,
)
```

Список дублирует `iskra.__all__` в коде (удобно сравнить построчно с [`iskra/__init__.py`](../iskra/__init__.py)).

Явный список имён `__all__` в порядке кода:

`__version__`, `EmotionClassifier`, `EventLog`, `EventLogEntry`, `EventLogLineModel`, `IntentPayload`, `IskraConfig`, `LLMResponse`, `LLMAdapter`, `LLMError`, `LLMNetworkError`, `LLMRateLimitError`, `LLMTimeoutError`, `MainLoop`, `MemoryRecord`, `PreflightError`, `MemoryStore`, `OutputChannel`, `SparkEvent`, `StateSnapshot`, `TriggerType`, `create_llm_adapter`, `create_memory_store`, `create_output_channel`, `create_trigger_types`, `load_config`, `preflight`, `validate_cross_config`, `validate_event_log_line_json`.

### `load_config` и CLI

- **`load_config(path)`** (библиотека) при ошибке **выбрасывает исключения** (`FileNotFoundError`, `yaml.YAMLError`, `pydantic.ValidationError`, `ValueError` и т.д.), а не завершает процесс. Это поведение с **0.3.0**.
- **`python -m iskra`** и команда консоли **`iskra`**: оформляют ошибки, печатают в `stderr` и выходят с кодом 1. См. [cli.py](../iskra/cli.py). Общий флаг **`--dry-run`** — один проход без LLM и без записи в память / `events.jsonl` (промпты в лог **INFO**). Подкоманды **`dashboard`**, **`summary`**, **`webhook`** — см. [QUICKSTART.md](QUICKSTART.md) §3b.

### Конфигурация

- Эталонный полный пример: [`config.yaml`](../config.yaml) в корне репозитория.
- Минимальный пример для тестов/CI: [tests/minimal.yaml](../tests/minimal.yaml).
- Схема полей: [CONFIG_SCHEMA.md](CONFIG_SCHEMA.md), в том числе **`emotion_classifier.lexicon_custom_file`** / **`max_input_chars`**, **`general.external_input_file`** (внешний UTF-8 в тик), **`general.preflight`**. Подкоманды **`dashboard`**, **`summary`**, **`webhook`** и **`--dry-run`**: [QUICKSTART.md](QUICKSTART.md) §3 и §3b; реализация в **`iskra.experience`** (не входит в `__all__`).

## Не считается публичным API

Свободно рефакторится между minor, если не задокументировано иначе:

- внутренние модули: `iskra.core.state_engine`, `iskra.core.trigger_engine`, `iskra.core.intent_generator` (кроме явно экспортируемого `MainLoop` и конфига); **`iskra.experience`** (дашборд / резюме / webhook для подкоманд CLI);
- реализации адаптеров: `iskra.llm.ollama_adapter`, …;
- приватные имена, начинающиеся с `_`;
- структура тестов и примеры в `tests/`;
- **не** импортируйте из `iskra` символы, не входящие в `__all__`, если хотите устойчивость к обновлениям (или зафиксируйте верхнюю границу версии: `iskra>=0.3,<0.4`).

Расширение через **собственные** классы, реализующие протоколы `MemoryStore`, `LLMAdapter`, `OutputChannel`, `TriggerType`, — нормальный путь (см. [ARCHITECTURE.md](ARCHITECTURE.md)).

## Сборка и зависимость в другом репозитории

```bash
pip install "iskra>=0.3.0"
# или с VCS, по тегу:
pip install "iskra @ git+https://github.com/your-org/Iskra1.git@v0.3.0"
```

Имя пакета **`iskra` на PyPI** относится к **другому** проекту (не Iskra-1). Чтобы получить именно этот репозиторий и extras (**`[memory]`**, **`[web]`**), ставьте из **git** или из каталога клона: `pip install ".[web]"` и т.п.; **`pip install iskra[web]` с индекса не ставит Iskra-1 и не подтягивает `duckduckgo-search`**.

В `pyproject.toml` downstream-пакета, например:

```toml
[project]
dependencies = [
  "iskra>=0.3,<1",
]
```

## Внешний репозиторий поверх `iskra` (форк, отдельный пакет)

Основная линия развития (**память + agency**) ведётся **в репозитории Iskra-1** — см. [MEMORY_AND_AGENCY.md](MEMORY_AND_AGENCY.md), [TODO_MEMORY_AGENCY.md](TODO_MEMORY_AGENCY.md). Если вы всё же ведёте **свой** git-проект, который только **подключает** ядро:

- Зависимость: `pip install iskra` или `iskra @ git+…` по тегу; **не** копируйте каталог `iskra/` в свой репо и **не** используйте submodule исходников вместо установки пакета.
- Импорты — **только** из этого документа (`__all__`); внутренние `iskra.core.*` в проде нестабильны между minor.
- Расширяйте через **протоколы** (`MemoryStore`, `LLMAdapter`, `OutputChannel`, `TriggerType`), наследование или композицию **`MainLoop`**; не дублируйте цикл тиков вторым `asyncio`-циклом без дизайна.
- Нужен хук в ядре — **issue/PR** в апстрим Iskra-1, а не «мини-форк» навсегда.
- CI: тесты против **установленного** `iskra`, без `PYTHONPATH` в чужой клон.

## Связь с дорожной картой

- Развитие продукта в одном репо: [ROADMAP.md](ROADMAP.md), [MEMORY_AND_AGENCY.md](MEMORY_AND_AGENCY.md), [TODO_MEMORY_AGENCY.md](TODO_MEMORY_AGENCY.md).
- Changelog: [CHANGELOG.md](CHANGELOG.md).
