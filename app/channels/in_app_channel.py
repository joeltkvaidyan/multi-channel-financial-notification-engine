"""In-app channel adapter. Production: write to a per-user inbox table /
push over an existing WebSocket connection if the user is online."""

from __future__ import annotations

import logging

from app.channels.base import ChannelAdapter, ChannelSendResult, SimulatedFailureMixin

logger = logging.getLogger("notification_engine.channels.in_app")


class InAppChannel(SimulatedFailureMixin, ChannelAdapter):
    name = "IN_APP"
    failure_rate = 0.01   # writing to our own DB rarely fails
    min_latency_ms = 10
    max_latency_ms = 80

    async def send(self, recipient: str, content: str | dict) -> ChannelSendResult:
        logger.info("IN_APP -> user:%s: %s", recipient, content)
        return await self._simulate("INAPP")
