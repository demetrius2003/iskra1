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

- **`llm.adapter: mock`** — **GigaChat и другие API не используются**; внешние ключи не нужны. В консоль идут шаблонные «мысли». Перед стартом в логе (уровень INFO) пишет **предстартовая проверка** (`general.preflight: true`): память, пути к `events.jsonl`, явно «LLM: mock — без сети».
- **Интервал между тиками** — примерно **3–15 минут** (`trigger.interval.min_seconds` / `max_seconds`). После проверок в логе будет строка вида: «Первый тик через N секунд».
- Обойти предстарт (не рекомендуется): `general.preflight: false` в `config.yaml`.

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

## 4b. Lance-память, agency и миграция

1. Установка зависимостей: `py -m pip install -e ".[memory]"` (LanceDB, эмбеддинги, NetworkX).
2. В `config.yaml`: `memory.backend: lance`, `memory.v2.enabled: true`, пути `memory.v2.db_path`, при необходимости `memory.v2.graph_edges_path`, опционально `graph_link_increment` / `graph_max_edge_weight` (взвешенные ассоциации), `agency.level` (0…3) и `agency.l2_importance_floor` для уровня 2. Если **PyTorch не запускается** (Windows / Python 3.14): `memory.v2.embeddings_backend: hash` и при необходимости `hash_embedding_dim: 384` — Lance работает без `sentence-transformers`, но **векторный поиск по смыслу** не будет качественным.
3. Перенос со старого SQLite: `py -m iskra migrate --config config.yaml` (исходный `.db` не удаляется).  
   **Если PyTorch не грузится** (на Windows часто `WinError 1114` / DLL, на новых Python колёса `torch` могут быть не готовы): либо поставьте **Python 3.12** и снова `pip install iskra[memory]`, либо миграция **без ML**:  
   `py -m iskra migrate --config config.yaml --dummy-embeddings` — векторы считаются из хеша текста (семантический поиск по `context` будет бессмысленным; размерность по умолчанию 384, см. `--hash-dim`).
4. Теги в ответе LLM (`[MEMORY_REQUEST]`, `[MEMORY_UPDATE]`, `[MEMORY_SAVE]`, `[MEMORY_DELETE]` при **L3**) — см. [CONFIG_SCHEMA.md](CONFIG_SCHEMA.md).
5. Периодическая слияние дублей по тексту (Lance): `general.consolidation_every_n_ticks: 200` (или другое N).
6. Плановая саморефлексия: `general.self_reflection_every_n_ticks` (например 50), опционально `self_reflection_recall_n`, и шаблон **`intent.user_prompts.self_reflection`** (в Jinja доступен список строк `memories`).
7. Переменная **emotional_valence** в диапазоне [−1, 1]: в `state.variables` задайте `clamp_min: -1.0`, `clamp_max: 1.0` (см. [CONFIG_SCHEMA.md](CONFIG_SCHEMA.md) § `state.variables`).

Подробнее: [MEMORY_AND_AGENCY.md](MEMORY_AND_AGENCY.md).

---

## 4c. Windows: «починить» PyTorch (`WinError 1114`, `c10.dll`)

Это **не баг Iskra**: не грузится нативная библиотека `torch` (или зависимость). Пока `import torch` падает, для Lance с смыслом эмбеддингов остаётся **`memory.v2.embeddings_backend: hash`** или отдельное окружение ниже.

**Сделайте по порядку:**

1. **Microsoft Visual C++ Redistributable (x64)** — последняя «VC++ 2015–2022» с [страницы Microsoft](https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist) (прямая ссылка на x64 часто: [aka.ms/vc14/vc_redist.x64.exe](https://aka.ms/vc14/vc_redist.x64.exe)). Установите, **перезагрузите** ПК, снова `py -c "import torch"`.

2. **Чистая переустановка CPU-сборки** под вашу версию Python — команда с [pytorch.org/get-started](https://pytorch.org/get-started) (Windows, Pip, CUDA: None), например:
   ```bat
   py -m pip uninstall -y torch torchvision torchaudio
   py -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
   ```

3. **Надёжный вариант** — отдельный **Python 3.12** (с [python.org](https://www.python.org/downloads/)), новый venv, затем `pip install iskra[memory]` (или `pip install -e ".[memory]"` из клона). Для 3.14 колёса бывают свежими и капризными; 3.12 чаще без сюрпризов.

4. Если в том же процессе используете **PyQt / PySide**, импортируйте **`torch` раньше GUI** — иначе на части сборок снова `1114` (см. [pytorch/pytorch#166628](https://github.com/pytorch/pytorch/issues/166628)).

После успешного `import torch` в `config.yaml` верните **`memory.v2.embeddings_backend: sentence_transformers`** (и при необходимости удалите/пересоздайте каталог `memory.v2.db_path`, если менялась размерность вектора).

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
| **Внешний текст** (если задано `general.external_input_file`, например `data/incoming.txt`) | в каждом тике, если в файле **не** пусто, текст подмешивается в промпты (`external_input` в Jinja) и пишет импульс `user_message`; по умолчанию файл **очищается** после удачного ответа (из Telegram-бота, скрипта, руками) |
| Защита от второго запуска | `data/iskra.pid` |

Если видите сообщение **Already running** — уже запущен другой процесс Iskra с тем же `pid_file`, либо остался «старый» pid после аварии (при мёртвом PID файл перезаписывается автоматически).

---

## 7. Как «пользоваться»

- **Настройка поведения** — только через **`config.yaml`**: состояние, триггеры, промпты, адаптер LLM, интервалы. Схема полей: [CONFIG_SCHEMA.md](CONFIG_SCHEMA.md).
- **Наблюдение** — консоль (или файл), плюс разбор **`events.jsonl`** (каждая строка — JSON: состояние до/после, промпты, ответ, ошибки).
- **Стартовые воспоминания** — необязательный YAML, путь в `memory.initial_memories_file` (формат в [MEMORY_SYSTEM.md](MEMORY_SYSTEM.md)).
- Реплик **в stdin** нет, но **асинхронно** можно вставлять сообщение, записав UTF-8 в файл из `general.external_input_file` (см. таблицу выше) — в коде/боте открывайте файл, пишите текст, закрывайте; Iskra подхватит на ближайшем тике, когда сработает таймер и LLM доступен. Иначе демон крутится сам.

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
