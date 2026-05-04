"""Дашборд HTML, текстовое резюме по JSONL и минимальный webhook (внешний ввод в файл)."""

from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from iskra.event_log_schema import EventLogLineModel, validate_event_log_line_json

logger = logging.getLogger("iskra.experience")

CHART_JS = "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"


def parse_event_timestamp(raw: str) -> datetime:
    s = raw.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def iter_event_log_lines(path: Path) -> Iterator[EventLogLineModel]:
    if not path.is_file():
        return
    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield validate_event_log_line_json(line)
            except Exception as e:
                logger.warning("events.jsonl:%d skip invalid line: %s", lineno, e)


def load_events_last_hours(
    path: Path,
    *,
    hours: float,
    now: datetime | None = None,
) -> list[EventLogLineModel]:
    if hours <= 0:
        raise ValueError("hours must be positive")
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    cutoff = now - timedelta(hours=hours)
    out: list[EventLogLineModel] = []
    for row in iter_event_log_lines(path):
        try:
            ts = parse_event_timestamp(row.timestamp)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
        except Exception:
            continue
        if ts >= cutoff:
            out.append(row)
    out.sort(key=lambda r: r.timestamp)
    return out


def build_daily_summary_text(
    rows: list[EventLogLineModel],
    *,
    window_label: str,
    generated_at: datetime | None = None,
) -> str:
    gen = generated_at or datetime.now(UTC)
    if gen.tzinfo is None:
        gen = gen.replace(tzinfo=UTC)
    lines: list[str] = [
        f"Iskra-1 — резюме событий ({window_label})",
        f"Сформировано: {gen.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"Записей в окне: {len(rows)}",
        "",
    ]
    if not rows:
        lines.append("Нет событий за выбранный период.")
        return "\n".join(lines) + "\n"

    trig = Counter(r.trigger_type or "(пусто)" for r in rows)
    lines.append("Триггеры:")
    for name, n in trig.most_common():
        lines.append(f"  {name}: {n}")
    err_n = sum(1 for r in rows if r.errors)
    tok = [r.llm_tokens for r in rows if r.llm_tokens > 0]
    lines.extend(
        [
            "",
            f"Тиков с ошибками (errors не пустой): {err_n}",
            f"Сумма llm_tokens (где >0): {sum(tok)}",
            f"Среднее llm_tokens (где >0): {sum(tok)/len(tok):.1f}" if tok else "Среднее llm_tokens: —",
        ]
    )
    return "\n".join(lines) + "\n"


def build_dashboard_html(
    rows: list[EventLogLineModel],
    *,
    title: str = "Iskra-1 dashboard",
    chart_cdn_url: str = CHART_JS,
) -> str:
    trig = Counter(r.trigger_type or "—" for r in rows)
    labels_tr = list(trig.keys())
    data_tr = [trig[k] for k in labels_tr]
    if not labels_tr:
        labels_tr = ["—"]
        data_tr = [0]

    # бакеты по часу (UTC) из сырого timestamp
    hourly: Counter[str] = Counter()
    for r in rows:
        try:
            ts = parse_event_timestamp(r.timestamp)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            key = ts.astimezone(UTC).strftime("%Y-%m-%d %H:00")
            hourly[key] += 1
        except Exception:
            continue
    labels_h = sorted(hourly.keys())
    data_h = [hourly[k] for k in labels_h]
    if not labels_h:
        labels_h = ["—"]
        data_h = [0]

    payload = {
        "trigger_labels": labels_tr,
        "trigger_data": data_tr,
        "hour_labels": labels_h,
        "hour_data": data_h,
        "n_events": len(rows),
    }
    json_payload = json.dumps(payload, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{title}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 1rem 2rem; background: #0f1419; color: #e6edf3; }}
    h1 {{ font-weight: 600; }}
    .grid {{ display: grid; gap: 1.5rem; max-width: 1100px; }}
    canvas {{ max-height: 360px; }}
    .muted {{ color: #8b949e; font-size: 0.9rem; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p class="muted">Событий в выборке: <strong>{len(rows)}</strong> · статический отчёт из events.jsonl</p>
  <div class="grid">
    <section><h2>Триггеры</h2><canvas id="chartTriggers"></canvas></section>
    <section><h2>События по часам (UTC)</h2><canvas id="chartHours"></canvas></section>
  </div>
  <script src="{chart_cdn_url}"></script>
  <script>
    const DATA = {json_payload};
    Chart.defaults.color = '#8b949e';
    Chart.defaults.borderColor = '#30363d';
    new Chart(document.getElementById('chartTriggers'), {{
      type: 'bar',
      data: {{
        labels: DATA.trigger_labels,
        datasets: [{{ label: 'События', data: DATA.trigger_data, backgroundColor: '#58a6ff' }}]
      }},
      options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }} }}
    }});
    new Chart(document.getElementById('chartHours'), {{
      type: 'line',
      data: {{
        labels: DATA.hour_labels,
        datasets: [{{ label: 'За час', data: DATA.hour_data, borderColor: '#3fb950', tension: 0.2 }}]
      }},
      options: {{ responsive: true }}
    }});
  </script>
