# TODO: долговременная память и agency (один репозиторий Iskra-1)

**Статус:** Фаза 0 закрыта (2026-04-25); дальше — реализация по фазам 2.1+  
**Нормативное ТЗ:** [MEMORY_AND_AGENCY.md](MEMORY_AND_AGENCY.md)  
**Блокирующих зависимостей нет:** можно вести дизайн и первые PR параллельно текущим релизам; ломающие изменения конфига — только с bump `CONFIG_SCHEMA_VERSION` и SemVer по [VERSIONING.md](VERSIONING.md).

---

## Фаза 0 — согласование (до большого кода)

- [x] Утвердить **имена секций** в `config.yaml`: `memory.backend` (`sqlite` \| `lance`), вложенный блок `memory.v2`, корневая секция `agency.level` — см. [CONFIG_SCHEMA.md](CONFIG_SCHEMA.md) § «Расширенная память и agency».  
- [x] Зафиксировать **синтаксис тегов** `[MEMORY_REQUEST]`, `[MEMORY_UPDATE]`, `[MEMORY_SAVE]` — см. тот же § и [MEMORY_AND_AGENCY.md](MEMORY_AND_AGENCY.md) §6.  
- [x] **optional-dependencies:** `pip install iskra[memory]` → LanceDB + NetworkX + sentence-transformers ([`pyproject.toml`](../pyproject.toml)).  
- [x] **Миграция:** однократно `python -m iskra migrate` (копия записей, эмбеддинги; исходный SQLite остаётся как бэкап) — описано в CONFIG_SCHEMA.  
- [x] Ссылка на закрытие Фазы 0 в [ROADMAP.md](ROADMAP.md) (сроки 2.1–2.3 уточняются по факту merge).

---

## Фаза 2.1 (MVP)

- [x] **Memory Store** Lance + фабрика `create_memory_store` (`memory.backend: lance`).  
- [x] **Эмбеддинги** (`sentence-transformers`) и векторный recall при `recall(..., context=...)`.  
- [x] **Граф** связей: NetworkX, JSON (`memory_graph.json` или `graph_edges_path`), тег `links`, `recall_graph_extra`.  
- [x] Парсер **тегов** + исполнение по `agency.level` (L0: только REQUEST; L1: предложения SAVE/UPDATE в лог без мутаций store; L2+: исполнение SAVE/UPDATE/links; L3: DELETE).  
- [x] Тесты: `test_memory_tags`, `test_lance_store` (при установленном `lancedb`), инвариант конфига.  
- [x] Фрагмент в [QUICKSTART.md](QUICKSTART.md) § 4b; [PUBLIC_API.md](PUBLIC_API.md) без новых символов в `__all__`.

---

## Фаза 2.2

- [x] Уровни **L2–L3**: пол `l2_importance_floor`, **`[MEMORY_DELETE]` только при L3**; L1 без пола.  
- [x] **clamp_min / clamp_max** для OU-переменных (bipolar valence и др.).  
- [x] **Консолидация** Lance: `general.consolidation_every_n_ticks`, `MemoryStore.consolidate()`.

---

## Фаза 2.3

- [x] Развитие **графа** и ассоциаций (взвешенные рёбра, усиление при повторном `link`, приоритет в `recall_graph_extra`, слияние при `repoint`).  
- [x] **Self-reflection** loop (`general.self_reflection_every_n_ticks`, `intent.user_prompts.self_reflection`).  
- [x] Базовый CI: **pytest** без extra `memory` (`.github/workflows/tests.yml`).

---

## Документация и бренд

- [x] В [README.md](../README.md) при появлении фичи — кратко: «расширенная память» + ссылка на MEMORY_AND_AGENCY.  
- [ ] При расширении **публичного API** — обновить `iskra.__all__` и [PUBLIC_API.md](PUBLIC_API.md), прогнать `tests/test_public_api.py`.

---

**Версия TODO:** 1.3
