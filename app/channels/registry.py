"""Registry mapping channel name -> adapter instance. One place to wire up
real providers later (e.g. read provider choice from env/config per channel)."""

from __future__ import annotations

from app.channels.base import ChannelAdapter
from app.channels.email_channel import EmailChannel
from app.channels.in_app_channel import InAppChannel
from app.channels.push_channel import PushChannel
from app.channels.sms_channel import SMSChannel
from app.channels.whatsapp_channel import WhatsAppChannel

CHANNEL_REGISTRY: dict[str, ChannelAdapter] = {
    "SMS": SMSChannel(),
    "EMAIL": EmailChannel(),
    "PUSH": PushChannel(),
    "WHATSAPP": WhatsAppChannel(),
    "IN_APP": InAppChannel(),
}


def get_channel(name: str) -> ChannelAdapter:
    try:
        return CHANNEL_REGISTRY[name.upper()]
    except KeyError as exc:
        raise ValueError(f"Unknown channel: {name}") from exc
