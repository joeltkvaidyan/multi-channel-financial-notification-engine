"""
Template engine.

Uses Jinja2's "{{ variable }}" syntax, which is a superset-compatible
stand-in for the Handlebars/Mustache syntax the brief asked for — the
sample templates in /templates use plain {{var}} placeholders so they'd
port to a real Handlebars renderer in a Node service unchanged.

Templates are organised as: templates/<channel>/<locale>/<event_code>.txt
(or .html for email). Falling back to "en" if a locale-specific template
is missing keeps localisation additive rather than all-or-nothing.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

TEMPLATES_ROOT = Path(__file__).resolve().parent.parent.parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_ROOT)),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def _template_path(channel: str, event_code: str, locale: str, ext: str) -> str:
    return f"{channel.lower()}/{locale}/{event_code}.{ext}"


_EXT_BY_CHANNEL = {
    "EMAIL": "html",
    "SMS": "txt",
    "PUSH": "txt",
    "WHATSAPP": "txt",
    "IN_APP": "txt",
}


def render(channel: str, event_code: str, context: dict, locale: str = "en") -> str:
    """Render a channel-specific template for an event. Falls back to the
    'en' locale, then to a generic fallback template, so a missing
    translation never blocks a regulatory-mandatory message from sending."""
    ext = _EXT_BY_CHANNEL.get(channel.upper(), "txt")

    for candidate_locale in (locale, "en"):
        path = _template_path(channel, event_code, candidate_locale, ext)
        try:
            template = _env.get_template(path)
            return template.render(**context)
        except TemplateNotFound:
            continue

    # last-resort generic fallback so nothing silently fails to render
    fallback = _env.get_template(f"{channel.lower()}/en/_generic.{ext}")
    return fallback.render(event_code=event_code, **context)
