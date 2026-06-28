"""SMS channel adapter. Production: swap `_simulate` call for an MSG91/
Twilio/Karix REST call, keeping the same ChannelSendResult contract."""

from __future__ import annotations

import logging

from app.channels.base import ChannelAdapter, ChannelSendResult, SimulatedFailureMixin

logger = logging.getLogger("notification_engine.channels.sms")


class SMSChannel(SimulatedFailureMixin, ChannelAdapter):
    name = "SMS"
    failure_rate = 0.05   # SMS is generally highly reliable in India
    min_latency_ms = 200
    max_latency_ms = 1500

    async def send(self, recipient: str, content: str | dict) -> ChannelSendResult:
        body = content if isinstance(content, str) else str(content)
        logger.info("SMS -> %s: %s", recipient, body[:60])
        return await self._simulate("SMS")
