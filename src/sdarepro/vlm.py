"""Model clients behind one tiny interface.

Messages use a neutral format so conditions are client-agnostic:
    [{"role": "user"|"assistant", "content": [{"type": "text", "text": str} | {"type": "image", "image": PIL.Image}]}]
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Reply:
    text: str
    parsed: Optional[dict]
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    latency_s: float = 0.0
    stop_reason: str = ""


def parse_json(text: str) -> Optional[dict]:
    """The LAST complete JSON object in the reply; tolerates code fences and prose around it.

    Track V bug: a reply with a JSON answer followed by 'Correction to format: {...}' was read by a
    greedy regex as one invalid block and scored as an empty answer. The last object is the model's
    final word."""
    dec, found, i = json.JSONDecoder(), None, text.find("{")
    while i != -1:
        try:
            obj, end = dec.raw_decode(text, i)
        except json.JSONDecodeError:
            i = text.find("{", i + 1)
            continue
        if isinstance(obj, dict):
            found = obj
        i = text.find("{", end)
    return found


def norm_name(x) -> str:
    """'Chair 1', 'chair_1', 'chair1', '#chair1' -> 'chair1'."""
    return re.sub(r"[\s_#]+", "", str(x).lower())


def ids_from(parsed: Optional[dict], name_map: Optional[dict[str, int]] = None) -> list[int]:
    """Candidate ids from a reply. Accepts 7, '#7', or a drawn name tag like 'chair 3' (needs name_map)."""
    if not parsed:
        return []
    out = []
    for x in parsed.get("candidate_ids", []) or []:
        key = norm_name(x)
        if name_map and key in name_map:
            out.append(name_map[key])
            continue
        try:
            out.append(int(key))
        except ValueError:
            continue
    return sorted(set(out))


class VLMClient:
    name = "base"

    def respond(self, system: str, messages: list[dict]) -> Reply:  # pragma: no cover
        raise NotImplementedError


class ScriptedClient(VLMClient):
    """Returns pre-set replies in order. Used by tests and dry runs."""

    name = "scripted"

    def __init__(self, replies: list[dict]):
        self.replies = list(replies)
        self.calls: list[tuple[str, list[dict]]] = []

    def respond(self, system: str, messages: list[dict]) -> Reply:
        self.calls.append((system, list(messages)))  # snapshot: the runner appends to its list afterwards
        r = self.replies.pop(0)
        return Reply(text=json.dumps(r), parsed=r)


def _jpeg_b64(img, quality: int = 90) -> str:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode()


class ClaudeClient(VLMClient):
    """Anthropic Messages API.

    The key is read from SDA_API_KEY (preferred) and only then from ANTHROPIC_API_KEY.
    Keep it in SDA_API_KEY: if ANTHROPIC_API_KEY is set in the shell that starts Claude Code,
    Claude Code switches to API-key auth and Remote Control refuses to start.

    The model id is NOT hard-coded: pass it or set SDA_MODEL. Run
    `python -m sdarepro.vlm --list` to print the ids your key can use.

    Sampling: current models reject a non-default temperature (and SDK 1.x has no `temperature`
    argument), so PLAN.md 5.2 no longer sets temperature 0. Thinking is set by SDA_THINKING:
    'between_tools' (default, thinking off, like the paper's GPT-4o), 'adaptive', or 'omit'
    (send no thinking field, for models that do not know 'between_tools').
    """

    name = "claude"

    def __init__(self, model: Optional[str] = None, max_tokens: int = 400, thinking: Optional[str] = None,
                 cache_images: bool = True, max_retries: int = 5):
        import anthropic  # imported lazily so tests run without the SDK

        key = os.environ.get("SDA_API_KEY")
        self.client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
        self.model = model or os.environ.get("SDA_MODEL")
        if not self.model:
            raise ValueError("set SDA_MODEL or pass model=...")
        self.max_tokens = max_tokens
        self.thinking = thinking or os.environ.get("SDA_THINKING", "between_tools")
        if self.thinking not in ("between_tools", "adaptive", "omit"):
            raise ValueError(f"SDA_THINKING must be between_tools, adaptive or omit, not {self.thinking!r}")
        self.cache_images, self.max_retries = cache_images, max_retries

    def _convert(self, messages: list[dict]) -> list[dict]:
        out = []
        last_image_pos = None
        for mi, m in enumerate(messages):
            if m["role"] == "system":  # mid-conversation system message: plain text only
                out.append({"role": "system", "content": " ".join(b["text"] for b in m["content"])})
                continue
            blocks = []
            for b in m["content"]:
                if b["type"] == "text":
                    blocks.append({"type": "text", "text": b["text"]})
                else:
                    blocks.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                               "data": _jpeg_b64(b["image"])}})
                    last_image_pos = (mi, len(blocks) - 1)
            out.append({"role": m["role"], "content": blocks})
        if self.cache_images and last_image_pos is not None:
            mi, bi = last_image_pos
            out[mi]["content"][bi]["cache_control"] = {"type": "ephemeral"}
        return out

    def respond(self, system: str, messages: list[dict]) -> Reply:
        import anthropic

        payload = self._convert(messages)
        for attempt in range(self.max_retries):
            try:
                t0 = time.time()
                extra = {} if self.thinking == "omit" else {"thinking": {"type": self.thinking}}
                r = self.client.messages.create(model=self.model, max_tokens=self.max_tokens,
                                                system=system, messages=payload, **extra)
                text = "".join(getattr(b, "text", "") for b in r.content)
                u = r.usage
                return Reply(text=text, parsed=parse_json(text), input_tokens=u.input_tokens,
                             output_tokens=u.output_tokens,
                             cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
                             cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
                             latency_s=time.time() - t0, stop_reason=r.stop_reason or "")
            except (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.InternalServerError):
                time.sleep(2 ** attempt)
        raise RuntimeError("Claude API failed after retries")


if __name__ == "__main__":  # python -m sdarepro.vlm --list
    import sys

    if "--list" in sys.argv:
        import anthropic

        key = os.environ.get("SDA_API_KEY")
        for m in (anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()).models.list():
            print(m.id)
