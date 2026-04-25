# Changelog

Все существенные изменения пакета `iskra` и публичного API описываются здесь. Формат по мотивам [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/); нумерация — [SemVer](https://semver.org/lang/ru/). Версия прод дублируется в [VERSION](../VERSION) (`PRODUCT_VERSION`).

## [Unreleased]

- Исправление: подстановка `${VAR}` в `config.yaml` выполняется только в **значениях** YAML после разбора; плейсхолдеры в **комментариях** (например документация с `${VAR}`) больше не требуют переменных окружения.
- Предстартовая **самодиагностика** (`general.preflight`, по умолчанию `true`): проверка памяти, путей журнала/файла вывода, доступности LLM (для `mock` — явное сообщение «без сети»; для GigaChat — OAuth; для Ollama — `/api/tags`). CLI выходит с кодом 1 при сбое.
- **Внешний ввод из файла** (`general.external_input_file`): перед тиком (если LLM готов) читается непустой UTF-8; текст в промптах Jinja2 как `external_input`, импульс `user_message` к состоянию; по умолчанию файл **очищается после** успешного ответа и вывода (повтор иначе). Подходит для вставки текста с Telegram, скрипта, ручного редактора.

## [0.3.0] — 2026-04-25

### Добавлено

- Публичный API: реэкспорты в `iskra`, список `__all__`, документ [docs/PUBLIC_API.md](PUBLIC_API.md).
- Консольная команда: `iskra` (entry point на `iskra.cli:main` в [pyproject.toml](../pyproject.toml)).
- [docs/CHANGELOG.md](CHANGELOG.md) (этот файл).
- [project.urls] и [keywords] в [pyproject](../pyproject.toml) для публикации на PyPI.

### Изменено

- [**Совместимость:**] `load_config()` больше **не** вызывает `sys.exit`; при ошибке выбрасываются исключения. CLI (`python -m iskra`, `iskra`) обрабатывает их и выходит с кодом 1. Потребителям библиотеки не нужно менять логику, кроме случаев, если они **ожидали** завершения процесса при неверном конфиге.
- `iskra.__main__` делегирует в `iskra.cli`.

### Для сопровождения

- См. [docs/TODO_LIBRARY_AND_ISKRA2.md](TODO_LIBRARY_AND_ISKRA2.md) — закрытие чеклиста «Iskra1 как библиотека».

## [0.2.0] — ранее

- Исполняемое ядро, `python -m iskra`, тесты, адаптеры LLM, память и т.д. (см. [ROADMAP.md](ROADMAP.md), [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)).

[Unreleased]: https://github.com/PLACEHOLDER/Iskra1/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/PLACEHOLDER/Iskra1/compare/v0.2.0...v0.3.0
