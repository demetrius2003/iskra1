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
        try:
            sys_t = jinja2.Template(self._cfg.system_prompt_template)
            system_prompt = sys_t.render(state=state)
        except jinja2.TemplateError as e:
            logger.error("system template error: %s", e)
            raise

        trigger = event.trigger_type
        tmpl_str = self._cfg.user_prompts.get(trigger, self._cfg.user_prompts["default"])
        if trigger not in self._cfg.user_prompts:
            logger.warning("missing user_prompt for %s, using default", trigger)

        context_string = self._context_string(event)
        try:
            user_t = jinja2.Template(tmpl_str)
            user_prompt = user_t.render(
                context=context_string,
                memories=[m.content for m in event.memory_context],
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
        if mc:
            return mc[0].content
        return ""
