"""
Channel adapter interface.

Every channel implements `send(recipient, content) -> ChannelSendResult`.
The router and saga only ever talk to this interface — they don't know or
care whether SMS is backed by a mock, MSG91, or Twilio. This is what makes
the Saga's retry/fallback logic channel-agnostic: it just calls
`channel.send(...)` and inspects `.success`.

All adapters in this repo are MOCKS that simulate realistic latency and a
configurable failure rate, so the demo can exercise retries and DLQ
behaviour without needing live SMS/email/push credentials. Swapping a mock
for a real provider means implementing this interface once per provider —
no other module changes.
"""

from __future__ import annotations

import abc
import random
from dataclasses import dataclass


@dataclass
class ChannelSendResult:
    success: bool
    provider_message_id: str | None = None
    error: str | None = None
    latency_ms: int = 0


class ChannelAdapter(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    async def send(self, recipient: str, content: str | dict) -> ChannelSendResult: ...


class SimulatedFailureMixin:
    """Shared mock behaviour: random latency + configurable failure rate,
    so different channels can have different realistic reliability profiles
    (e.g. push notifications drop more often than SMS in the real world)."""

    failure_rate: float = 0.0
    min_latency_ms: int = 50
    max_latency_ms: int = 400

    async def _simulate(self, provider_prefix: str) -> ChannelSendResult:
        import asyncio
        import uuid

        latency = random.randint(self.min_latency_ms, self.max_latency_ms)
        await asyncio.sleep(latency / 1000.0)

        if random.random() < self.failure_rate:
            return ChannelSendResult(
                success=False,
                error=f"{provider_prefix}_PROVIDER_TIMEOUT",
                latency_ms=latency,
            )

        return ChannelSendResult(
            success=True,
            provider_message_id=f"{provider_prefix}-{uuid.uuid4().hex[:10]}",
            latency_ms=latency,
        )
