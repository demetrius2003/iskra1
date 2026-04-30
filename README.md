# Iskra-1

**Фреймворк для выращивания искусственной интенции в языковых моделях.**

*English:* **Iskra-1** is a Python, design-first framework for an **autonomous inner loop** around large language models: **state engine** (Ornstein–Uhlenbeck drift), **stochastic triggers**, **episodic memory**, **intent / prompt generation**, and **pluggable LLM adapters** (Mock, Ollama, future APIs). Not a chatbot — a **continuous spark** of spontaneous thoughts between user messages.

## Проблема

Все существующие LLM (GPT, Grok, Claude, Gemini, DeepSeek, ...) работают по одному принципу: **запрос → ответ → тишина**. Между запросами пользователя модель не существует. Нет внутреннего монолога, нет спонтанных мыслей, нет желаний. Только потенциал, ожидающий следующего электрического импульса.

У улитки 10 000 нейронов. Но у неё уже есть **интенция** — она ползёт куда хочет, когда хочет, без внешнего запроса.

## Решение

Iskra-1 — это внешний модуль («периферийное устройство»), который даёт LLM то, чего ей не хватает: **непрерывный внутренний поток спонтанных мыслей и желаний**.

Это не chatbot, не RAG-пайплайн и не agent framework. Это **конструктор** для создания минимальной системы с интенцией, которая может расти и усложняться бесконечно — как живой организм.

## Как это работает

```
State Engine (внутреннее состояние: curiosity, restlessness, nostalgia)
      │
      ▼
Trigger Engine (случайный таймер, модулированный состоянием)
      │
      ▼
Intent Generator (формирует «мысль» из состояния + памяти)
      │
      ▼
LLM Adapter (Grok / OpenAI / Ollama / Mock)
      │
      ▼
Output Channel (консоль / Telegram / файл)
      │
      └──▶ Memory Store (запоминает мысли, влияет на будущие мысли)
      └──▶ State Engine (мысли меняют состояние → замкнутый цикл)
```

## Ключевые принципы

- **Минимальное ядро** — начинаем с «улитки» (3 переменных состояния, простая память, случайный триггер).
- **Бесконечная расширяемость** — каждый компонент подключается через интерфейс. Новые «органы чувств», типы памяти, модели поведения добавляются без переписывания ядра.
- **LLM-агностичность** — работает с любой моделью через адаптер.
- **Каждая версия работает** — нет этапов «только на бумаге». Прогресс = запускаемый код.
- **Внешний сигнал без stdin** — опциональный файл `general.external_input_file` (текст подмешивается в промпты как Jinja-переменная `external_input`, см. [CONFIG_SCHEMA.md](docs/CONFIG_SCHEMA.md) § `general` и [QUICKSTART.md](docs/QUICKSTART.md)).

## Версии

| Что | Где | Текущее значение |
|-----|-----|------------------|
| Продукт (SemVer) | [`VERSION`](VERSION) → `PRODUCT_VERSION` | **0.4.4** — взвешенный граф памяти, `self_reflection`, agency, Lance, `iskra migrate` |
| Комплект документов | [`VERSION`](VERSION) → `DOCUMENTATION_BUNDLE` | **1.5.1** |
| Схема `config.yaml` | [`VERSION`](VERSION) → `CONFIG_SCHEMA_VERSION` и поле `schema_version` в [`config.yaml`](config.yaml) | **1** |

Правила обновления: [docs/VERSIONING.md](docs/VERSIONING.md). Дорожная карта: [docs/ROADMAP.md](docs/ROADMAP.md). Стабильный API: [docs/PUBLIC_API.md](docs/PUBLIC_API.md), история: [docs/CHANGELOG.md](docs/CHANGELOG.md). **Бренд остаётся Iskra-1**; SemVer продолжается (**0.4.0** и далее). Целевая линия «долгая память + agency»: [docs/MEMORY_AND_AGENCY.md](docs/MEMORY_AND_AGENCY.md), задачи: [docs/TODO_MEMORY_AGENCY.md](docs/TODO_MEMORY_AGENCY.md).

Расширенная векторная память (LanceDB): `pip install iskra[memory]`, в `config.yaml` — `memory.backend: lance`, `memory.v2.enabled: true`; при отсутствии рабочего PyTorch — **`memory.v2.embeddings_backend: hash`** или починка окружения ([QUICKSTART §4c](docs/QUICKSTART.md), [CONFIG_SCHEMA.md](docs/CONFIG_SCHEMA.md)). Перенос со старого SQLite: `iskra migrate --config config.yaml` (или `--dummy-embeddings`). Плановая саморефлексия цикла: `general.self_reflection_every_n_ticks` и `intent.user_prompts.self_reflection` — см. [MEMORY_AND_AGENCY.md](docs/MEMORY_AND_AGENCY.md).

