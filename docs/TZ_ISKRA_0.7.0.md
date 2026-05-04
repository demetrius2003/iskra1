# Техническое Задание: Iskra-1 v0.7.0
## «Мультимодальное тело: реальный мир + песочница»

> **Статус:** планирование  
> **Предыдущая версия:** 0.6.0  
> **Блокирующих зависимостей нет** (ключи API опциональны; без них выключаются weather/rss)

---

## Цель

Дать системе контакт с реальным миром и возможность действовать — читать новости, чувствовать погоду и время, писать файлы, запускать код.

### Допущение по безопасности (эксперимент)

Для **v0.7.0** сознательно **не** закладываем изоляцию песочницы, запрет сети для **`RUN_PYTHON`** и отдельные жёсткие уровни agency под файловые/кодовые теги: приоритет — скорость проверки идей на **выделенной ВМ**, где падение окружения не критично. Запуск с недоверенной моделью или на «боевой» системе без доработок **не входит** в область этого ТЗ; последующие версии могут добавить политику и ограничения.

### Инженерные минимумы (не «безопасность», а предсказуемость)

- **Файловые пути sandbox** — только под **`sandbox.path`**: любой путь из тегов нормализуется и запрещается выход выше корня (защита от опечаток `../../`, не политика zero-trust).
- **`RUN_PYTHON` / `PYTHON_CODE`** — **`cwd`** процесса = корень **`sandbox.path`**; интерпретатор из конфига.
- Обрезка **stdout/stderr** до **`max_output_bytes`** с пометкой в тексте, что вывод усечён.

---

## Что добавляется

### 1. Датчики реального мира (WorldSensors)

#### Время суток

Без внешних API, локальные часы (timezone ОС). Импульсы в State Engine **только при смене слота** суток, а не на каждой проверке:

| Слот | Часы (локальное время) | Событие (логическое имя) | curiosity | restlessness | valence |
|------|-------------------------|--------------------------|-----------|--------------|---------|
| morning | 06–09 | `morning` | +0.10 | +0.15 | +0.10 |
| midday | 12–14 | `midday` | 0 | +0.05 | 0 |
| evening | 18–21 | `evening` | +0.05 | -0.10 | +0.05 |
| night | 23:00–05:59 (локально) | `night` | -0.10 | -0.20 | -0.05 |
| neutral | часы вне morning/midday/evening/night | `neutral` | 0 | 0 | 0 |

Промежутки вроде **10–11**, **15–17** попадают в слот **`neutral`** без автоматических импульсов (таблицу при желании расширить позже). Проверка по **`world.time_sensor.check_interval_seconds`**; при смене слота с последней известной — один вызов **`apply_impulse`** с настроенными дельтами (имя события импульса, например **`world_time_slot`** — зафиксировать в CONFIG_SCHEMA).

#### Погода

**OpenWeatherMap** (Current Weather API или эквивалент из бесплатного тарифа). Обновление не чаще **`update_interval_seconds`**.

Реализация: маппинг **не по русской строке**, а по **`weather[0].main`** и/или **`weather[0].id`** (Thunderstorm / Drizzle / Rain / Snow / Clear / Clouds / …). Таблица ТЗ ниже — целевые **импульсы после нормализации** (например Rain+Drizzle → «дождь»):

| Условие (после нормализации) | valence | nostalgia | arousal |
|------------------------------|---------|-----------|---------|
| Ясно / ясновато | +0.10 | 0 | 0 |
| Дождь / морось | -0.08 | +0.15 | 0 |
| Гроза | 0 | 0 | +0.20 |
| Снег | 0 | +0.10 | 0 |
| Облачно / смешанное | 0 | 0 | 0 |

При ошибке API или отсутствии ключа — пропуск обновления, в **`world_context`** строка «погода недоступна» или пусто.

#### RSS

Список лент в **`world.rss.feeds`**. Период **`update_interval_seconds`**.

- Забирать заголовки (**title** + **link** + опционально **published**).
- **Дедупликация**: не писать в память повторно ту же новость; ключ — **`link`**, при отсутствии — **`guid`** из item, иначе стабильный хеш **`feed_url + title`**.
- Категория записи в памяти: поле **`category`** из элемента ленты в конфиге (например `tech`, `science`); если не задано — **`world.rss.default_category`** (например `news`).
- **`save_importance`** / **`max_items_per_feed`** — как в конфиге ниже.

---

### 2. Песочница (Sandbox)

Корень — **`sandbox.path`** (по умолчанию `data/sandbox`). Создавать каталог при старте, если **`sandbox.enabled`**.

