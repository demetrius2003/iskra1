"""Trigger types registry."""

from iskra.core.config import MemoryConfig, TriggerConfig
from iskra.triggers.continue_context import ContinueContextTrigger
from iskra.triggers.meta_reflection import MetaReflectionTrigger
from iskra.triggers.new_topic import NewTopicTrigger
from iskra.triggers.recall_memory import RecallMemoryTrigger


def create_trigger_types(trigger_cfg: TriggerConfig, memory_cfg: MemoryConfig) -> list:
    """Instantiate trigger implementations for each configured type."""
    out: list = []
    pool = list(trigger_cfg.random_topic_pool)
    for name, tc in trigger_cfg.types.items():
        if name == "new_topic":
            out.append(NewTopicTrigger(tc, pool))
        elif name == "recall_memory":
            out.append(RecallMemoryTrigger(tc, memory_cfg))
        elif name == "continue_context":
            out.append(ContinueContextTrigger(tc))
        elif name == "meta_reflection":
            out.append(MetaReflectionTrigger(tc))
        else:
            raise ValueError(
                f"Unknown trigger type '{name}' — add implementation in triggers/__init__.py"
            )
    return out