</body>
</html>
"""


def write_dashboard(
    *,
    events_path: Path,
    output_path: Path,
    hours: float = 24.0,
) -> int:
    rows = load_events_last_hours(events_path, hours=hours)
    html = build_dashboard_html(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return len(rows)


def write_daily_summary(
    *,
    events_path: Path,
    output_path: Path,
    hours: float = 24.0,
) -> int:
    rows = load_events_last_hours(events_path, hours=hours)
    text = build_daily_summary_text(rows, window_label=f"последние {hours} ч")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    return len(rows)


class WebhookHTTPRequestHandler(BaseHTTPRequestHandler):
    target_file: Path
    max_body_bytes: int = 65_536

    def log_message(self, format: str, *args: Any) -> None:
        logger.info("%s - %s", self.address_string(), format % args)

    def _send(self, code: int, body: bytes, content_type: str = "text/plain; charset=utf-8") -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/hook"):
            msg = (
                "Iskra webhook: POST JSON {\"text\":\"...\"} или text/plain телом запроса.\n"
                "Только локальная запись UTF-8 в файл внешнего ввода (см. general.external_input_file).\n"
            )
            self._send(HTTPStatus.OK, msg.encode("utf-8"))
            return
        self._send(HTTPStatus.NOT_FOUND, b"not found\n")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path not in ("/", "/hook"):
            self._send(HTTPStatus.NOT_FOUND, b"not found\n")
            return
        length_hdr = self.headers.get("Content-Length")
        try:
            n = int(length_hdr or "0")
        except ValueError:
            self._send(HTTPStatus.BAD_REQUEST, b"bad Content-Length\n")
            return
        if n > self.max_body_bytes:
            self._send(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, b"body too large\n")
            return
        raw = self.rfile.read(n)
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        text: str
        if ctype == "application/json":
            try:
                obj = json.loads(raw.decode("utf-8"))
            except Exception:
                self._send(HTTPStatus.BAD_REQUEST, b"invalid JSON\n")
                return
            if isinstance(obj, dict):
                chunk = obj.get("text") or obj.get("content") or obj.get("message")
                if chunk is None:
                    self._send(HTTPStatus.BAD_REQUEST, b"missing text/content/message\n")
                    return
                text = str(chunk)
            else:
                self._send(HTTPStatus.BAD_REQUEST, b"JSON must be object\n")
                return
        else:
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                self._send(HTTPStatus.BAD_REQUEST, b"utf-8 required\n")
                return

        text = text.strip()
        if not text:
            self._send(HTTPStatus.BAD_REQUEST, b"empty body\n")
            return

        try:
            self.target_file.parent.mkdir(parents=True, exist_ok=True)
            self.target_file.write_text(text, encoding="utf-8")
        except OSError as e:
            logger.warning("webhook write failed: %s", e)
            self._send(HTTPStatus.INTERNAL_SERVER_ERROR, str(e).encode("utf-8"))
            return

        self._send(HTTPStatus.OK, b"ok\n")


def run_webhook_server(
    *,
    target_file: Path,
    host: str,
    port: int,
    max_body_bytes: int = 65_536,
) -> None:
    """Блокирующий цикл до Ctrl+C. Не использовать на открытом интернете без TLS и авторизации."""

    class Handler(WebhookHTTPRequestHandler):
        pass

    Handler.target_file = target_file
    Handler.max_body_bytes = max_body_bytes

    server = HTTPServer((host, port), Handler)
    logger.info(
        "webhook слушает http://%s:%s → записывает UTF-8 в %s",
        host,
        port,
        target_file,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("webhook остановлен")
    finally:
        server.server_close()
