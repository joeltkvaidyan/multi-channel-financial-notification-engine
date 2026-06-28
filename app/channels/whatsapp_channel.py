"""WhatsApp channel adapter. Production: swap for WhatsApp Business Cloud API.
Note: WhatsApp template messages outside the 24h session window require
pre-approved Meta templates -- this is a real operational constraint worth
calling out in the runbook, not just a code detail."""

from __future__ import annotations

import logging

from app.channels.base import ChannelAdapter, ChannelSendResult, SimulatedFailureMixin

logger = logging.getLogger("notification_engine.channels.whatsapp")


class WhatsAppChannel(SimulatedFailureMixin, ChannelAdapter):
    name = "WHATSAPP"
    failure_rate = 0.08
    min_latency_ms = 200
    max_latency_ms = 1800

    async def send(self, recipient: str, content: str | dict) -> ChannelSendResult:
        body = content if isinstance(content, str) else str(content)
        logger.info("WHATSAPP -> %s: %s", recipient, body[:60])
        return await self._simulate("WA")
