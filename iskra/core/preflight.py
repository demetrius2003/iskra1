"""Предстартовая самодиагностика: LLM, память, пути — до основного цикла."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from iskra.core.main_loop import MainLoop

logger = logging.getLogger("iskra.preflight")


class PreflightError(Exception):
    """Сбой обязательной предстартовой проверки."""


def _touch_write(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write("")
    if not os.access(path, os.W_OK):
        raise PreflightError(f"нет права на запись: {path}")


async def preflight(main: MainLoop) -> None:
    """Проверки до PID и цикла. При сбое — :exc:`PreflightError`."""
    cfg = main.config
    out: list[str] = []
    ad = main.llm_adapter
    adapter_name = cfg.llm.adapter

    # --- Память (СУБД / бэкенд) ---
    try:
        n = main.memory_store.count()
    except Exception as e:
        raise PreflightError(
            f"память ({cfg.memory.backend}): не удалось прочитать хранилище: {e}"
        ) from e
    out.append(f"память ({cfg.memory.backend}): OK, записей: {n}")

    # --- Event log (JSONL) ---
    if cfg.logging.event_log.enabled:
        elp = Path(cfg.logging.event_log.path)
        try:
            _touch_write(elp)
        except OSError as e:
            raise PreflightError(f"journal events: {e}") from e
        out.append(f"journal: OK ({elp})")
    else:
        out.append("journal: отключён")

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

    for line in out:
        logger.info("preflight | %s", line)
    logger.info("preflight | готово. Запускаем основной цикл.")