- **Файлы** — читать/писать только внутри корня; расширения из **`allowed_extensions`**; размер чтения ограничен **`max_file_size_bytes`**.
- **`LIST_FILES`** — по умолчанию **нерекурсивный** список имён в корне sandbox (рекурсия — только если явно добавят ключ в конфиг позже).
- **Python** — **`subprocess`**, **`timeout_seconds`**, объединённый stdout+stderr в одну строку для памяти, обрезка по **`max_output_bytes`**.
- **Результат** — запись в память **`category="sandbox_result"`** (или из конфига **`sandbox.memory_category`**).

Полный доступ к ФС и сети **вне** каталога sandbox со стороны **интерпретатора** не запрещается (см. допущение по безопасности); ограничиваются только операции **файловых тегов** путём привязки к **`sandbox.path`**.

---

### 3. Новые теги agency

Синтаксис полей — как у существующих **`[MEMORY_*]`**: одна операция на строку или согласованный многострочный блок только для **`[PYTHON_CODE]`** … **`[/PYTHON_CODE]`**.

```
[WRITE_FILE] filename: "note.txt", content: "текст"
[READ_FILE] filename: "note.txt"
[LIST_FILES]
[RUN_PYTHON] filename: "idea.py"
[PYTHON_CODE]
print("результат")
[/PYTHON_CODE]
```

Рекомендация: исполнять после разбора **`MEMORY_*`** в том же проходе **`MainLoop`** (или одним модулем «post-parse actions»), логировать ошибки тегов на уровне INFO/WARNING, не валить тик.

Опционально **`sandbox.max_tag_ops_per_tick`** (например 5) — защита от спама тегов в одном ответе.

---

### 4. Новый модуль: `iskra/sensors/`

```
iskra/sensors/
    __init__.py
    time_sensor.py      # слоты суток + импульсы только при смене слота
    weather_sensor.py   # OpenWeatherMap → импульсы + фрагмент для world_context
    rss_sensor.py       # RSS → память с дедупом
    world_context.py    # агрегатор короткой строки/блока для промпта
```

### 5. Новый модуль: `iskra/sandbox/`

```
iskra/sandbox/
    __init__.py
    file_ops.py         # WRITE_FILE / READ_FILE / LIST_FILES
    python_runner.py    # RUN_PYTHON / PYTHON_CODE
    sandbox_manager.py  # единая точка входа из MainLoop / парсера тегов
```

---

## Зависимости

| Назначение | Предложение |
|------------|-------------|
| HTTP | уже есть **`httpx`** в проекте — погода и RSS (или **`feedparser`** для RSS по желанию) |
| RSS | опциональный extra **`feedparser`** в **`pyproject.toml`** (`iskra[world]` или расширить **`[memory]`** — решить при реализации) |

---

## Изменения в конфиге

Новые секции **`world`** и **`sandbox`** опциональны; при отсутствии поведение как в **0.6.x**.

```yaml
world:
  context_max_chars: 1200        # обрезка агрегата для промпта (system или отдельное поле Jinja)
  time_sensor:
    enabled: true
    check_interval_seconds: 300  # как часто проверять часы; импульсы только при смене слота
    # опционально: переопределение импульсов по имени слота — см. CONFIG_SCHEMA
  weather:
    enabled: false
    api_key: "${OPENWEATHER_KEY}"
    city: "Moscow"               # или lat/lon — уточнить в схеме
    update_interval_seconds: 3600
  rss:
    enabled: false
    update_interval_seconds: 3600
    default_category: "news"
    max_items_per_feed: 5
    save_importance: 0.5
    feeds:
      - name: "Хабр"
        url: "https://habr.com/ru/rss/hubs/all/"
        category: "tech"
      - name: "Наука"
        url: "https://nplus1.ru/rss"
        category: "science"

sandbox:
  enabled: true
  path: "data/sandbox"
  memory_category: "sandbox_result"
  max_tag_ops_per_tick: 8       # опционально
  python:
    enabled: true
    interpreter: "python"
    timeout_seconds: 30
    max_output_bytes: 10000
  files:
    enabled: true
    max_file_size_bytes: 102400
    allowed_extensions: [".txt", ".md", ".py", ".json"]
    list_recursive: false
```

---

## Версионирование и схема

- **`PRODUCT_VERSION`** → **0.7.0**, документация bundle при необходимости — по [VERSIONING.md](VERSIONING.md).
- **`schema_version` в `config.yaml`**: если новые секции **полностью опциональны** и дефолты не ломают старый конфиг — можно оставить **`1`**; если вводится обязательное поле — поднять **`CONFIG_SCHEMA_VERSION`** и описать в CONFIG_SCHEMA.

