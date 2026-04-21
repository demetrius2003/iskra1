"""Output channel protocol."""

from datetime import datetime
from typing import Protocol

from iskra.models import StateSnapshot


class OutputChannel(Protocol):
    name: str

    async def emit(
        self,
        event_id: str,
        thought: str,
        trigger_type: str,
        state_snapshot: StateSnapshot,
        timestamp: datetime,
    ) -> None: ...
