"""RSS → память с дедупликацией ключей."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

from iskra.core.config import WorldRSSConfig, WorldRSSFeedConfig
from iskra.memory.protocol import MemoryStore
from iskra.sensors.rss_xml import dedupe_key_item, parse_rss_items

logger = logging.getLogger("iskra.sensors.rss")


def dedupe_file_path(data_dir: str) -> Path:
    return Path(data_dir) / "rss_dedupe.json"


def load_dedupe_keys(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        keys = data.get("keys")
        if isinstance(keys, list):
            return {str(k) for k in keys if isinstance(k, str)}
    except (OSError, ValueError, json.JSONDecodeError) as e:
        logger.warning("rss dedupe: не загрузить %s: %s", path, e)
    return set()


def save_dedupe_keys(path: Path, keys: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lst = sorted(keys)
    path.write_text(json.dumps({"keys": lst}, ensure_ascii=False), encoding="utf-8")


async def refresh_rss_feeds(
    *,
    cfg: WorldRSSConfig,
    data_dir: str,
    memory_store: MemoryStore,
    dedupe_keys: set[str],
    client: httpx.AsyncClient,
    timeout: float = 15.0,
) -> list[str]:
    """Загружает ленты, пишет новые элементы в память. Возвращает строки для world_context."""
    previews: list[str] = []
    dedupe_path = dedupe_file_path(data_dir)

    for feed_cfg in cfg.feeds:
        title_lines = await _poll_one_feed(
            feed_cfg=feed_cfg,
            rss_cfg=cfg,
            memory_store=memory_store,
            dedupe_keys=dedupe_keys,
            client=client,
            timeout=timeout,
        )
        previews.extend(title_lines)

    try:
        save_dedupe_keys(dedupe_path, dedupe_keys)
    except OSError as e:
        logger.warning("rss dedupe: не сохранить %s: %s", dedupe_path, e)

    return previews[-40:]  # не раздувать контекст одним проходом


async def _poll_one_feed(
    *,
    feed_cfg: WorldRSSFeedConfig,
    rss_cfg: WorldRSSConfig,
    memory_store: MemoryStore,
    dedupe_keys: set[str],
    client: httpx.AsyncClient,
    timeout: float,
) -> list[str]:
    out: list[str] = []
    url = feed_cfg.url.strip()
    if not url:
        return out
    try:
        r = await client.get(url, timeout=timeout, follow_redirects=True)
        r.raise_for_status()
        items = parse_rss_items(r.content, max_items=rss_cfg.max_items_per_feed)
    except Exception as e:
        logger.warning("rss: лента %s не загружена: %s", feed_cfg.name, e)
        return out

    cat = feed_cfg.category or rss_cfg.default_category
    imp = rss_cfg.save_importance

    for item in items:
        dk = dedupe_key_item(url, item)
        if dk in dedupe_keys:
            continue
        dedupe_keys.add(dk)
        title = item.get("title") or "(без заголовка)"
        link = item.get("link") or ""
        body = f"[RSS:{feed_cfg.name}] {title}"
        if link:
            body += f"\n{link}"
        mid = memory_store.store(cat, body, imp)
        if mid:
            logger.info("rss: сохранено id=%s feed=%s", mid, feed_cfg.name)
        out.append(f"- {feed_cfg.name}: {title[:120]}")
    return out
