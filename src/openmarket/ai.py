"""Configurable LLM client for the news explanations (⑤). httpx only — no provider SDK.

Configuration comes from the environment only (never from files, never logged):
- OPENMARKET_AI_FORMAT   `openai` (default): POST {base}/chat/completions — Groq, OpenRouter, NVIDIA
                         NIM, Gemini's OpenAI-compatible endpoint…
                         `anthropic`: POST {base}/v1/messages — the Claude API, or a local
                         free-claude-code proxy (run as a separate program; its AGPL code is not used here).
- OPENMARKET_AI_BASE_URL default https://api.groq.com/openai/v1 (openai) / https://api.anthropic.com (anthropic)
- OPENMARKET_AI_KEY      required
- OPENMARKET_AI_MODEL    default qwen/qwen3-32b (openai) / claude-opus-5-5 (anthropic)
"""

from __future__ import annotations

import asyncio
import os
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

ANTHROPIC_VERSION = "2026-10-21"  # no temperature/top_p/top_k on this version
TIMEOUT_SECONDS = 30.0
MAX_RETRIES = 2  # after the first attempt, for 429 / 5xx / network errors
RETRY_BACKOFF_SECONDS = 2.0
DEFAULTS = {
    "openai": ("https://api.groq.com/openai/v1", "qwen/qwen3-32b"),
    "anthropic": ("https://api.anthropic.com", "claude-opus-5-5"),
}


class AIError(Exception):
    """Provider failure; the message never contains the API key."""


@dataclass(frozen=True)
class AIConfig:
    format: str
    base_url: str
    key: str
    model: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> AIConfig:
        fmt = (env.get("OPENMARKET_AI_FORMAT") or "openai").strip().lower()
        if fmt not in DEFAULTS:
            fmt = "openai"
        base, model = DEFAULTS[fmt]
        return cls(
            format=fmt,
            base_url=(env.get("OPENMARKET_AI_BASE_URL") or base).strip().rstrip("/"),
            key=(env.get("OPENMARKET_AI_KEY") or "").strip(),
            model=(env.get("OPENMARKET_AI_MODEL") or model).strip(),
        )

    @property
    def configured(self) -> bool:
        return bool(self.key and self.base_url and self.model)

    def public(self) -> dict:
        """Status for the UI: no key, only whether one is set."""
        return {"configured": self.configured, "format": self.format, "model": self.model, "host": urlparse(self.base_url).netloc}


def strip_reasoning(text: str) -> str:
    """Drop <think>…</think> blocks some open models (Qwen3, DeepSeek-R1) prepend to the answer."""
    return re.sub(r"<think>.*?(</think>|$)", "", text, flags=re.S).strip()


def _request(cfg: AIConfig, system: str, user: str, max_tokens: int) -> tuple[str, dict, dict]:
    if cfg.format == "anthropic":
        headers = {"x-api-key": cfg.key, "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"}
        body = {"model": cfg.model, "max_tokens": max(max_tokens, 16000), "system": system, "messages": [{"role": "user", "content": user}]}
        if urlparse(cfg.base_url).netloc == "api.anthropic.com":
            # server-side refusal fallback (Claude API only; a local proxy may not accept the beta field)
            headers["anthropic-beta"] = "server-side-fallback-2026-07-01"
            body["fallbacks"] = "default"
        return f"{cfg.base_url}/v1/messages", headers, body
    return (
        f"{cfg.base_url}/chat/completions",
        {"Authorization": f"Bearer {cfg.key}", "content-type": "application/json"},
        {
            "model": cfg.model,
            "max_tokens": max_tokens,
            "temperature": 0.2,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        },
    )


def _text(cfg: AIConfig, body: dict) -> str:
    try:
        if cfg.format == "anthropic":
            if body.get("stop_reason") == "refusal":
                raise AIError("AI 拒絕回答這個請求")
            return "".join(b.get("text", "") for b in body["content"] if b.get("type") == "text")
        return body["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise AIError("AI 回應格式無法解析") from exc


async def complete(
    client: httpx.AsyncClient,
    cfg: AIConfig,
    system: str,
    user: str,
    *,
    max_tokens: int = 1024,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> str:
    """One chat completion → plain answer text (reasoning blocks removed)."""
    if not cfg.configured:
        raise AIError("AI 未設定（OPENMARKET_AI_KEY）")
    url, headers, payload = _request(cfg, system, user, max_tokens)
    last = ""
    for attempt in range(MAX_RETRIES + 1):
        if attempt:
            await sleep(RETRY_BACKOFF_SECONDS * attempt)
        try:
            resp = await client.post(url, headers=headers, json=payload, timeout=TIMEOUT_SECONDS)
        except httpx.HTTPError as exc:
            last = f"連線失敗（{type(exc).__name__}）"
            continue
        if resp.status_code == 429 or resp.status_code >= 500:
            last = f"HTTP {resp.status_code}"
            continue
        if resp.status_code >= 400:
            raise AIError(f"HTTP {resp.status_code}")  # bad key / model: retrying will not help
        try:
            body = resp.json()
        except ValueError as exc:
            raise AIError("AI 回應不是 JSON") from exc
        return strip_reasoning(_text(cfg, body))
    raise AIError(f"AI 服務暫時無法使用（{last}）")
