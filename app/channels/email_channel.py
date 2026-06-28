"""Email channel adapter. Production: swap for SendGrid/SES/Postmark API call."""

from __future__ import annotations

import logging

from app.channels.base import ChannelAdapter, ChannelSendResult, SimulatedFailureMixin

logger = logging.getLogger("notification_engine.channels.email")


class EmailChannel(SimulatedFailureMixin, ChannelAdapter):
    name = "EMAIL"
    failure_rate = 0.03
    min_latency_ms = 300
    max_latency_ms = 2000

    async def send(self, recipient: str, content: str | dict) -> ChannelSendResult:
        body = content if isinstance(content, str) else str(content)
        logger.info("EMAIL -> %s (%d chars)", recipient, len(body))
        return await self._simulate("EMAIL")
