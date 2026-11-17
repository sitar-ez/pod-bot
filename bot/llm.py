"""Talks to Claude and returns parsed JSON."""
import json
import re

import anthropic

from . import settings
from .common import env

_client = None


def client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=env("ANTHROPIC_API_KEY"))
    return _client


def ask_json(system, prompt, max_tokens=8000):
    msg = client().messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    from . import costs
    costs.claude(msg)
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return parse_json(text)


def parse_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
        end = max(text.rfind("}"), text.rfind("]"))
        if start < 0 or end < 0:
            raise
        return json.loads(text[start:end + 1])
