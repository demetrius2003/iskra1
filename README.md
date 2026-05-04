# Iskra-1

**Фреймворк для выращивания искусственной интенции в языковых моделях.**

*English:* **Iskra-1** is a Python, design-first framework for an **autonomous inner loop** around large language models: **state engine** (Ornstein–Uhlenbeck drift), **stochastic triggers**, **episodic memory** (SQLite или LanceDB + эмбеддинги и граф), **intent / prompt generation**, **эмоциональная окраска** текста и состояния, **agency** (теги памяти в ответе модели), опционально **веб-поиск** (DuckDuckGo → сводка в память), и **сменные LLM-адаптеры**: Mock, Ollama, GigaChat, YandexGPT. Это не чат-бот и не очередной agent framework — **непрерывная искра** внутренних мыслей между сообщениями пользователя.

## Проблема

Большинство LLM живут по схеме **запрос → ответ → тишина**. Между запросами «личности» нет: нет стабильного внутреннего состояния, монолога и памяти как у существа с интервалами самопроизвольной активности.

## Решение

Iskra-1 — внешний цикл вокруг выбранной модели: тики по случайному интервалу, состояние + память → промпт → ответ → обновление памяти и переменных (**curiosity**, **restlessness**, **nostalgia**, **valence**, **arousal** и др. по конфигу). Внешний текст можно подать файлом или webhook’ом; модель может запрашивать recall и правки памяти тегами **`[MEMORY_*]`**, при включённом **`tools.web_search`** — запускать поиск строкой **`[WEB_SEARCH]`**.

## Как это работает

```
State Engine (OU-дрейф по переменным состояния)
      │
      ▼
Trigger Engine (случайный интервал, веса триггеров, пул тем / контекст памяти)
      │
      ▼
Intent Generator (Jinja2: состояние + память + опционально external_input)
      │
      ▼
LLM Adapter (mock | ollama | gigachat | yandexgpt | …)
      │
      ├──▶ опционально: tools.web_search ([WEB_SEARCH] → память web_research)
      │
      ▼
Output Channel (консоль / файл)
      │
      └──▶ Memory Store → снова State Engine (обратная связь по тексту мысли)
```

## Что умеет система сейчас

Полный список реализованных возможностей и поведения цикла — **[docs/FEATURES.md](docs/FEATURES.md)** (тики, триггеры, пул тем из YAML, память Lance/SQLite, теги **`[MEMORY_*]`**, веб-поиск **`[WEB_SEARCH]`**, CLI и т.д.).

## Ключевые принципы

- **Минимальное ядро** — базовый режим с SQLite и mock-LLM без тяжёлых зависимостей.
- **Расширяемая память** — LanceDB, векторный recall, граф ассоциаций (`pip install ".[memory]"`, см. [MEMORY_AND_AGENCY.md](docs/MEMORY_AND_AGENCY.md)).
- **Эмоции** — поля памяти и состояние **valence / arousal**, лексикон в **`emotion_classifier`**, учёт в recall ([CONFIG_SCHEMA.md](docs/CONFIG_SCHEMA.md)).
- **Agency** — уровни правок памяти по тегам **`[MEMORY_REQUEST]`**, **`[MEMORY_SAVE]`**, **`[MEMORY_UPDATE]`**, **`[MEMORY_DELETE]`** ([MEMORY_AND_AGENCY.md](docs/MEMORY_AND_AGENCY.md)).
- **Опциональный веб-поиск** — **`tools.web_search`**, зависимость **`duckduckgo-search`** ([CONFIG_SCHEMA.md](docs/CONFIG_SCHEMA.md) § `tools`).
- **Вся логика в `config.yaml`** — один файл, валидация Pydantic; см. [CONFIG_SCHEMA.md](docs/CONFIG_SCHEMA.md).

## Быстрый старт и CLI

Рабочая директория — **корень репозитория** (рядом с `config.yaml`, `data/`).

