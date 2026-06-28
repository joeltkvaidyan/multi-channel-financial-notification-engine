"""
Saga Pattern: multi-channel delivery orchestration.

A `Notification` has a channel_plan, e.g. ["SMS", "PUSH", "EMAIL"]. The
saga is the long-running process that walks this plan:

  for each channel in plan:
      retry up to MAX_RETRIES with exponential backoff
      if it succeeds -> done, record DELIVERED, stop (no need to spam every
                         channel once one has worked)
      if it exhausts retries -> move to next channel in the plan (fallback)
  if every channel in the plan is exhausted -> dead-letter the notification

This is a saga rather than a single try/except because it's a sequence of
local steps (each channel send), each independently retryable, with a
defined compensating path (DLQ) if the whole sequence fails — exactly the
shape sagas are for, just without needing to *undo* prior steps (sending
an SMS doesn't need "compensating"; the closest thing to compensation here
is escalating to the next channel).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from app.channels.registry import get_channel
from app.channels.base import ChannelSendResult

logger = logging.getLogger("notification_engine.saga")

MAX_RETRIES_PER_CHANNEL = 3
BASE_BACKOFF_SECONDS = 0.2   # demo-scaled; production would use seconds-to-minutes


@dataclass
class ChannelAttemptLog:
    channel: str
    attempt_number: int
    result: ChannelSendResult


@dataclass
class SagaResult:
    delivered: bool
    delivered_channel: str | None
    attempts: list[ChannelAttemptLog] = field(default_factory=list)
    dead_lettered: bool = False


async def _send_with_retry(channel_name: str, recipient: str, content) -> list[ChannelAttemptLog]:
    channel = get_channel(channel_name)
    logs: list[ChannelAttemptLog] = []

    for attempt in range(1, MAX_RETRIES_PER_CHANNEL + 1):
        result = await channel.send(recipient, content)
        logs.append(ChannelAttemptLog(channel_name, attempt, result))
        if result.success:
            return logs
        backoff = BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
        logger.warning(
            "channel=%s attempt=%d failed (%s), backing off %.2fs",
            channel_name, attempt, result.error, backoff,
        )
        await asyncio.sleep(backoff)

    return logs


async def run_saga(channel_plan: list[str], recipients: dict[str, str], rendered_content: dict[str, str]) -> SagaResult:
    """
    recipients: {"SMS": "+91...", "EMAIL": "user@...", ...}
    rendered_content: {"SMS": "rendered text", "EMAIL": "<html>...", ...}
    """
    all_attempts: list[ChannelAttemptLog] = []

    for channel_name in channel_plan:
        recipient = recipients.get(channel_name)
        content = rendered_content.get(channel_name)
        if not recipient or content is None:
            logger.info("skipping channel=%s: no recipient/content on file", channel_name)
            continue

        logs = await _send_with_retry(channel_name, recipient, content)
        all_attempts.extend(logs)

        if logs and logs[-1].result.success:
            return SagaResult(delivered=True, delivered_channel=channel_name, attempts=all_attempts)

        logger.info("falling back from channel=%s to next in plan", channel_name)

    # exhausted every channel in the plan without success
    return SagaResult(delivered=False, delivered_channel=None, attempts=all_attempts, dead_lettered=True)
