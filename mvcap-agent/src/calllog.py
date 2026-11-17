"""The record of one call: caller ID, what they asked for, how it ended, how long it took.

The agent notes facts as the call goes, then writes one row to public.calls when the call ends.
Nothing the caller said is stored, only the keyword or person the agent matched.
A failed write is logged and never affects the call.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from supabase_client import get_supabase

logger = logging.getLogger("mvcap-agent")


@dataclass
class CallLog:
    caller_id: str | None
    room_name: str
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    request_type: str = "none"
    keywords: list[str] = field(default_factory=list)
    people: list[str] = field(default_factory=list)
    outcome: str = "caller_hung_up"
    transfer_target: str | None = None

    def keyword(self, keyword: str) -> None:
        if keyword not in self.keywords:
            self.keywords.append(keyword)
        if self.request_type == "none":
            self.request_type = "keyword"

    def person(self, name: str) -> None:
        if name not in self.people:
            self.people.append(name)
        if self.request_type == "none":
            self.request_type = "directory"

    def finish(self, outcome: str, target: str | None = None) -> None:
        self.outcome = outcome
        if target:
            self.transfer_target = target

    def row(self, ended_at: datetime | None = None) -> dict:
        ended_at = ended_at or datetime.now(UTC)
        return {
            "started_at": self.started_at.isoformat(),
            "ended_at": ended_at.isoformat(),
            "duration_seconds": max(
                0, round((ended_at - self.started_at).total_seconds())
            ),
            "caller_id": self.caller_id,
            "request_type": self.request_type,
            "keywords": self.keywords,
            "people": self.people,
            "outcome": self.outcome,
            "transfer_target": self.transfer_target,
            "room_name": self.room_name,
        }

    async def save(self) -> None:
        row = self.row()
        try:
            await asyncio.to_thread(
                lambda: get_supabase().table("calls").insert(row).execute()
            )
            logger.info(
                "call logged: %s", {k: row[k] for k in ("request_type", "outcome")}
            )
        except Exception:
            logger.exception("could not save the call record")