```bash
# установка в режиме разработки
py -m pip install -e .

# основной цикл (конфиг по умолчанию ./config.yaml)
py -m iskra
py -m iskra --config config.yaml

# один проход: только промпты в лог (INFO), без LLM и без записи в память / events.jsonl
py -m iskra --dry-run --config tests/minimal.yaml

# SQLite → Lance (см. документацию по migrate)
py -m iskra migrate --config config.yaml
py -m iskra migrate --config config.yaml --dummy-embeddings

# статический HTML-дашборд по журналу событий → data/dashboard.html (или general.data_dir)
py -m iskra dashboard --config config.yaml

# текстовое резюме за окно времени → daily_summary.txt
py -m iskra summary --config config.yaml --hours 24

# localhost webhook → файл external_input (как прокси к следующему тику)
py -m iskra webhook --config config.yaml --port 8765
```

Остановка цикла: **Ctrl+C**. Пошагово от установки до первой «мысли»: **[docs/QUICKSTART.md](docs/QUICKSTART.md)** (интервал тиков, mock vs реальный LLM, дашборд §3b).

## Установка и зависимости

| Режим | Команда (из корня клона) |
|--------|---------------------------|
| Базовый код | `py -m pip install -e .` |
| Lance + эмбеддинги + граф | `py -m pip install -e ".[memory]"` |
| Веб-поиск `[WEB_SEARCH]` | `py -m pip install duckduckgo-search` или `py -m pip install -e ".[web]"` |
| Разработка (тесты, ruff) | `py -m pip install -e ".[dev]"` |

**Имя пакета на PyPI.** На индексе есть **другой** проект **`iskra`** (не этот репозиторий). Команда **`pip install iskra[web]`** с PyPI **не** ставит Iskra-1 и **не** подтягивает зависимости этого проекта. Используйте установку **из каталога клона** или зависимость по URL git (см. [PUBLIC_API.md](docs/PUBLIC_API.md)).

**Один интерпретатор Python.** На Windows часто `pip` ставит пакеты в одну версию Python (например 3.12), а **`py -m iskra`** запускает другую (например 3.14). Надёжно: **`py -m pip install …`** или **`"<путь>\python.exe" -m pip install …`** для того же интерпретатора.

При Lance и **`sentence-transformers`** модель загружается с Hugging Face; предупреждения про **`HF_TOKEN`** не фатальны — при желании задайте токен для лимитов на Hugging Face Hub.

## Версии

| Что | Где | Текущее значение |
|-----|-----|------------------|
| Продукт (SemVer) | [`VERSION`](VERSION) → `PRODUCT_VERSION` | **0.6.0** |
| Комплект документов | [`VERSION`](VERSION) → `DOCUMENTATION_BUNDLE` | **1.7.0** |
| Поле `schema_version` в YAML | [`VERSION`](VERSION) → `CONFIG_SCHEMA_VERSION`, [`config.yaml`](config.yaml) | **1** |

Кратко о линии **0.6.x**: опциональный **`tools.web_search`** и тег **`[WEB_SEARCH]`**, автоматическая доработка схемы Lance для колонок **`emotional_valence` / `arousal`** у старых таблиц, выверенные сообщения preflight про установку **`duckduckgo-search`**. Ранее в **0.5.x**: эмоции в памяти и состоянии, **`emotion_classifier`**, расширенный recall. Регламент версий: [docs/VERSIONING.md](docs/VERSIONING.md). История изменений: [docs/CHANGELOG.md](docs/CHANGELOG.md). Дорожная карта: [docs/ROADMAP.md](docs/ROADMAP.md). Стабильный API пакета: [docs/PUBLIC_API.md](docs/PUBLIC_API.md).

Целевая линия памяти и agency: [docs/MEMORY_AND_AGENCY.md](docs/MEMORY_AND_AGENCY.md), чеклист: [docs/TODO_MEMORY_AGENCY.md](docs/TODO_MEMORY_AGENCY.md). Идеи по качеству ответов и инструментам: [docs/TODO_QUALITY_BOOST.md](docs/TODO_QUALITY_BOOST.md).

## Документация

