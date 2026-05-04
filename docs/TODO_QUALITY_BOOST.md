# TODO: качество продукта и удобство конфигурации

Накопительный список улучшений. Закрытые пункты отмечены `[x]`; при релизе переносите существенное в [CHANGELOG.md](CHANGELOG.md).

Связанные документы: [TODO_MEMORY_AGENCY.md](TODO_MEMORY_AGENCY.md), [CONFIG_SCHEMA.md](CONFIG_SCHEMA.md), [VERSION](../VERSION).

---

## Конфигурация: пул тем вне `config.yaml`

**Цель:** не раздувать основной конфиг сотнями строк `random_topic_pool`.

### Задачи

- [x] Схема `trigger.random_topic_pool_file`, загрузка и слияние с инлайном; эталон `data/random_topic_pool.yaml`; документация и тесты.

---

## Надёжность и доверие к поведению

- [x] Интеграционный тест полного тика (SQLite): mock LLM → эмоции → запись → `recall` со `state`.
- [x] Интеграционный тик на Lance (`embeddings_backend: hash`, `pytest.importorskip("lancedb")`).
- [x] Контракт `events.jsonl`: `EventLogLineModel` + round-trip тест.
- [x] Cross-config эмоций и импульсов состояния.

---

## Качество эмоций и классификатора

- [x] Расширяемый лексикон: **`emotion_classifier.lexicon_custom_file`** (merge с основным файлом).
- [x] Ограничение длины входа классификатора: **`emotion_classifier.max_input_chars`** (стабильнее на длинных ответах).

---

## Операционка и отладка

- [x] **`python -m iskra --dry-run`** — один проход без LLM и без записи в память / JSONL.
- [x] Preflight: счётчики лексикона, размер журнала, свободное место на диске (`data_dir`).

---

## Документация и миграции

- [x] [UPGRADING.md](UPGRADING.md), отсылки в README / QUICKSTART / CONFIG_SCHEMA.

---

## «Бустеры» опыта

- [x] **Дашборд:** `python -m iskra dashboard` — статический HTML (Chart.js CDN) из `events.jsonl` за окно **`--hours`** (по умолчанию 24 ч).
- [x] **Резюме:** `python -m iskra summary` → `daily_summary.txt` под тот же интервал (удобно для cron).
- [x] **Webhooks:** `python -m iskra webhook` — POST JSON `{"text":"..."}` или `text/plain` → UTF-8 в **`general.external_input_file`** или **`--target`** (по умолчанию только `127.0.0.1`).

---

**Версия TODO:** 1.3  
**Последнее обновление:** 2026-04-28
