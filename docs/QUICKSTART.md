# Быстрый старт Iskra-1

Как установить демон, запустить первый прогон и куда смотреть дальше.

---

## 1. Требования

- **Python 3.12+** (рекомендуется 3.12 или 3.13; на 3.14 обычно тоже работает).
- **Git** (если клонируете репозиторий).
- Для режима с настоящей моделью: **[Ollama](https://ollama.com/)** с загруженной моделью (например `llama3:8b`).

---

## 2. Установка

В корне репозитория (там же, где лежат `config.yaml`, `pyproject.toml` и каталог `iskra/`):

```bash
# Windows (если в PATH нет python/pip):
py -m pip install -e .

# Linux / macOS:
python -m pip install -e .
```

Флаг `-e` ставит пакет в **режиме разработки**: изменения в коде `iskra/` сразу видны без переустановки.

Проверка:

```bash
py -c "import iskra; print(iskra.__version__)"
```

---

## 3. Запуск по умолчанию

Рабочая директория должна быть **корень проекта** (чтобы находился `config.yaml` и относительные пути вроде `data/`).

```bash
cd /path/to/Iskra1
py -m iskra
```

Или явно указать конфиг:

```bash
py -m iskra --config config.yaml
py -m iskra --config C:\proj\Iskra1\my_profile.yaml
```

В эталонном `config.yaml` по умолчанию:

- **`llm.adapter: mock`** — без сети и без Ollama; в консоль идут шаблонные «мысли».
- **Инвал между тиками** — примерно **3–15 минут** (`trigger.interval.min_seconds` / `max_seconds`). После старта в логе будет строка вида: «Первый тик через N секунд».

Остановка: **Ctrl+C** (корректное завершение, pid-файл удаляется).

---

## 4. Быстрее увидеть первую мысль

Чтобы не ждать 3–15 минут, временно уменьшите интервал в `config.yaml`:

```yaml
trigger:
  interval:
    min_seconds: 10
    max_seconds: 30
```

Либо используйте тестовый конфиг с коротким интервалом (только для экспериментов):

```bash
py -m iskra --config tests/minimal.yaml
```

Убедитесь, что пути `memory.settings.db_path`, `logging.event_log.path` и `general.pid_file` в этом файле вас устраивают (по умолчанию там префикс `data/test_*`).

---

## 5. Режим с Ollama

1. Установите и запустите Ollama, подтяните модель, например: `ollama pull llama3:8b`.
2. В `config.yaml` установите:

```yaml
llm:
  adapter: "ollama"
  settings:
    ollama:
      base_url: "http://localhost:11434"
      model: "llama3:8b"
      timeout_seconds: 60
```

3. Снова: `py -m iskra`.

Если Ollama недоступна, в логе будет предупреждение, тик пропускается — процесс **не падает**.

---

## 5a. GigaChat и YandexGPT (облако, без своего GPU)

Полное описание полей: [GROK_INTEGRATION.md](GROK_INTEGRATION.md).

**GigaChat:** в личном кабинете GigaChat API получите Client ID и Secret (или готовый Base64-ключ). В окружение, например:

```text
set GIGACHAT_CLIENT_ID=...
set GIGACHAT_CLIENT_SECRET=...
```

В `config.yaml`:

```yaml
llm:
  adapter: "gigachat"
  settings:
    gigachat:
      client_id: "${GIGACHAT_CLIENT_ID}"
      client_secret: "${GIGACHAT_CLIENT_SECRET}"
      scope: "GIGACHAT_API_PERS"
      model: "GigaChat"
      ca_bundle_file: "certs/russian_trusted_root_ca.cer"
```

Файл **`russian_trusted_root_ca.cer`** возьмите из материалов GigaChat (портал Сбера) и положите в проект, например в каталог `certs/`, либо в корень — тогда путь `russian_trusted_root_ca.cer`. Запускайте из каталога, относительно которого этот путь существует.

**YandexGPT:** нужны каталог (`folder_id`) и либо IAM-токен, либо API-ключ. Пример с IAM:

```yaml
llm:
  adapter: "yandexgpt"
  settings:
    yandexgpt:
      folder_id: "${YC_FOLDER_ID}"
      auth: "iam"
      iam_token: "${YC_IAM_TOKEN}"
      model: "yandexgpt"
      model_version: "latest"
```

IAM-токен периодически обновляйте (скрипт/cron/`yc iam create-token`).

---

## 6. Что куда пишется

| Что | Где (по умолчанию в эталонном конфиге) |
|-----|----------------------------------------|
| Память SQLite | `data/memory.db` |
| Журнал событий (JSONL) | `data/events.jsonl` |
| Мысли в файл (если `output.channel: file`) | `data/thoughts.log` |
| Защита от второго запуска | `data/iskra.pid` |

Если видите сообщение **Already running** — уже запущен другой процесс Iskra с тем же `pid_file`, либо остался «старый» pid после аварии (при мёртвом PID файл перезаписывается автоматически).

---

## 7. Как «пользоваться»

- **Настройка поведения** — только через **`config.yaml`**: состояние, триггеры, промпты, адаптер LLM, интервалы. Схема полей: [CONFIG_SCHEMA.md](CONFIG_SCHEMA.md).
- **Наблюдение** — консоль (или файл), плюс разбор **`events.jsonl`** (каждая строка — JSON: состояние до/после, промпты, ответ, ошибки).
- **Стартовые воспоминания** — необязательный YAML, путь в `memory.initial_memories_file` (формат в [MEMORY_SYSTEM.md](MEMORY_SYSTEM.md)).
- Это **не чат**: пользователь не вводит реплики в процесс; демон крутится сам, пока его не остановят.

---

## 8. Тесты

```bash
py -m pip install -e ".[dev]"
py -m pytest tests
```

---

## 9. Что дальше по разработке

Ориентир по этапам: [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). Уже сделаны скелет, mock/Ollama, память, основной цикл и журнал; логичные следующие шаги:

- стабильный длительный прогон и доработка edge-case’ов;
- дополнительные LLM-адаптеры (облако);
- улучшение метрик и сценариев из [ТЕХНИЧЕСКОЕ ЗАДАНИЕ.txt](ТЕХНИЧЕСКОЕ%20ЗАДАНИЕ.txt).

Полный контракт реализации: [FORMAL_SPECIFICATION.md](FORMAL_SPECIFICATION.md).