Навигация по каталогу **[docs/](docs/)**. Эталон конфигурации — **[config.yaml](config.yaml)** в корне репозитория. Черновики и материалы для размышления — **[research/](research/)**.

### Архитектура и поведение

| Файл | Содержание |
|------|------------|
| [FEATURES.md](docs/FEATURES.md) | **Обзор текущей реализации:** что реально делает демон (одним списком) |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Компоненты и потоки данных |
| [STATE_ENGINE.md](docs/STATE_ENGINE.md) | OU-процесс и переменные состояния |
| [TRIGGER_ENGINE.md](docs/TRIGGER_ENGINE.md) | Триггеры и случайный интервал |
| [MEMORY_SYSTEM.md](docs/MEMORY_SYSTEM.md) | Память, decay, recall |
| [MEMORY_AND_AGENCY.md](docs/MEMORY_AND_AGENCY.md) | Lance, граф, теги agency |
| [INTENT_GENERATOR.md](docs/INTENT_GENERATOR.md) | Промпты из события |
| [EVENT_LIFECYCLE.md](docs/EVENT_LIFECYCLE.md) | Жизненный цикл тика |
| [CONFIG_SCHEMA.md](docs/CONFIG_SCHEMA.md) | Полная схема **`config.yaml`**: memory / v2 / agency / **`emotion_classifier`** / **`tools`** / внешний ввод |
| [GROK_INTEGRATION.md](docs/GROK_INTEGRATION.md) | Идея LLM-адаптеров и интеграции |

### Практика и спецификация

| Файл | Содержание |
|------|------------|
| [QUICKSTART.md](docs/QUICKSTART.md) | Установка, запуск, дашборд, webhook, migrate, Lance без GPU |
| [UPGRADING.md](docs/UPGRADING.md) | Переход на ветку с эмоциями и расширенной памятью |
| [PUBLIC_API.md](docs/PUBLIC_API.md) | Стабильный API, зависимость из другого репозитория |
| [CHANGELOG.md](docs/CHANGELOG.md) | История релизов |
| [FORMAL_SPECIFICATION.md](docs/FORMAL_SPECIFICATION.md) | Формализованный контракт |
| [IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | План реализации по шагам |
| [ТЕХНИЧЕСКОЕ ЗАДАНИЕ.txt](docs/ТЕХНИЧЕСКОЕ%20ЗАДАНИЕ.txt) | Техническое задание (v2.1) |
| [VERSIONING.md](docs/VERSIONING.md) | Продукт, документы, schema_version |
| [ROADMAP.md](docs/ROADMAP.md) | Планы развития |

### Прочее

| Файл | Содержание |
|------|------------|
| [GITHUB_DISCOVERY.md](docs/GITHUB_DISCOVERY.md) | Описание репозитория для поиска |
| [PSYCHOLOGY_MODEL.md](docs/PSYCHOLOGY_MODEL.md) | Биологическая метафора развития |
| [TECHNOLOGIES.md](docs/TECHNOLOGIES.md) | Стек и окружение |
| [MANIFEST.md](docs/MANIFEST.md) | Зачем проект |
| [CONTRIBUTING.md](docs/CONTRIBUTING.md) | Участие в разработке |
| [CODE_OF_CONDUCT.md](docs/CODE_OF_CONDUCT.md) | Правила общения |

### Исследования (`research/`)

| Файл | Содержание |
|------|------------|
| [iskra.txt](research/iskra.txt) | Ранняя переписка и эволюция идеи |
| [Поиск паттернов надмира…](research/Поиск%20паттернов%20надмира%20в%20реальности%20-%20Grok.txt) | Исследовательский диалог |

## Использование как библиотеки

```python
import asyncio
from iskra import MainLoop, load_config

def run() -> None:
    config = load_config("config.yaml")
    loop = MainLoop(config)
    asyncio.run(loop.run())

if __name__ == "__main__":
    run()
```

`load_config` при ошибке **не** вызывает `sys.exit` — пробрасывает исключения (см. [PUBLIC_API.md](docs/PUBLIC_API.md)).

## Тесты

```bash
py -m pytest tests
```

## Лицензия

MIT
