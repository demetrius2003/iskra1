# TODO: Iskra1 как библиотека-основа, Iskra2+ как отдельные репозитории

**Статус:** ~~план~~ **реализовано для Iskra1 (секция 1)**; репозиторий Iskra2 — отдельная задача.  
**Цель:** две (и далее) **независимых** репозитория; **Iskra2+** ставит **Iskra1** как зависимость (`pip install iskra`) и не дублирует ядро. Публичный API Iskra1 **зафиксирован и документирован**.

Связанные документы: [ARCHITECTURE.md](ARCHITECTURE.md), [VERSIONING.md](VERSIONING.md), [CONFIG_SCHEMA.md](CONFIG_SCHEMA.md), [PUBLIC_API.md](PUBLIC_API.md), [CHANGELOG.md](CHANGELOG.md), [MANIFEST.md](MANIFEST.md).

---

## 1. Репозиторий Iskra1 (этот проект) — пакет `iskra`

### 1.1 Публичный API (контракт для потребителей)

- [x] Описать в одном месте **стабильные точки импорта** и гарантию совместимости (minor/patch не ломают импорты, перечислить модули/имена). → [PUBLIC_API.md](PUBLIC_API.md)
- [x] В `iskra/__init__.py` **явно** реэкспортировать стабильный набор: версия, `load_config` / `IskraConfig`, `MainLoop`, ключевые типы из `iskra.models`, фабрики `create_*`, протоколы и исключения LLM — см. `__all__`.
- [x] Зафиксировать **что НЕ публичный API** — [PUBLIC_API.md](PUBLIC_API.md) раздел «Не считается публичным API».
- [x] Правило: ломающие изменения → **major** SemVer + запись в changelog + при необходимости bump `CONFIG_SCHEMA_VERSION` ([VERSIONING.md](VERSIONING.md)). → [CHANGELOG.md](CHANGELOG.md)

### 1.2 Сборка, установка, релизы

- [x] Проверить, что `pyproject.toml` пригоден для **публикации** — `keywords`, `[project.urls]`, `[project.scripts]`.
- [x] **Changelog** — [CHANGELOG.md](CHANGELOG.md).
- [x] В **README** — «использование как библиотеки» и ссылка на [PUBLIC_API.md](PUBLIC_API.md).

### 1.3 CLI и библиотечное использование

- [x] В доке разделение: **CLI** (`python -m iskra`, `iskra`) vs **программный вход** — [PUBLIC_API.md](PUBLIC_API.md), [README](../README.md).
- [x] Разбор `argparse` вынесен в `iskra/cli.py`, `__main__.py` тонкий.

### 1.4 Конфигурация и схема

- [x] Псевдокод и примечание про `load_config` / CLI — [CONFIG_SCHEMA.md](CONFIG_SCHEMA.md); пути к эталонному и минимальному YAML — [PUBLIC_API.md](PUBLIC_API.md).

### 1.5 Расширяемость (когда понадобится Iskra2)

- [ ] (По мере реализации Iskra2) **хуки/стратегии** вокруг шагов `MainLoop` — отдельная задача.
- [ ] (Опционально) entry points для плагинов триггеров/памяти — отдельная задача.

---

## 2. Будущий репозиторий Iskra2 (и следующие) — **не** в этом репо

**Примечание:** пункты ниже — чеклист при создании отдельного репо; в Iskra1 — [PUBLIC_API.md](PUBLIC_API.md) и [ISKRA2_REPOSITORY_GUIDE.md](ISKRA2_REPOSITORY_GUIDE.md) (скопировать в Iskra-2, заменить `PLACEHOLDER` в URL).

- [ ] Новый `pyproject.toml`: зависимость `iskra>=0.3,<1` (уточнить по релизам).
- [ ] Собственный пакет (например `iskra2` / `iskra_agent`) — **не** копипаста `iskra/`.
- [ ] Реализация долгой памяти и агентности: композиция/наследование от `MainLoop`, кастомные `MemoryStore` / шаги, отдельный CLI или слой.
- [ ] Собственные тесты интеграции с **установленной** `iskra` (CI: `pip install` из PyPI/tagged ref).
- [ ] В README Isk2: требуемая версия `iskra`, ссылка на репо Iskra1.

---

## 3. Критерий готовности «затеи»

- [x] Iskra1: **PUBLIC_API** + `__all__` + Changelog.
- [x] Iskra1: установка `pip` / `pip from git` и импорт `iskra` без копирования кода (см. [PUBLIC_API.md](PUBLIC_API.md)).
- [ ] Iskra2 (отдельный репо) — когда будет создан, см. раздел 2.

---

**Версия этого TODO:** 1.1
