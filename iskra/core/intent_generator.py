"""Jinja2-based intent / prompt generation."""

from __future__ import annotations

import logging

import jinja2

from iskra.core.config import IntentConfig
from iskra.models import IntentPayload, SparkEvent

logger = logging.getLogger("iskra.core.intent")


class Jinja2IntentGenerator:
    def __init__(self, config: IntentConfig) -> None:
        self._cfg = config

    def generate(self, event: SparkEvent) -> IntentPayload:
        state = event.state_snapshot
        ext = (event.metadata or {}).get("external_input") or ""
        if not isinstance(ext, str):
            ext = str(ext)

        world_ctx = (event.metadata or {}).get("world_context") or ""
        if not isinstance(world_ctx, str):
            world_ctx = str(world_ctx)

        sandbox_tools_available = bool(
            (event.metadata or {}).get("sandbox_tools_available")
        )
        _meta = event.metadata or {}
        agency_level = _meta.get("agency_level")
        if agency_level is not None:
            agency_level = int(agency_level)
        web_search_enabled = bool(_meta.get("web_search_enabled", True))

        try:
            sys_t = jinja2.Template(self._cfg.system_prompt_template)
            system_prompt = sys_t.render(
                state=state,
                external_input=ext,
                world_context=world_ctx,
                sandbox_tools_available=sandbox_tools_available,
                agency_level=agency_level,
                web_search_enabled=web_search_enabled,
            )
        except jinja2.TemplateError as e:
            logger.error("system template error: %s", e)
            raise

        trigger = event.trigger_type
        tmpl_str = self._cfg.user_prompts.get(trigger, self._cfg.user_prompts["default"])
        if trigger not in self._cfg.user_prompts:
            logger.warning("missing user_prompt for %s, using default", trigger)

        context_string = self._context_string(event)
        memory_lines = [
            f"{m.content} [эмоции записи: valence={m.emotional_valence:.2f}, arousal={m.arousal:.2f}]"
            for m in event.memory_context
        ]
        try:
            user_t = jinja2.Template(tmpl_str)
            user_prompt = user_t.render(
                context=context_string,
                memories=[m.content for m in event.memory_context],
                memory_lines=memory_lines,
                external_input=ext,
                world_context=world_ctx,
                sandbox_tools_available=sandbox_tools_available,
                agency_level=agency_level,
                web_search_enabled=web_search_enabled,
            )
        except jinja2.TemplateError as e:
            logger.error("user template error: %s", e)
            raise

        return IntentPayload(
            event_id=event.id,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            trigger_type=trigger,
            timestamp=event.timestamp,
        )

    def _context_string(self, event: SparkEvent) -> str:
        mc = event.memory_context
        tt = event.trigger_type
        if tt == "new_topic" and mc:
            return mc[0].content
        if tt == "recall_memory" and mc:
            return mc[0].content
        if tt == "continue_context" and mc:
            return mc[0].content
        if tt == "meta_reflection":
            return ""
        if tt == "self_reflection":
            return ""
        if mc:
            return mc[0].content
        return ""