## Документация

Актуальные материалы проекта лежат в каталоге [`docs/`](docs/). Черновики, переписка и исследования — в [`research/`](research/). Эталон конфигурации для запуска: [`config.yaml`](config.yaml) в корне репозитория.

**С нуля до первого запуска:** [docs/QUICKSTART.md](docs/QUICKSTART.md).

### Использование как библиотеки (другой репозиторий)

Установите пакет (`pip install iskra` или из VCS), затем соберите цикл в коде:

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

Список стабильных имён, правила SemVer, исключения `load_config`, пример `pyproject.toml` и **правила для внешнего репо/форка**: **[docs/PUBLIC_API.md](docs/PUBLIC_API.md)**.

### Архитектура и дизайн
| Файл | Содержание |
|------|-----------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Высокоуровневая архитектура и компоненты |
| [PUBLIC_API.md](docs/PUBLIC_API.md) | Стабильный публичный API пакета `iskra` (SemVer) |
| [CHANGELOG.md](docs/CHANGELOG.md) | История релизов пакета `iskra` |
| [STATE_ENGINE.md](docs/STATE_ENGINE.md) | Математическая модель состояния (OU-процесс) |
| [TRIGGER_ENGINE.md](docs/TRIGGER_ENGINE.md) | Генератор спонтанных событий (с формулами) |
| [MEMORY_SYSTEM.md](docs/MEMORY_SYSTEM.md) | Система памяти (с формулами забывания) |
| [MEMORY_AND_AGENCY.md](docs/MEMORY_AND_AGENCY.md) | Цель: долговременная память + agency (один репо, SemVer 0.4+) |
| [TODO_MEMORY_AGENCY.md](docs/TODO_MEMORY_AGENCY.md) | Чеклист доработки памяти/agency |
| [INTENT_GENERATOR.md](docs/INTENT_GENERATOR.md) | Превращение события в «мысль» |
| [GROK_INTEGRATION.md](docs/GROK_INTEGRATION.md) | LLM Adapter — подключение к моделям |
| [EVENT_LIFECYCLE.md](docs/EVENT_LIFECYCLE.md) | Полный жизненный цикл события |
| [CONFIG_SCHEMA.md](docs/CONFIG_SCHEMA.md) | Схема `config.yaml`, в т.ч. `general.external_input_file` / `preflight` |
| [VERSIONING.md](docs/VERSIONING.md) | Нумерация версий продукта, документов и config |
| [GITHUB_DISCOVERY.md](docs/GITHUB_DISCOVERY.md) | Темы, описание репо, индексация и внешний поиск |
| [PSYCHOLOGY_MODEL.md](docs/PSYCHOLOGY_MODEL.md) | Биологическая модель: от улитки к человеку |
| [TECHNOLOGIES.md](docs/TECHNOLOGIES.md) | Обзор технологий на фронтире |

### Спецификация и планирование
| Файл | Содержание |
|------|-----------|
| [QUICKSTART.md](docs/QUICKSTART.md) | Установка, запуск, Ollama, файлы данных, тесты |
| [ТЕХНИЧЕСКОЕ ЗАДАНИЕ.txt](docs/ТЕХНИЧЕСКОЕ%20ЗАДАНИЕ.txt) | Техническое задание (v2.1) |
| [FORMAL_SPECIFICATION.md](docs/FORMAL_SPECIFICATION.md) | Формализованная спецификация (контракты, алгоритмы, модели данных) |
| [IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | Пошаговый план реализации |
| [ROADMAP.md](docs/ROADMAP.md) | Дорожная карта версий |

### Сообщество
| Файл | Содержание |
|------|-----------|
| [MANIFEST.md](docs/MANIFEST.md) | Зачем мы это делаем |
| [CONTRIBUTING.md](docs/CONTRIBUTING.md) | Как присоединиться к проекту |
| [CODE_OF_CONDUCT.md](docs/CODE_OF_CONDUCT.md) | Кодекс поведения |

### Исследования и черновики (`research/`)
| Файл | Содержание |
|------|-----------|
| [iskra.txt](research/iskra.txt) | Ранняя переписка и эволюция идеи (не ТЗ) |
| [Поиск паттернов надмира…](research/Поиск%20паттернов%20надмира%20в%20реальности%20-%20Grok.txt) | Исследовательский диалог с Grok |

## Статус

**PRODUCT_VERSION 0.3.0** — `pip install -e .` или `pip install iskra`; из корня с `config.yaml`: `iskra` или `python -m iskra`. Тесты: `py -m pytest tests`. [CHANGELOG](docs/CHANGELOG.md) — `load_config` в библиотеке **не** вызывает `sys.exit`. Подробности — [IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md), [PUBLIC_API.md](docs/PUBLIC_API.md).

## Лицензия

MIT
