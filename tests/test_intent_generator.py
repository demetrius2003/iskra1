"""Intent generator: trigger-specific Jinja context."""

from __future__ import annotations

from datetime import UTC, datetime

from iskra.core.config import IntentConfig
from iskra.core.intent_generator import Jinja2IntentGenerator
from iskra.models import MemoryRecord, SparkEvent


def test_self_reflection_renders_memories_list() -> None:
    gen = Jinja2IntentGenerator(
        IntentConfig(
            system_prompt_template="S: {{ state.curiosity }}",
            user_prompts={
                "default": "d",
                "self_reflection": "{% for m in memories %}[{{ m }}]{% endfor %}",
            },
        )
    )
    now = datetime.now(UTC)
    recs = [
        MemoryRecord(
            id="a",
            timestamp=now,
            category="x",
            content="one",
            importance=0.5,
            last_recall=now,
            recall_count=0,
            decay_rate=0.01,
        ),
        MemoryRecord(
            id="b",
            timestamp=now,
            category="y",
            content="two",
            importance=0.5,
            last_recall=now,
            recall_count=0,
            decay_rate=0.01,
        ),
    ]
    event = SparkEvent(
        trigger_type="self_reflection",
        state_snapshot={"curiosity": 0.3},
        memory_context=recs,
        timestamp=now,
    )
    payload = gen.generate(event)
    assert "[one][two]" in payload.user_prompt
