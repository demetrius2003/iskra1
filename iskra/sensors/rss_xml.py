"""Минимальный разбор RSS 2.0 (без обязательного feedparser)."""

from __future__ import annotations

import hashlib
import logging
import xml.etree.ElementTree as ET

logger = logging.getLogger("iskra.sensors.rss_xml")


def _strip_ns(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def parse_rss_items(xml_bytes: bytes, *, max_items: int) -> list[dict[str, str]]:
    """Возвращает списки с ключами title, link, guid (строки могут быть пустыми)."""
    out: list[dict[str, str]] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        logger.warning("rss: XML parse error: %s", e)
        return []

    root_tag = _strip_ns(root.tag).lower()
    if root_tag == "rss":
        channel = root.find("channel")
        if channel is None:
            return []
        for item in channel.findall("item"):
            if len(out) >= max_items:
                break
            title_el = item.find("title")
            link_el = item.find("link")
            guid_el = item.find("guid")
            title = (title_el.text or "").strip() if title_el is not None and title_el.text else ""
            link = (link_el.text or "").strip() if link_el is not None and link_el.text else ""
            guid = (guid_el.text or "").strip() if guid_el is not None and guid_el.text else ""
            out.append({"title": title, "link": link, "guid": guid})
        return out

    # Atom (упрощённо)
    if root_tag == "feed":
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns)
        if not entries:
            entries = root.findall("{http://www.w3.org/2005/Atom}entry")
        for ent in entries:
            if len(out) >= max_items:
                break
            title_el = ent.find("atom:title", ns) or ent.find("{http://www.w3.org/2005/Atom}title")
            id_el = ent.find("atom:id", ns) or ent.find("{http://www.w3.org/2005/Atom}id")
            link_el = ent.find("atom:link", ns) or ent.find("{http://www.w3.org/2005/Atom}link")
            title = (title_el.text or "").strip() if title_el is not None and title_el.text else ""
            guid = (id_el.text or "").strip() if id_el is not None and id_el.text else ""
            link = ""
            if link_el is not None:
                link = (link_el.get("href") or "").strip()
            out.append({"title": title, "link": link, "guid": guid})
        return out

    logger.warning("rss: неизвестный корень %s", root_tag)
    return []


def dedupe_key_item(feed_url: str, item: dict[str, str]) -> str:
    link = item.get("link") or ""
    if link:
        return f"link:{link}"
    guid = item.get("guid") or ""
    if guid:
        return f"guid:{guid}"
    title = item.get("title") or ""
    h = hashlib.sha256(f"{feed_url}\n{title}".encode("utf-8")).hexdigest()
    return f"hash:{h}"
