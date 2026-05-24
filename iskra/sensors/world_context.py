"""Строка world_context для Jinja (время, погода, свежие RSS)."""

from __future__ import annotations

from iskra.sensors.time_sensor import slot_display_name_ru


def build_world_context_text(
    *,
    slot_name: str,
    weather_line: str,
    rss_lines: list[str],
    max_chars: int,
) -> str:
    lines: list[str] = []
    lines.append(f"Мир (сенсоры): время суток — {slot_display_name_ru(slot_name)}.")
    if weather_line:
        lines.append(weather_line)
    else:
        lines.append("Погода: данных нет или сервис выключен.")
    if rss_lines:
        lines.append("Свежие заголовки (последний опрос RSS):")
        lines.extend(rss_lines)
    else:
        lines.append("RSS: новых заголовков в этом проходе нет или ленты выключены.")

    text = "\n".join(lines).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 12].rstrip() + "\n[… обрезано]"

