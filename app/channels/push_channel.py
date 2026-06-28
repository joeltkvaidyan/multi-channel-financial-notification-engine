"""Push channel adapter. Production: swap for FCM/APNs via firebase-admin."""

from __future__ import annotations

import logging

from app.channels.base import ChannelAdapter, ChannelSendResult, SimulatedFailureMixin

logger = logging.getLogger("notification_engine.channels.push")


class PushChannel(SimulatedFailureMixin, ChannelAdapter):
    name = "PUSH"
    failure_rate = 0.18   # push has the highest drop rate: disabled perms, stale tokens
    min_latency_ms = 50
    max_latency_ms = 500

    async def send(self, recipient: str, content: str | dict) -> ChannelSendResult:
        logger.info("PUSH -> device:%s payload=%s", recipient, content)
        return await self._simulate("PUSH")
