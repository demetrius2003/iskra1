# Iskra-2: как работать с Iskra-1 (библиотека `iskra`)

**Назначение:** этот текст рассчитан на **репозиторий Iskra-2** (отдельный git-проект). Скопируйте в корень (`DEVELOPING.md`, `ON_ISKRA1.md`) или в `docs/`, **заменив** в ссылках `https://github.com/PLACEHOLDER/Iskra1` на URL вашего **апстрим-репозитория** Iskra-1. Каноническая копия: [Iskra-1 `docs/ISKRA2_REPOSITORY_GUIDE.md`](https://github.com/PLACEHOLDER/Iskra1/blob/main/docs/ISKRA2_REPOSITORY_GUIDE.md).

Ориентир для **человека** и для **модели/агента** в IDE: сначала границы и зависимости, потом реализация.

---

## 1. Главное правило

**Iskra-1 — единственное «ядро»** цикла (состояние, триггеры, намерения, адаптеры LLM, вывод, журнал). В Iskra-2 **не** переписывайте этот цикл с нуля и **не** копируйте модули из репозитория Iskra-1.

**Правильно:**

- `pip install` пакет **`iskra`** и импорт из [публичного API](https://github.com/PLACEHOLDER/Iskra1/blob/main/docs/PUBLIC_API.md) (`iskra.__all__`).
- Развивайте **долгую память, агентность, сценарии, интеграции** в *этом* репозитории, поверх или вокруг `iskra`.

**Неправильно:**

- Вендорить **копию** `iskra/`, дублировать `MainLoop` / `StateEngine` / адаптеры «ради скорости».
- Стабилизировать **внутренние** модули Iskra-1 (`iskra.core.*` и т.д., не в `__all__`) в проде — в minor-релизе `iskra` это может смениться.

---

## 2. Зависимость

```toml
[project]
dependencies = [
  "iskra>=0.3,<1",  # верхнюю грань согласовать после 1.0.0; см. релизы Iskra-1
]
```

- Нижняя граница — по версии, с которой **реально** прошли тесты.
- PyPI, когда `iskra` опубликован; иначе: `pip install "iskra @ git+https://github.com/PLACEHOLDER/Iskra1.git@v0.3.0"` (тег/коммит подставьте сами).

---

## 3. Что брать из библиотеки (и только оттуда)

См. [PUBLIC_API](https://github.com/PLACEHOLDER/Iskra1/blob/main/docs/PUBLIC_API.md). Типовой сценарий Iskra-2:

- **`load_config`**, **`IskraConfig`**, при необходимости **`validate_cross_config`**.
- **`MainLoop`** — наследование или **композиция**; не копируйте тело `run()`.
- **`create_*`** — если `config` совместим; иначе **свои** классы по тем же **протоколам** (`MemoryStore`, `LLMAdapter`, `OutputChannel`, `TriggerType`).
- **Модели** (`SparkEvent`, `LLMResponse`, …) — не плодите дубликаты с той же ролью.

Перед новой подсистемой: [ARCHITECTURE](https://github.com/PLACEHOLDER/Iskra1/blob/main/docs/ARCHITECTURE.md) Iskra-1 — расширяйте плагинные границы, не клонируйте идеи.

---

## 4. Как расширять без велосипедов

| Задача | Подход |
|--------|--------|
| Другой бэкенд «долгой» памяти | Класс по **`MemoryStore`**, отдать в ядро свой экземпляр. |
| Шаги до/после LLM | Подкласс **`MainLoop`** или адаптер; сначала прочитайте `main_loop` в Iskra-1, чтобы согласовать тики. |
| Агент / инструменты | Слой над LLM или свой **`LLMAdapter`**, контракт **`LLMResponse`**. |
| Другой вывод | Реализация **`OutputChannel`**. |
| Триггеры | Под **`TriggerType`**; не хватает регистрации — [issue/PR в Iskra-1](https://github.com/PLACEHOLDER/Iskra1) (entry points, хуки), а не копия `trigger_engine`. |

---

## 5. Антипаттерны

1. Копипаст `Iskra1/iskra/...` в Iskra-2.  
2. Стабильные импорты только с [PUBLIC_API](https://github.com/PLACEHOLDER/Iskra1/blob/main/docs/PUBLIC_API.md); `iskra.core.state_engine` в проде — риск.  
3. Второй полный `async` цикл тиков рядом с `MainLoop` без явного дизайна.  
4. «Мини-форк» Iskra-1 вместо bump `iskra`.  
5. Submodule **исходников** Iskra-1 вместо `pip` — ломает модель «одна библиотека в окружении».

---

## 6. Iskra-1 vs Iskra-2 (где менять)

| Ситуация | Репозиторий |
|----------|-------------|
| Баг/фича ядра, публичный хук, общий адаптер, схема `config` | **Iskra-1** → релиз `iskra` |
| Продукт, долгий контекст агента, UI, внешние API, бренд | **Iskra-2** |

---

## 7. Тесты и CI

- CI: `pip install` → тесты против **установленного** `iskra` (без `PYTHONPATH` в чужой сорц).  
- Пин тега git при установке `iskra` с VCS.  
- Периодически — последняя **minor** в разрешённом диапазоне.

---

## 8. Быстрые ссылки (замените `PLACEHOLDER`)

| Тема | Iskra-1 (после подстановки org) |
|------|----------------------------------|
| Публичный API | `.../Iskra1/blob/main/docs/PUBLIC_API.md` |
| Архитектура | `.../Iskra1/blob/main/docs/ARCHITECTURE.md` |
| Схема конфига | `.../Iskra1/blob/main/docs/CONFIG_SCHEMA.md` |
| Changelog | `.../Iskra1/blob/main/docs/CHANGELOG.md` |
| План экосистемы | `.../Iskra1/blob/main/docs/TODO_LIBRARY_AND_ISKRA2.md` |

**Перед большим куском кода:** *уже ли это в `iskra`? это протокол? это issue в Iskra-1?*

---

## 9. Версия гайда

| Поле | Значение |
|------|----------|
| Документ | 1.0 |
| Ориентир `iskra` | ≥ 0.3.0 |

Правьте этот гайд по мере взросления: по возможности **в Iskra-1** (источник правды), затем копия в Iskra-2.
