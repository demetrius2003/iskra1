# Версионирование Iskra-1

**Версия документа:** 1.0  
**Комплект документации:** 1.0.1 (см. файл `VERSION` в корне репозитория)

---

## 1. Файл `VERSION` (корень репозитория)

Машиночитаемые константы в формате `КЛЮЧ=значение`:

| Ключ | Назначение |
|------|----------------|
| `PRODUCT_VERSION` | Версия **продукта** (код, релизы). [Semantic Versioning](https://semver.org/lang/ru/): `MAJOR.MINOR.PATCH`. |
| `DOCUMENTATION_BUNDLE` | Версия **согласованного комплекта** документов (ТЗ, формальная спецификация, схема конфигурации, выровненные пути в коде/доках). |
| `CONFIG_SCHEMA_VERSION` | Целое число — значение поля `schema_version` в `config.yaml`. Меняется только при несовместимых изменениях схемы конфигурации. |

При правке спецификации обновляйте `DOCUMENTATION_BUNDLE` по SemVer:

- **PATCH** — уточнения формулировок, опечатки, несущественные примеры.
- **MINOR** — новые необязательные поля конфига, новые разделы документации без ломки старого.
- **MAJOR** — несовместимые изменения контрактов, удаление полей конфига, смена структуры пакета `iskra/`.

---

## 2. Версии отдельных документов

Независимые **редакции** ключевых текстов (указаны в шапке каждого файла):

| Документ | Поле версии | Связь |
|----------|-------------|--------|
| `ТЕХНИЧЕСКОЕ ЗАДАНИЕ.txt` | Версия документа (например 2.1) | Задаёт цели и приёмку; ссылается на комплект через `VERSION`. |
| `FORMAL_SPECIFICATION.md` | Версия документа (например 1.1) | Контракты реализации; основание — актуальное ТЗ. |
| `CONFIG_SCHEMA.md` | Версия документа | Описание YAML и Pydantic; `schema_version` в YAML. |
| `IMPLEMENTATION_PLAN.md` | Версия документа | План работ; структура каталогов **как в** `FORMAL_SPECIFICATION.md`. |

Редакции документов не обязаны совпадать с `DOCUMENTATION_BUNDLE`: бандл отражает **согласованность набора** в конкретный момент времени.

---

## 3. Дорожная карта продукта (`ROADMAP.md`)

Версии **v0.01**, **v0.1**, **v0.2** и т.д. — это **кодовые этапы развития** («Скелет», «Амёба», «Улитка»…): что уже умеет **запускаемая** система. Они не заменяют `PRODUCT_VERSION` из SemVer: при первом публичном релизе кодовая «Публикация» (v1.0 в roadmap) может соответствовать, например, `PRODUCT_VERSION=1.0.0`.

---

## 4. Эталон `config.yaml`

Каноническая копия для разработки и тестов лежит в **корне репозитория**: `config.yaml`. Тот же текст приведён в `CONFIG_SCHEMA.md` (раздел «Полный эталонный файл») для удобства чтения; при расхождении приоритет у файла в корне — его нужно синхронизировать с документом.

---

## 5. История комплекта

**1.1.0**

- [PUBLIC_API.md](PUBLIC_API.md), [CHANGELOG.md](CHANGELOG.md) (реализация библиотечного API v0.3.0); уточнения в [CONFIG_SCHEMA.md](CONFIG_SCHEMA.md) (загрузка конфигурации, `load_config`). *(Устаревшие заметки про отдельный downstream-репозиторий сведены в раздел «Внешний репозиторий» в PUBLIC_API.)*

**1.2 (редакция CONFIG_SCHEMA 1.3 и связанные тексты)**

- [CONFIG_SCHEMA.md](CONFIG_SCHEMA.md) § `general`: `external_input_file`, `external_input_max_chars`, `external_input_clear_after_use`, `preflight`; [INTENT_GENERATOR.md](INTENT_GENERATOR.md) (переменная Jinja `external_input`); [ARCHITECTURE.md](ARCHITECTURE.md) §8; [EVENT_LIFECYCLE.md](EVENT_LIFECYCLE.md); [README.md](../README.md); [PUBLIC_API.md](PUBLIC_API.md) (сводка по конфигу).

**1.2.1 (PUBLIC_API 1.1)**

- [PUBLIC_API.md](PUBLIC_API.md): явная пометка актуальности относительно `__all__`, список имён, ссылка на `tests/test_public_api.py`.

**1.3.0**

- [MEMORY_AND_AGENCY.md](MEMORY_AND_AGENCY.md), [TODO_MEMORY_AGENCY.md](TODO_MEMORY_AGENCY.md); обновления [ROADMAP.md](ROADMAP.md), [README.md](../README.md); пометки «архив» в `research/`; бренд Iskra-1 + линия SemVer 0.4+.

**1.3.1**

- Удалены вводящие в заблуждение вспомогательные документы в `docs/` про отдельный downstream-репозиторий; правила для внешних репо — раздел «Внешний репозиторий поверх `iskra`» в [PUBLIC_API.md](PUBLIC_API.md) (v1.2).

**1.5.1**

- [CONFIG_SCHEMA.md](CONFIG_SCHEMA.md) v1.5.1: `memory.v2.graph_link_increment`, `graph_max_edge_weight`; взвешенный граф в коде; [MEMORY_AND_AGENCY.md](MEMORY_AND_AGENCY.md); `networkx` в optional-dependencies `dev` ([pyproject.toml](../pyproject.toml)).

**1.5.0**

- [CONFIG_SCHEMA.md](CONFIG_SCHEMA.md) v1.5: `general.self_reflection_every_n_ticks`, `self_reflection_recall_n`, ключ `intent.user_prompts.self_reflection`; [FORMAL_SPECIFICATION.md](FORMAL_SPECIFICATION.md) INV-CONFIG; [INTENT_GENERATOR.md](INTENT_GENERATOR.md); workflow CI `tests` без `iskra[memory]`.

**1.4.0**

- [CONFIG_SCHEMA.md](CONFIG_SCHEMA.md) v1.4: утверждённый дизайн расширенной памяти (`memory.v2`, `backend: lance`), `agency.level`, протокол тегов памяти, команда миграции; [MEMORY_AND_AGENCY.md](MEMORY_AND_AGENCY.md), [TODO_MEMORY_AGENCY.md](TODO_MEMORY_AGENCY.md) (Фаза 0 закрыта); optional-dependencies `iskra[memory]` в [pyproject.toml](../pyproject.toml).

**1.0.1**

- `docs/GITHUB_DISCOVERY.md`, англоязычный абзац в `README.md`, `CITATION.cff`, `.github/ISSUE_TEMPLATE/config.yml`.

**1.0.0**

- Введены `VERSION`, `docs/VERSIONING.md`, корневой `config.yaml`.
- Выровнена структура: `EventLog` → `iskra/event_log.py` (как в формальной спецификации).
- В ТЗ помечены критерии **[ОБЯЗАТЕЛЬНО]** / **[ИССЛЕДОВАНИЕ]** для первого исполняемого прототипа.
- План реализации приведён к структуре пакета из `FORMAL_SPECIFICATION.md`.