---

## Интеграция с промптом

- В **`Jinja2IntentGenerator`** (или эквивалент): переменная **`world_context`** — результат **`world_context.build()`** (строка), уже обрезанная по **`world.context_max_chars`**.
- **`system_prompt_template`**: фраза вида «если ниже пусто — мир не обновлялся». Эталонный **`config.yaml`** — короткий абзац про sandbox и теги.

---

## TODO v0.7.0

### Фаза 0 — согласование (до кода)

- [ ] Утвердить список RSS лент и **`default_category`**
- [ ] Получить ключ OpenWeatherMap (бесплатный) или оставить **`enabled: false`** до ключа
- [ ] Утвердить таймауты и лимиты sandbox (**`max_output_bytes`**, **`max_file_size_bytes`**)
- [ ] Импульсы времени: таблица слотов и нейтральный «промежуток дня» — ок или расширить окна
- [ ] Политика обрезки: **`world.context_max_chars`**, усечённый stdout помечать `[…]` в конце

---

### Фаза 0.7.1 — датчики реального мира

- [ ] **`time_sensor.py`**: слот по локальным часам; хранить **`last_slot`**; при смене — **`apply_impulse`**
- [ ] Подключить в **MainLoop**: раз в тик или по таймеру монотонного времени — вызов проверки не чаще **`check_interval_seconds`**
- [ ] **`weather_sensor.py`**: httpx, парсинг JSON, нормализация **`main`/`id`**, импульсы + строка для агрегатора
- [ ] **`rss_sensor.py`**: fetch + parse, дедуп по **`link`/`guid`/hash**, **`MemoryStore.store`** с **`category`** из ленты
- [ ] **`world_context.py`**: склейка «время / погода / последние заголовки (без простыни)»
- [ ] Intent: **`world_context`** в шаблонах (**`system`** и при необходимости **`user`**)
- [ ] Preflight: при **`enabled`** — проба ключа погоды (без бана по лимиту — один запрос или отложенная проверка), доступность URL RSS (HEAD/GET), наличие **`feedparser`** если выбран
- [ ] Тесты: unit на time_slot transitions, weather mapping, rss dedupe (моки HTTP)

---

### Фаза 0.7.2 — песочница

- [ ] Создать **`sandbox.path`** при старте
- [ ] **`file_ops.py`**: пути только под корнем; **`LIST_FILES`** с **`list_recursive`**
- [ ] **`python_runner.py`**: **`cwd=sandbox.path`**, timeout, обрезка вывода
- [ ] Парсер тегов (расширение **`memory_tags.py`** или **`sandbox_tags.py`**) + вызов из **MainLoop**
- [ ] Сохранение результата в память (**`memory_category`**)
- [ ] Обновить **`system_prompt`** — формулировка «своя комната» / sandbox (см. совет ниже)
- [ ] Тесты: path traversal отсекается для файловых операций; runner с таймаутом и мок **`subprocess`**

---

### Фаза 0.7.3 — шлифовка

- [ ] Preflight: сводка **world** / **sandbox**
- [ ] Документация: **ARCHITECTURE**, **CONFIG_SCHEMA**, **PUBLIC_API**, **[FEATURES.md](FEATURES.md)** — новые возможности
- [ ] Bump **VERSION** / **pyproject** → **0.7.0**

---

## Новая документация

| Файл | Содержание |
|------|------------|
| `docs/WORLD_SENSORS.md` | Время (слоты), погода (OWM), RSS, дедуп, импульсы |
| `docs/SANDBOX.md` | Теги, корень **`sandbox.path`**, cwd для Python, лимиты; раздел «риски» → отсылка к допущению v0.7.0 |

Обновить существующие:

- `docs/ARCHITECTURE.md` — поток **MainLoop → sensors → intent**, **sandbox**
- `docs/CONFIG_SCHEMA.md` — **`world`**, **`sandbox`**, Pydantic
- `docs/PUBLIC_API.md` — при экспорте новых символов

---

## Совет по реализации

**Начни с `time_sensor`.** Ноль внешних API; сразу видно смену слота и импульсы в логе состояния.

**Sandbox в system_prompt** — как «своя комната», не сухой список команд (см. уже сказанное в ТЗ v1.0).

**RSS** — сразу заложить дедуп и **`default_category`**, иначе память раздуется за одну ночь на cron-подобном цикле.

---

**Версия ТЗ:** 1.1  
**Составлено:** май 2026  
