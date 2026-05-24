"""Предстартовая самодиагностика: LLM, память, пути — до основного цикла."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:
    from iskra.core.main_loop import MainLoop

import httpx

from iskra.core.config import (
    SandboxConfig,
    validate_cross_config,
    WorldRSSConfig,
    WorldWeatherConfig,
)

logger = logging.getLogger("iskra.preflight")

# Минимум свободного места на томе ``data_dir`` (иначе старт блокируем — журнал/память/Lance).
PREFLIGHT_MIN_FREE_DISK_BYTES = 50 * 1024 * 1024

# Исходящий HTTP: несколько независимых URI (TLS и plain).
_CONNECTIVITY_URLS: tuple[str, ...] = (
    "https://www.cloudflare.com/cdn-cgi/trace",
    "http://connectivitycheck.gstatic.com/generate_204",
)


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


def _append_clock_line(cfg: object, out: list[str]) -> None:
    now = datetime.now().astimezone()
    tz_label = now.tzname() or "local"
    out.append(f"часы: {now.isoformat(timespec='seconds')} ({tz_label})")
    if getattr(cfg.world.time_sensor, "enabled", False):
        if now.year < 2020:
            raise PreflightError(
                "часы: дата ОС до 2020 года — при включённом world.time_sensor синхронизируйте время"
            )


async def _ensure_http_connectivity(client: httpx.AsyncClient, out: list[str]) -> None:
    last_err: Exception | None = None
    for url in _CONNECTIVITY_URLS:
        try:
            resp = await client.get(url, follow_redirects=True)
            if resp.status_code < 500:
                host = urlparse(url).hostname or url[:56]
                out.append(f"сеть: исходящий HTTP OK ({host}, статус {resp.status_code})")
                return
        except Exception as e:
            last_err = e
            continue
    raise PreflightError(
        "сеть: не удалось установить исходящий HTTP ни по одному из контрольных URI "
        f"(интернет, прокси, firewall). Последняя ошибка: {last_err}"
    )


async def _preflight_openweather(
    client: httpx.AsyncClient,
    weather: WorldWeatherConfig,
    out: list[str],
) -> None:
    params: dict[str, str] = {
        "appid": (weather.api_key or "").strip(),
        "units": "metric",
    }
    if weather.lat is not None and weather.lon is not None:
        params["lat"] = str(weather.lat)
        params["lon"] = str(weather.lon)
    else:
        params["q"] = weather.city.strip()
    try:
        resp = await client.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params=params,
            timeout=18.0,
        )
    except Exception as e:
        raise PreflightError(f"weather OpenWeatherMap: нет ответа от API ({e})") from e
    if resp.status_code == 401:
        detail = ""
        try:
            payload = resp.json()
            msg = payload.get("message")
            if msg:
                detail = f' Ответ API: "{msg}"'
        except Exception:
            detail = f" Ответ (начало): {resp.text[:240]!r}"
        raise PreflightError(
            "weather OpenWeatherMap: HTTP 401 — ключ не принят OpenWeatherMap."
            f"{detail}"
            " Частые причины: (1) ключ создан недавно — активация до ~2 часов после регистрации "
            "и подтверждения email (см. https://openweathermap.org/faq#error401 ); "
            "(2) в конфиг попали пробелы/не те символы — возьмите ключ только из раздела «API keys» "
            "личного кабинета; (3) проверка в браузере: "
            "https://api.openweathermap.org/data/2.5/weather?q=London&appid=ВАШ_КЛЮЧ — должно быть 200 JSON."
        )
    if resp.status_code != 200:
        raise PreflightError(
            f"weather OpenWeatherMap: HTTP {resp.status_code} — {resp.text[:280]!r}"
        )
    out.append("weather: OpenWeatherMap Current Weather API ответил HTTP 200")


async def _preflight_open_meteo(
    client: httpx.AsyncClient,
    weather: WorldWeatherConfig,
    out: list[str],
) -> None:
    from iskra.sensors import weather_sensor as ws_mod

    res = await ws_mod.fetch_open_meteo_summary(
        city=weather.city,
        lat=weather.lat,
        lon=weather.lon,
        client=client,
        timeout=18.0,
    )
    if res is None:
        raise PreflightError(
            "weather Open-Meteo: нет данных (геокодирование города или forecast). "
            "Проверьте world.weather.city / lat+lon, интернет и доступность open-meteo.com."
        )
    _deltas, summary = res
    preview = summary if len(summary) <= 200 else summary[:197] + "..."
    out.append(f"weather: Open-Meteo OK — проба: {preview}")


async def _preflight_rss_feeds(
    client: httpx.AsyncClient,
    rss_cfg: WorldRSSConfig,
    out: list[str],
) -> None:
    failures: list[str] = []
    if not rss_cfg.feeds:
        raise PreflightError("world.rss.enabled, но feeds пуст")
    for feed in rss_cfg.feeds:
        label = f"{feed.name} ({feed.url})"
        try:
            resp = await client.get(feed.url, follow_redirects=True, timeout=18.0)
            if resp.status_code >= 400:
                failures.append(f"{label}: HTTP {resp.status_code}")
                continue
            snippet = (resp.text[:2000] if resp.text else "").lstrip().lower()
            ct = (resp.headers.get("content-type") or "").lower()
            looks_feed = (
                "xml" in ct
                or snippet.startswith("<?xml")
                or "<rss" in snippet
                or "<feed" in snippet
                or "<rdf:rdf" in snippet
            )
            if not looks_feed:
                failures.append(f"{label}: ответ не похож на RSS/Atom (Content-Type={ct!r})")
        except Exception as e:
            failures.append(f"{label}: {e}")
    if failures:
        joined = "; ".join(failures[:12])
        extra = f"; … всего ошибок {len(failures)}" if len(failures) > 12 else ""
        raise PreflightError(f"RSS: проблемы с лентами — {joined}{extra}")
    out.append(f"RSS: все {len(rss_cfg.feeds)} лент(ы) доступны и выглядят как XML")


def _sandbox_smoke_readwrite(root: Path, out: list[str]) -> None:
    probe = root / ".iskra_preflight_probe_delete_me"
    try:
        probe.write_text("ok\n", encoding="utf-8")
        txt = probe.read_text(encoding="utf-8")
        if txt.strip() != "ok":
            raise PreflightError(f"sandbox: пробная запись в {probe} прочиталась некорректно")
        probe.unlink(missing_ok=False)
    except OSError as e:
        raise PreflightError(
            f"sandbox: нет полноценного чтения/записи в каталоге {root}: {e}"
        ) from e
    out.append(f"sandbox files: пробный файл записан и удалён в {root}")


async def _preflight_sandbox_interpreter(sb: SandboxConfig, out: list[str]) -> None:
    if not sb.python.enabled:
        out.append("sandbox python: выключен (sandbox.python.enabled=false)")
        return
    exe = sb.python.interpreter
    try:
        proc = await asyncio.create_subprocess_exec(
            exe,
            "-c",
            "import sys; sys.stdout.write(sys.version.split()[0]); sys.stdout.flush()",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        raise PreflightError(
            f"sandbox python: интерпретатор {exe!r} не найден (PATH или полный путь в sandbox.python.interpreter)"
        ) from e
    except OSError as e:
        raise PreflightError(f"sandbox python: не удалось запустить {exe!r}: {e}") from e

    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=20.0)
    except TimeoutError as e:
        proc.kill()
        raise PreflightError(f"sandbox python: таймаут при запуске {exe!r}") from e

    if proc.returncode != 0:
        err = stderr_b.decode("utf-8", errors="replace").strip()
        raise PreflightError(
            f"sandbox python: {exe!r} вернул код {proc.returncode}: {err}"
        )
    ver = stdout_b.decode("utf-8", errors="replace").strip()
    out.append(f"sandbox python: интерпретатор OK ({exe!r} → Python {ver})")


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

    wc = cfg.world
    _append_clock_line(cfg, out)

    needs_http_probe = ws.enabled or wc.weather.enabled or wc.rss.enabled
    if needs_http_probe:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(20.0, connect=12.0)
        ) as http_client:
            await _ensure_http_connectivity(http_client, out)
            if wc.weather.enabled:
                if wc.weather.provider == "open_meteo":
                    await _preflight_open_meteo(http_client, wc.weather, out)
                else:
                    await _preflight_openweather(http_client, wc.weather, out)
            if wc.rss.enabled:
                await _preflight_rss_feeds(http_client, wc.rss, out)

    active_world = wc.time_sensor.enabled or wc.weather.enabled or wc.rss.enabled
    if active_world:
        bits: list[str] = []
        if wc.time_sensor.enabled:
            bits.append(
                f"time_sensor: включён (interval={wc.time_sensor.check_interval_seconds}s, локальные слоты)"
            )
        else:
            bits.append("time_sensor: выключен")
        if wc.weather.enabled:
            loc = ""
            if wc.weather.lat is not None and wc.weather.lon is not None:
                loc = f", lat={wc.weather.lat}, lon={wc.weather.lon}"
            api_lbl = "Open-Meteo (без ключа)" if wc.weather.provider == "open_meteo" else "OpenWeatherMap"
            bits.append(f"weather: {api_lbl} ({wc.weather.city}{loc})")
        else:
            bits.append("weather: выключен")
        if wc.rss.enabled:
            bits.append(
                f"rss: {len(wc.rss.feeds)} лент(ы), категория по умолчанию «{wc.rss.default_category}» "
                "(проверка HTTP/XML выше)"
            )
        else:
            bits.append("rss: выключен")
        out.append("world: " + "; ".join(bits))
    else:
        out.append(
            "world: все сенсоры выключены (world.time_sensor / weather / rss — см. docs/TZ_ISKRA_0.7.0.md)"
        )

    sb = cfg.sandbox
    if sb.enabled:
        root = Path(sb.path)
        _dir_writable(root, "sandbox.path")
        if sb.files.enabled:
            _sandbox_smoke_readwrite(root, out)
        else:
            out.append("sandbox files: выключены в конфиге — проба записи файлов пропущена")
        await _preflight_sandbox_interpreter(sb, out)
        out.append(
            f"sandbox: включён path={sb.path!r}, "
            f"max_tag_ops_per_tick={sb.max_tag_ops_per_tick}, "
            f"subprocess timeout={sb.python.timeout_seconds}s"
        )
    else:
        out.append("sandbox: выключен")

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
    if du.free < PREFLIGHT_MIN_FREE_DISK_BYTES:
        raise PreflightError(
            f"диск: на томе data_dir критически мало места "
            f"(свободно {du.free} B, нужно ≥ {PREFLIGHT_MIN_FREE_DISK_BYTES} B, "
            f"это ~{PREFLIGHT_MIN_FREE_DISK_BYTES // (1024 * 1024)} MiB)"
        )
    pct_free = 100.0 * du.free / du.total
    out.append(
        f"диск: свободно ~{free_gib:.2f} GiB (~{pct_free:.1f}% тома), порог свободного места OK "
        f"(≥{PREFLIGHT_MIN_FREE_DISK_BYTES // (1024 * 1024)} MiB на томе data_dir={dd})"
    )

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
