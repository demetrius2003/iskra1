"""Async main loop: tick → trigger → intent → LLM → memory → log."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import yaml

from iskra.core.config import IskraConfig
from iskra.core.intent_generator import Jinja2IntentGenerator
from iskra.core.memory_tags import apply_memory_tags, parse_memory_tags, strip_tag_lines
from iskra.core.state_engine import OUStateEngine
from iskra.core.trigger_engine import DefaultTriggerEngine
from iskra.event_log import EventLog
from iskra.llm import create_llm_adapter
from iskra.llm.protocol import LLMError, LLMNetworkError, LLMRateLimitError, LLMTimeoutError
from iskra.memory import create_memory_store
from iskra.models import EventLogEntry, LLMResponse, SparkEvent
from iskra.output import create_output_channel
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
            mem_ctx = self.memory_store.recall(category=None, n=n, context=None)
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

    def _load_seed_memories(self) -> None:
        path = self.config.memory.initial_memories_file
        if not path:
            return
        p = Path(path)
        if not p.is_file():
            logger.warning("initial_memories_file not found: %s", p)
            return
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
            memories = (data or {}).get("memories", [])
            for m in memories:
                self.memory_store.store(
                    str(m.get("category", "seed")),
                    str(m["content"]),
                    float(m.get("importance", 0.5)),
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

    async def _process_tick(self) -> None:
        now = time.monotonic()
        elapsed = max(0.0, now - self.last_tick_time)
        self.state_engine.tick(elapsed)
        state_before = self.state_engine.snapshot()

        if now < self.cooldown_until:
            self.last_tick_time = time.monotonic()
            return

        if not self.llm_adapter.is_available():
            logger.warning("LLM adapter not available, skipping tick")
            self.last_tick_time = time.monotonic()
            return

        external_text: str | None = self._read_external_input_text()
        if external_text:
            self.state_engine.apply_impulse("user_message")
            logger.info("внешний ввод из файла: %d символов", len(external_text))
        state_before = self.state_engine.snapshot()

        event: SparkEvent | None = None
        try:
            if self._pending_self_reflection:
                self._pending_self_reflection = False
                event = self._make_self_reflection_event(state_before)
            else:
                event = self.trigger_engine.evaluate(state_before)
            if event is None:
                self.last_tick_time = time.monotonic()
                return

            if external_text:
                event = replace(
                    event,
                    metadata={**event.metadata, "external_input": external_text},
                )

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

            tag_ops = parse_memory_tags(response.content)
            if tag_ops:
                apply_memory_tags(
                    self.memory_store,
                    tag_ops,
                    self.config.agency,
                    default_category=event.trigger_type,
                )
            display_content = strip_tag_lines(response.content).strip()
            if not display_content:
                display_content = "…"
            response = replace(response, content=display_content)

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
            state_after = self.state_engine.snapshot()

            imp = _compute_importance(event.trigger_type, response.content)
            mem_id = self.memory_store.store(event.trigger_type, response.content, imp)
            self.memory_store.store("last_context", response.content, 0.9)

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

    async def run(self) -> None:
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
