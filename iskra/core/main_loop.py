"""Async main loop: tick → trigger → intent → LLM → memory → log."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sys
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import yaml

from iskra.core.config import IskraConfig
from iskra.core.emotion_classifier import EmotionClassifier
from iskra.core.intent_generator import Jinja2IntentGenerator
from iskra.core.memory_tags import (
    apply_memory_tags,
    parse_memory_tags,
    parse_web_search_queries,
    strip_tag_lines,
)
from iskra.core.sandbox_tags import apply_sandbox_tags, parse_sandbox_tags
from iskra.core.state_engine import OUStateEngine
from iskra.core.trigger_engine import DefaultTriggerEngine
from iskra.event_log import EventLog
from iskra.llm import create_llm_adapter
from iskra.llm.protocol import LLMError, LLMNetworkError, LLMRateLimitError, LLMTimeoutError
from iskra.memory import create_memory_store
from iskra.models import EventLogEntry, LLMResponse, SparkEvent
from iskra.output import create_output_channel
from iskra.sandbox import SandboxManager
from iskra.sensors.world_poll import WorldRuntimeState, poll_world_sensors
from iskra.triggers import create_trigger_types

logger = logging.getLogger("iskra.core.main_loop")


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _compute_importance(trigger_type: str, content: str) -> float:
    base = 0.5
    if len(content) > 300:
        base += 0.1
    if "?" in content:
        base += 0.1
    if trigger_type in ("meta_reflection", "self_reflection"):
        base += 0.15
    return min(1.0, base)


class MainLoop:
    def __init__(self, config: IskraConfig) -> None:
        self.config = config
        self.running = False
        self.tick_count = 0
        self.last_tick_time = 0.0
        self.cooldown_until: float = 0.0
        self._thought_count = 0
        self._successful_ticks = 0
        self._pending_self_reflection = False

        Path(config.general.data_dir).mkdir(parents=True, exist_ok=True)

        self.state_engine = OUStateEngine(config.state)
        self.memory_store = create_memory_store(config.memory)
        self.trigger_types = create_trigger_types(config.trigger, config.memory)
        self.trigger_engine = DefaultTriggerEngine(
            config.trigger,
            self.trigger_types,
            self.memory_store,
            config.general.tick_jitter,
        )
        self.intent_generator = Jinja2IntentGenerator(config.intent)
        self.llm_adapter = create_llm_adapter(config.llm)
        self.output_channel = create_output_channel(config.output)
        self.event_log = EventLog(config.logging.event_log)
        ecfg = config.emotion_classifier
        lf_raw = ecfg.lexicon_file
        lc_raw = ecfg.lexicon_custom_file
        lf_clean = lf_raw.strip() if isinstance(lf_raw, str) and lf_raw.strip() else None
        lc_clean = lc_raw.strip() if isinstance(lc_raw, str) and lc_raw.strip() else None
        self._emotion = EmotionClassifier.from_lexicon_sources(
            lf_clean,
            lexicon_custom_file=lc_clean,
        )
        self._emotion_max_chars = ecfg.max_input_chars
        self._web_search_hour_times: list[float] = []
        self._ws_tick_remaining = 0

        self._world_runtime = WorldRuntimeState()
        if config.world.rss.enabled:
            self._world_runtime.init_rss_dedupe(config.general.data_dir)

        self._sandbox_manager: SandboxManager | None = None
        if config.sandbox.enabled:
            self._sandbox_manager = SandboxManager(config.sandbox)
            self._sandbox_manager.ensure_root()

    async def _poll_world_context(self, monotonic_now: float) -> str:
        w = self.config.world
        if not (w.time_sensor.enabled or w.weather.enabled or w.rss.enabled):
            return ""
        async with httpx.AsyncClient() as client:
            return await poll_world_sensors(
                cfg=self.config,
                state_engine=self.state_engine,
                memory_store=self.memory_store,
                runtime=self._world_runtime,
                monotonic_now=monotonic_now,
                client=client,
            )

    def _write_pid_file(self) -> None:
        pid_path = Path(self.config.general.pid_file)
        pid_path.parent.mkdir(parents=True, exist_ok=True)
        if pid_path.is_file():
            try:
                old = int(pid_path.read_text(encoding="utf-8").strip())
            except ValueError:
                old = -1
            if old > 0 and _pid_alive(old):
                print(f"Already running (PID: {old})", file=sys.stderr)
                sys.exit(1)
        pid_path.write_text(str(os.getpid()), encoding="utf-8")

    def _remove_pid_file(self) -> None:
        pid_path = Path(self.config.general.pid_file)
        try:
            pid_path.unlink(missing_ok=True)
        except OSError:
            pass

    def _read_external_input_text(self) -> str | None:
        """Текст из ``general.external_input_file`` или None (нет файла, пусто, ошибка)."""
        p = self.config.general.external_input_file
        if not p:
            return None
        path = Path(p)
        if not path.is_file():
            return None
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("external input: не прочитать %s: %s", path, e)
            return None
        text = raw.strip()
        if not text:
            return None
        max_c = self.config.general.external_input_max_chars
        if len(text) > max_c:
            logger.warning("external input: обрезано до %d символов", max_c)
            text = text[:max_c]
        return text

    def _clear_external_input_file(self) -> None:
        p = self.config.general.external_input_file
        if not p or not self.config.general.external_input_clear_after_use:
            return
        path = Path(p)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
        except OSError as e:
            logger.warning("external input: не очистить %s: %s", path, e)

    def _make_self_reflection_event(self, state_before: dict[str, float]) -> SparkEvent:
        n = self.config.general.self_reflection_recall_n
        try:
            mem_ctx = self.memory_store.recall(
                category=None, n=n, context=None, state=state_before
            )
        except Exception as e:
            logger.warning("self_reflection recall failed: %s", e)
            mem_ctx = []
        return SparkEvent(
            id=str(uuid4()),
            trigger_type="self_reflection",
            state_snapshot=dict(state_before),
            memory_context=mem_ctx,
            timestamp=datetime.now(UTC),
            metadata={},
        )

    def _seed_marker_path(self) -> Path:
        return Path(self.config.general.data_dir).resolve() / ".iskra_seed_marker.json"

    def _load_seed_memories(self) -> None:
        path = self.config.memory.initial_memories_file
        if not path:
            return
        p = Path(path)
        if not p.is_file():
            logger.warning("initial_memories_file not found: %s", p)
            return
        p = p.resolve()
        try:
            raw_bytes = p.read_bytes()
        except OSError as e:
            logger.warning("seed memories: не прочитать %s: %s", p, e)
            return
        fingerprint = hashlib.sha256(raw_bytes).hexdigest()
        marker_path = self._seed_marker_path()
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        if marker_path.is_file():
            try:
                meta = json.loads(marker_path.read_text(encoding="utf-8"))
                if meta.get("seed_path") == str(p) and meta.get("sha256") == fingerprint:
                    logger.info("seed memories уже применены (маркер), пропуск")
                    return
            except (OSError, ValueError, json.JSONDecodeError):
                pass
        try:
            data = yaml.safe_load(raw_bytes.decode("utf-8"))
            memories = (data or {}).get("memories", [])
            for m in memories:
                ev = float(m.get("emotional_valence", 0.0))
                ar = float(m.get("arousal", 0.5))
                self.memory_store.store(
                    str(m.get("category", "seed")),
                    str(m["content"]),
                    float(m.get("importance", 0.5)),
                    emotional_valence=ev,
                    arousal=ar,
                )
            marker_path.write_text(
                json.dumps({"seed_path": str(p), "sha256": fingerprint}, indent=2),
                encoding="utf-8",
            )
            logger.info("loaded %d seed memories", len(memories))
        except Exception as e:
            logger.warning("seed memories load failed: %s", e)

    async def _llm_complete_with_retry(
        self, system_prompt: str, user_prompt: str
    ) -> LLMResponse | None:
        cfg = self.config.llm
        last_err: Exception | None = None
        for attempt in range(cfg.retry.max_attempts):
            try:
                resp = await self.llm_adapter.complete(system_prompt, user_prompt)
                return resp
            except LLMRateLimitError as e:
                self.cooldown_until = time.monotonic() + float(cfg.cooldown_on_rate_limit_seconds)
                logger.warning("LLM rate limit: %s", e)
                return None
            except (LLMTimeoutError, LLMNetworkError) as e:
                last_err = e
                if attempt >= cfg.retry.max_attempts - 1:
                    logger.warning("LLM failed after retries: %s", e)
                    return None
                delay = cfg.retry.backoff_base_seconds * (2**attempt)
                await asyncio.sleep(delay)
            except LLMError as e:
                logger.warning("LLM error: %s", e)
                return None
        if last_err:
            logger.warning("LLM failed: %s", last_err)
        return None

    async def _flush_web_searches(self, queries: list[str]) -> tuple[list[str], str | None]:
        ws = self.config.tools.web_search
        if not ws.enabled or ws.max_per_tick <= 0:
            return [], None

        from iskra.tools.web_search import fetch_duckduckgo_snippets, summarize_snippets

        seen: set[str] = set()
        uniq: list[str] = []
        for q in queries:
            key = q.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            uniq.append(q.strip())

        now_wall = time.time()
        self._web_search_hour_times = [
            t for t in self._web_search_hour_times if now_wall - t < 3600.0
        ]

        summaries: list[str] = []
        last_mid: str | None = None
        for q in uniq:
            if self._ws_tick_remaining <= 0:
                logger.info("web_search: достигнут лимит max_per_tick на этот тик")
                break
            if ws.max_per_hour > 0 and len(self._web_search_hour_times) >= ws.max_per_hour:
                logger.info("web_search: достигнут лимит max_per_hour (скользящий час)")
                break

            try:
                snippets = fetch_duckduckgo_snippets(q, max_results=ws.max_results)
            except ImportError:
                logger.warning(
                    'web_search: установите duckduckgo-search (pip install duckduckgo-search или '
                    'из корня репозитория pip install ".[web]"; pip install iskra[web] с PyPI — другой пакет)'
                )
                break
            except Exception as e:
                logger.warning("web_search: ошибка DuckDuckGo %s", e)
                continue

            if ws.log_snippet_count:
                logger.info(
                    "web_search: запрос=%r сниппетов от поиска=%d",
                    q[:200],
                    len(snippets),
                )
            if ws.log_snippet_previews:
                lim = ws.log_snippet_preview_chars
                cap = ws.log_snippet_preview_limit
                if snippets:
                    shown = snippets[:cap]
                    for i, raw in enumerate(shown, 1):
                        one = " ".join(raw.split())
                        if len(one) > lim:
                            one = one[: lim - 1] + "…"
                        logger.info(
                            "web_search: сниппет %d/%d: %s",
                            i,
                            len(snippets),
                            one,
                        )
                    if len(snippets) > cap:
                        logger.info(
                            "web_search: превью только первых %d из %d сниппетов "
                            "(tools.web_search.log_snippet_preview_limit)",
                            cap,
                            len(snippets),
                        )
                else:
                    logger.info(
                        "web_search: сниппетов нет (пустой ответ поиска); сводка будет заглушкой"
                    )

            try:
                summary = await summarize_snippets(
                    self.llm_adapter,
                    q,
                    snippets,
                    summary_max_tokens=ws.summary_max_tokens,
                )
            except Exception as e:
                logger.warning("web_search: сводка через LLM не удалась %s", e)
                continue

            lp = ws.log_summary_preview_chars
            if lp is not None and summary:
                flat = " ".join(summary.split())
                tail = "…" if len(flat) > lp else ""
                logger.info("web_search: превью сводки (%d симв. max): %s%s", lp, flat[:lp], tail)

            cls_v, cls_a = self._emotion.classify(summary, max_chars=self._emotion_max_chars)
            body = f"[Источник: веб-поиск по запросу «{q}»]\n\n{summary}"
            mid = self.memory_store.store(
                ws.memory_category,
                body,
                ws.memory_importance,
                emotional_valence=cls_v,
                arousal=cls_a,
            )
            if mid:
                last_mid = mid
            logger.info(
                "web_search: сохранено category=%s id=%s query=%r",
                ws.memory_category,
                mid,
                q[:120],
            )
            self._web_search_hour_times.append(time.time())
            self._ws_tick_remaining -= 1
            summaries.append(summary)

        return summaries, last_mid

    async def _tick_external_web_search_only(
        self, state_before: dict[str, float], queries: list[str]
    ) -> None:
        summaries, last_mid = await self._flush_web_searches(queries)
        self._clear_external_input_file()
        blob = "\n\n".join(summaries) if summaries else "(нет результатов)"
        eid = str(uuid4())
        try:
            await self.output_channel.emit(
                eid,
                blob,
                "web_search",
                state_before,
                datetime.now(UTC),
            )
        except Exception as e:
            logger.warning("output emit failed: %s", e)
            print(blob, file=sys.stdout)

        ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        state_after = self.state_engine.snapshot()
        resp_trim = blob if len(blob) <= 8000 else blob[:7997] + "..."
        self.event_log.record(
            EventLogEntry(
                event_id=eid,
                timestamp=ts,
                trigger_type="web_search",
                state_before=state_before,
                state_after=state_after,
                memory_ids_recalled=[],
                prompt_system="",
                prompt_user="\n".join(queries),
                llm_response=resp_trim,
                llm_model=self.config.llm.adapter,
                llm_tokens=0,
                llm_latency_ms=0,
                memory_id_stored=last_mid or None,
                output_channel=getattr(self.output_channel, "name", "unknown"),
                errors=[],
            )
        )
        self._thought_count += 1
        logger.info("web_search-only tick #%d queries=%s", self._thought_count, queries)

    async def _dry_run_tick(self) -> None:
        """Один проход: триггер и промпты в лог; без вызова LLM и без записи в память / JSONL."""
        now = time.monotonic()
        elapsed = max(0.0, now - self.last_tick_time)
        self.state_engine.tick(elapsed)
        world_ctx_str = await self._poll_world_context(now)
        state_before = self.state_engine.snapshot()

        external_text: str | None = self._read_external_input_text()
        clean_ext = strip_tag_lines(external_text).strip() if external_text else ""
        if external_text:
            self.state_engine.apply_impulse("user_message")
            logger.info("dry-run | внешний ввод: %d символов", len(external_text))
            state_before = self.state_engine.snapshot()

        event: SparkEvent | None = None
        try:
            if self._pending_self_reflection:
                self._pending_self_reflection = False
                event = self._make_self_reflection_event(state_before)
            else:
                event = self.trigger_engine.evaluate(state_before)
            if event is None:
                logger.info("dry-run | триггер не выбран (evaluate → None)")
                return

            md = {
                **(event.metadata or {}),
                "world_context": world_ctx_str,
                "sandbox_tools_available": self._sandbox_manager is not None,
                "agency_level": self.config.agency.level,
                "web_search_enabled": self.config.tools.web_search.enabled,
            }
            if external_text:
                md["external_input"] = clean_ext
            event = replace(event, metadata=md)

            intent = self.intent_generator.generate(event)
            recalled_ids = [m.id for m in event.memory_context if m.id]

            logger.info("dry-run | trigger=%s event_id=%s", event.trigger_type, event.id)
            logger.info(
                "dry-run | memory_ids_recalled (%d): %s",
                len(recalled_ids),
                recalled_ids[:24],
            )
            logger.info(
                "dry-run | system_prompt (%d chars)\n%s",
                len(intent.system_prompt),
                intent.system_prompt[:4000],
            )
            logger.info(
                "dry-run | user_prompt (%d chars)\n%s",
                len(intent.user_prompt),
                intent.user_prompt[:4000],
            )

            probe = "[DRY-RUN] синтетический маркер"
            cls_v, cls_a = self._emotion.classify(probe, max_chars=self._emotion_max_chars)
            counts = self._emotion.lexicon_counts()
            logger.info(
                "dry-run | lexicon: pos=%d neg=%d arousal_words=%d distinct_tokens=%d",
                counts["positive_words"],
                counts["negative_words"],
                counts["high_arousal_words"],
                counts["distinct_tokens"],
            )
            logger.info(
                "dry-run | classify(%r): valence=%.3f arousal=%.3f",
                probe,
                cls_v,
                cls_a,
            )
            logger.info(
                "dry-run | готово: LLM не вызывался; память и events.jsonl не изменялись"
            )
        except Exception:
            logger.exception("dry-run | ошибка")
        finally:
            self.last_tick_time = time.monotonic()
            self.tick_count += 1

    async def _process_tick(self) -> None:
        now = time.monotonic()
        elapsed = max(0.0, now - self.last_tick_time)
        self.state_engine.tick(elapsed)

        world_ctx_str = await self._poll_world_context(now)

        if now < self.cooldown_until:
            self.last_tick_time = time.monotonic()
            return

        if not self.llm_adapter.is_available():
            logger.warning("LLM adapter not available, skipping tick")
            self.last_tick_time = time.monotonic()
            return

        ws_cfg = self.config.tools.web_search
        if ws_cfg.enabled and ws_cfg.max_per_tick > 0:
            self._ws_tick_remaining = ws_cfg.max_per_tick
        else:
            self._ws_tick_remaining = 0

        external_text: str | None = self._read_external_input_text()
        ext_queries_pre: list[str] = []
        if external_text and ws_cfg.enabled and ws_cfg.max_per_tick > 0:
            ext_queries_pre = parse_web_search_queries(external_text)
        clean_ext = strip_tag_lines(external_text).strip() if external_text else ""

        if external_text:
            self.state_engine.apply_impulse("user_message")
            logger.info("внешний ввод из файла: %d символов", len(external_text))
        state_before = self.state_engine.snapshot()

        event: SparkEvent | None = None
        try:
            short_circuit = (
                ws_cfg.enabled
                and ws_cfg.max_per_tick > 0
                and external_text is not None
                and bool(ext_queries_pre)
                and not clean_ext
            )
            if short_circuit:
                await self._tick_external_web_search_only(state_before, ext_queries_pre)
                return

            if ext_queries_pre and ws_cfg.enabled:
                await self._flush_web_searches(ext_queries_pre)

            if self._pending_self_reflection:
                self._pending_self_reflection = False
                event = self._make_self_reflection_event(state_before)
            else:
                event = self.trigger_engine.evaluate(state_before)
            if event is None:
                self.last_tick_time = time.monotonic()
                return

            md = {
                **(event.metadata or {}),
                "world_context": world_ctx_str,
                "sandbox_tools_available": self._sandbox_manager is not None,
                "agency_level": self.config.agency.level,
                "web_search_enabled": self.config.tools.web_search.enabled,
            }
            if external_text:
                md["external_input"] = clean_ext
            event = replace(event, metadata=md)

            intent = self.intent_generator.generate(event)

            if hasattr(self.llm_adapter, "prepare_tick"):
                self.llm_adapter.prepare_tick(event.trigger_type)

            response = await self._llm_complete_with_retry(
                intent.system_prompt, intent.user_prompt
            )
            if response is None:
                self.event_log.record_error(event.id, "llm_complete_failed")
                self.last_tick_time = time.monotonic()
                return

            response = replace(response, event_id=event.id)

            raw_llm = response.content
            tag_ops = parse_memory_tags(raw_llm)
            ws_post = parse_web_search_queries(raw_llm)
            if tag_ops:
                apply_memory_tags(
                    self.memory_store,
                    tag_ops,
                    self.config.agency,
                    default_category=event.trigger_type,
                )
            if self._sandbox_manager:
                sb_ops = parse_sandbox_tags(raw_llm)
                if sb_ops:
                    await apply_sandbox_tags(
                        sb_ops,
                        manager=self._sandbox_manager,
                        memory_store=self.memory_store,
                        max_ops=self.config.sandbox.max_tag_ops_per_tick,
                    )
            if ws_post:
                await self._flush_web_searches(ws_post)

            display_content = strip_tag_lines(raw_llm).strip()
            if not display_content:
                display_content = "…"
            response = replace(response, content=display_content)
            cls_v, cls_a = self._emotion.classify(
                display_content, max_chars=self._emotion_max_chars
            )

            try:
                await self.output_channel.emit(
                    event.id,
                    response.content,
                    event.trigger_type,
                    state_before,
                    response.timestamp,
                )
            except Exception as e:
                logger.warning("output emit failed: %s", e)
                print(response.content, file=sys.stdout)

            self.state_engine.apply_feedback(event.trigger_type, response.content)
            ecfg = self.config.emotion_classifier
            self.state_engine.blend_emotion_toward_sample(
                cls_v,
                cls_a,
                valence_blend=ecfg.valence_blend,
                arousal_blend=ecfg.arousal_blend,
            )
            state_after = self.state_engine.snapshot()

            insight_cfg = self.config.general.self_reflection_insight
            if event.trigger_type == "self_reflection" and insight_cfg.enabled:
                store_cat = insight_cfg.category
                imp_ins = insight_cfg.importance
            else:
                store_cat = event.trigger_type
                imp_ins = _compute_importance(event.trigger_type, response.content)

            mem_id = self.memory_store.store(
                store_cat,
                response.content,
                imp_ins,
                emotional_valence=cls_v,
                arousal=cls_a,
            )
            self.memory_store.store(
                "last_context",
                response.content,
                0.9,
                emotional_valence=cls_v,
                arousal=cls_a,
            )

            self._successful_ticks += 1
            if self._successful_ticks % self.config.general.decay_every_n_ticks == 0:
                self.memory_store.decay()
            c_every = self.config.general.consolidation_every_n_ticks
            if c_every and self._successful_ticks % c_every == 0:
                self.memory_store.consolidate()
            sr_every = self.config.general.self_reflection_every_n_ticks
            if sr_every and self._successful_ticks % sr_every == 0:
                self._pending_self_reflection = True

            mem_recalled_ids = [m.id for m in event.memory_context if m.id]
            ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            self.event_log.record(
                EventLogEntry(
                    event_id=event.id,
                    timestamp=ts,
                    trigger_type=event.trigger_type,
                    state_before=state_before,
                    state_after=state_after,
                    memory_ids_recalled=mem_recalled_ids,
                    prompt_system=intent.system_prompt,
                    prompt_user=intent.user_prompt,
                    llm_response=response.content,
                    llm_model=response.model,
                    llm_tokens=response.tokens_used,
                    llm_latency_ms=response.latency_ms,
                    memory_id_stored=mem_id or None,
                    output_channel=getattr(self.output_channel, "name", "unknown"),
                    errors=[],
                )
            )

            if external_text:
                self._clear_external_input_file()

            self._thought_count += 1
            logger.info(
                "thought #%d trigger=%s model=%s",
                self._thought_count,
                event.trigger_type,
                response.model,
            )

        except Exception as e:
            logger.exception("tick error: %s", e)
            eid = event.id if event else "unknown"
            self.event_log.record_error(eid, str(e))
        finally:
            self.last_tick_time = time.monotonic()
            self.tick_count += 1

    async def run(self, *, dry_run: bool = False) -> None:
        if dry_run:
            logger.info(
                "режим dry-run: один проход без предстарта, PID, загрузки seed и основного цикла"
            )
            self.state_engine.apply_impulse("system_startup")
            self.last_tick_time = time.monotonic() - 86_400.0
            await self._dry_run_tick()
            return

        if self.config.general.preflight:
            from iskra.core.preflight import preflight

            await preflight(self)
        self._write_pid_file()
        self._load_seed_memories()
        self.state_engine.apply_impulse("system_startup")
        self.running = True
        self.last_tick_time = time.monotonic()

        interval = self.trigger_engine.next_interval(self.state_engine.snapshot())
        logger.info("Iskra-1 запущена. Первый тик через %.0f секунд.", interval)

        try:
            while self.running:
                await asyncio.sleep(interval)
                await self._process_tick()
                interval = self.trigger_engine.next_interval(self.state_engine.snapshot())
        except asyncio.CancelledError:
            logger.info("shutdown requested")
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        self.running = False
        self._remove_pid_file()
        logger.info("Iskra-1 остановлена.")

    def stop(self) -> None:
        self.running = False
