"""Предстартовая самодиагностика: LLM, память, пути — до основного цикла."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from iskra.core.main_loop import MainLoop

from iskra.core.config import validate_cross_config

logger = logging.getLogger("iskra.preflight")


class PreflightError(Exception):
    """Сбой обязательной предстартовой проверки."""


def _touch_write(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write("")
    if not os.access(path, os.W_OK):
        raise PreflightError(f"нет права на запись: {path}")


def _dir_writable(dir_path: Path, ctx: str) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    if not os.access(dir_path, os.W_OK):
        raise PreflightError(f"{ctx}: нет записи в каталог {dir_path}")


def _file_writable_if_exists(path: Path, ctx: str) -> None:
    if path.is_file() and not os.access(path, os.W_OK):
        raise PreflightError(f"{ctx}: нет записи в файл {path}")


def _file_readable_if_exists(path: Path, ctx: str) -> None:
    if path.is_file() and not os.access(path, os.R_OK):
        raise PreflightError(f"{ctx}: нет чтения {path}")


async def preflight(main: MainLoop) -> None:
    """Проверки до PID и цикла. При сбое — :exc:`PreflightError`."""
    from iskra import __version__ as iskra_version

    cfg = main.config
    validate_cross_config(cfg)
    out: list[str] = []
    ad = main.llm_adapter
    adapter_name = cfg.llm.adapter

    out.append(
        "конфиг: кросс-валидация OK (триггеры↔state, agency, self_reflection↔промпты и т.д.)"
    )

    em_counts = main._emotion.lexicon_counts()
    out.append(
        f"эмоции: лексикон pos={em_counts['positive_words']} "
        f"neg={em_counts['negative_words']} "
        f"high_arousal={em_counts['high_arousal_words']} "
        f"distinct_tokens={em_counts['distinct_tokens']}"
    )

    if "new_topic" in cfg.trigger.types:
        npool = len(cfg.trigger.random_topic_pool)
        out.append(f"триггер new_topic: пул тем после загрузки — {npool} строк")

    # --- Память (СУБД / бэкенд) ---
    try:
        n = main.memory_store.count()
    except Exception as e:
        raise PreflightError(
            f"память ({cfg.memory.backend}): не удалось прочитать хранилище: {e}"
        ) from e
    if cfg.memory.backend == "sqlite":
        out.append(
            f"память: SQLite — OK, записей: {n} "
            "(базовый режим: без LanceDB, векторного recall и графа в store; см. QUICKSTART §4b)"
        )
    else:
        v2 = cfg.memory.v2
        emb_desc = (
            f"sentence_transformers / {v2.embeddings_model}"
            if v2.embeddings_backend == "sentence_transformers"
            else f"hash (dim={v2.hash_embedding_dim}, без PyTorch)"
        )
        out.append(
            f"память: Lance / LanceDB — OK, записей: {n}; "
            f"memory.v2.db_path={v2.db_path}; эмбеддинги: {emb_desc}"
        )

    # --- Начальные воспоминания (YAML) ---
    seed = cfg.memory.initial_memories_file
    if seed:
        sp = Path(seed)
        if not sp.is_file():
            raise PreflightError(
                f"memory.initial_memories_file: файл не найден: {sp}"
            )
        _file_readable_if_exists(sp, "memory.initial_memories_file")
        out.append(f"seed memories: OK ({sp})")

    # --- Lance: эмбеддинги, каталог БД, граф ---
    if cfg.memory.backend == "lance" and cfg.memory.v2.enabled:
        from iskra.memory.lance_store import LanceMemoryStore

        if not isinstance(main.memory_store, LanceMemoryStore):
            raise PreflightError(
                "внутренняя ошибка: для backend=lance ожидается LanceMemoryStore"
            )
        lstore = main.memory_store
        try:
            dim = lstore.preflight_embedding_probe()
        except PreflightError:
            raise
        except Exception as e:
            v2 = cfg.memory.v2
            label = (
                v2.embeddings_model
                if v2.embeddings_backend == "sentence_transformers"
                else f"hash dim={v2.hash_embedding_dim}"
            )
            raise PreflightError(f"Lance эмбеддинги ({label}): {e}") from e
        v2 = cfg.memory.v2
        if v2.embeddings_backend == "hash":
            out.append(f"Lance: проба эмбеддингов OK (hash, dim={dim}, без PyTorch)")
        else:
            out.append(
                f"Lance: проба эмбеддингов OK (dim={dim}, sentence-transformers / {v2.embeddings_model})"
            )

        dbp = Path(cfg.memory.v2.db_path)
        _dir_writable(dbp, "memory.v2.db_path")
        out.append(f"Lance: каталог БД доступен на запись ({dbp})")

        extra_g = cfg.memory.v2.recall_graph_extra
        if extra_g > 0:
            out.append(
                f"Lance: recall_graph_extra={extra_g} (к recall подмешиваются соседи по графу)"
            )

        if cfg.memory.v2.graph_enabled:
            g = lstore.memory_graph_sidecar
            if g is None:
                raise PreflightError(
                    "memory.v2.graph_enabled=true, но граф не инициализирован. "
                    "Установите networkx (например pip install iskra[memory])."
                )
            gpath = (
                Path(cfg.memory.v2.graph_edges_path)
                if cfg.memory.v2.graph_edges_path
                else dbp / "memory_graph.json"
            )
            _dir_writable(gpath.parent, "граф памяти (каталог JSON)")
            _file_writable_if_exists(gpath, "граф памяти")
            out.append(
                f"Lance: граф ассоциаций (NetworkX) OK, JSON={gpath}; "
                f"link_increment={cfg.memory.v2.graph_link_increment}, "
                f"max_edge_weight={cfg.memory.v2.graph_max_edge_weight}"
            )
        else:
            out.append("Lance: граф выключен (memory.v2.graph_enabled=false)")

    ws = cfg.tools.web_search
    if ws.enabled:
        try:
            import duckduckgo_search  # noqa: F401
        except ImportError as e:
            exe = sys.executable
            raise PreflightError(
                "tools.web_search.enabled=true, но в этом интерпретаторе Python недоступен модуль "
                "duckduckgo_search (пакет pip: duckduckgo-search). "
                f"Интерпретатор сейчас: {exe}. "
                f'Установите в тот же Python: "{exe}" -m pip install duckduckgo-search '
                "(часто `pip install` попадает в другую версию, чем `py -m iskra`). "
                'Либо явно: py -3.12 -m iskra после установки в 3.12.'
            ) from e
        out.append(
            f"web_search: включён (max_results={ws.max_results}, max_per_tick={ws.max_per_tick}, "
            f"max_per_hour={ws.max_per_hour})"
        )
    else:
        out.append("web_search: выключен (tools.web_search.enabled=false)")

    # --- Внешний ввод (файл) ---
    ex = cfg.general.external_input_file
    if ex:
        ep = Path(ex)
        _dir_writable(ep.parent, "general.external_input_file")
        if ep.is_file():
            _file_readable_if_exists(ep, "general.external_input_file")
            out.append(f"external_input: OK (чтение {ep})")
        else:
            out.append(
                f"external_input: OK (каталог {ep.parent} доступен, файла ещё нет)"
            )

    # --- Agency и цикл (общие для SQLite и Lance) ---
    lv = cfg.agency.level
    floor = cfg.agency.l2_importance_floor
    out.append(
        f"agency: уровень L{lv} "
        "(L0—только MEMORY_REQUEST; L1—SAVE/UPDATE только лог «предложение», без записи в store; L2+—мутации; DELETE только L3); "
        f"l2_importance_floor={floor}"
    )
    sr = cfg.general.self_reflection_every_n_ticks
    if sr:
        out.append(
            f"саморефлексия: каждые {sr} успешных тиков → тик self_reflection "
            f"(recall_n={cfg.general.self_reflection_recall_n})"
        )
    else:
        out.append("саморефлексия: выключена (general.self_reflection_every_n_ticks не задан)")
    c_every = cfg.general.consolidation_every_n_ticks
    if c_every:
        if cfg.memory.backend == "lance":
            out.append(
                f"консолидация: каждые {c_every} успешных тиков (Lance — слияние дублей по тексту)"
            )
        else:
            out.append(
                f"консолидация: в конфиге N={c_every}, но при SQLite store это no-op "
                "(имеет эффект только с memory.backend=lance)"
            )
    elif cfg.memory.backend == "lance":
        out.append("консолидация: выключена (general.consolidation_every_n_ticks не задан)")

    # --- Event log (JSONL) ---
    if cfg.logging.event_log.enabled:
        elp = Path(cfg.logging.event_log.path)
        try:
            _touch_write(elp)
        except OSError as e:
            raise PreflightError(f"journal events: {e}") from e
        sz = elp.stat().st_size if elp.is_file() else 0
        out.append(
            f"journal: OK ({elp}); текущий размер {sz} байт; ротация при >{cfg.logging.event_log.rotate_mb} MiB"
        )
    else:
        out.append("journal: отключён")

    dd = Path(cfg.general.data_dir).resolve()
    dd.mkdir(parents=True, exist_ok=True)
    du = shutil.disk_usage(dd)
    free_gib = du.free / (1024**3)
    out.append(f"диск: свободно ~{free_gib:.2f} GiB (том каталога data_dir={dd})")

    # --- Output: файл ---
    if cfg.output.channel == "file":
        file_cfg: dict[str, Any] = dict(cfg.output.settings.get("file", {}))
        fpath = Path(str(file_cfg.get("path", "data/thoughts.log")))
        try:
            _touch_write(fpath)
        except OSError as e:
            raise PreflightError(f"output file: {e}") from e
        out.append(f"вывод (файл): OK ({fpath})")
    else:
        out.append(f"вывод: {cfg.output.channel} (путь в рантайме)")

    # --- LLM ---
    if adapter_name == "mock":
        out.append("LLM: mock — без сети и внешних ключей; ответы по шаблону из config")
    elif adapter_name == "ollama":
        ollama_base = getattr(ad, "_base_url", "?")
        if not await asyncio.to_thread(ad.is_available):
            raise PreflightError(
                f"Ollama недоступна: нет ответа HTTP 200 на {ollama_base}/api/tags. "
                "Запустите `ollama serve` и проверьте llm.settings.ollama.base_url."
            )
        model = getattr(ad, "_model", "?")
        out.append(f"LLM: ollama OK (модель: {model}, {ollama_base})")
    elif adapter_name == "gigachat":
        from iskra.llm.gigachat_adapter import GigaChatAdapter

        if not isinstance(ad, GigaChatAdapter):
            raise PreflightError("внутренняя ошибка: ожидался GigaChatAdapter")
        try:
            await ad.preflight_oauth()
        except Exception as e:
            raise PreflightError(
                f"GigaChat OAuth не прошёл (ключи, сеть, CA): {e}"
            ) from e
        out.append("LLM: GigaChat — OAuth OK (токен получен)")
    elif adapter_name in ("yandexgpt", "yandex_gpt"):
        from iskra.llm.yandexgpt_adapter import YandexGPTAdapter

        if not isinstance(ad, YandexGPTAdapter):
            raise PreflightError("внутренняя ошибка: ожидался YandexGPTAdapter")
        if not ad.is_available():
            raise PreflightError(
                "YandexGPT: задайте folder_id и iam_token (или api_key при auth=api_key) в config"
            )
        out.append("LLM: YandexGPT — реквизиты заданы (первый запрос проверит API)")
    else:
        available = ad.is_available()
        if not available:
            raise PreflightError(
                f"LLM-адаптер {adapter_name!r}: is_available() == False — проверьте настройки"
            )
        out.append(f"LLM: {adapter_name} — is_available() OK")

    logger.info(
        "preflight | ========== Iskra-1 предстарт (v%s) ==========",
        iskra_version,
    )
    for line in out:
        logger.info("preflight | %s", line)
    logger.info("preflight | ========== готово, запуск цикла ==========")
