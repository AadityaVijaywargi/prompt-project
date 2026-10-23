"""OpenAI-compatible chat endpoint (Gemini, Groq, Ollama, Sarvam). Keys come from environment variables."""
from __future__ import annotations

import os
import random
import time

import httpx

from . import Completion, Provider

RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504}


class OpenAICompatProvider(Provider):
    name = "openai_compat"

    def __init__(self, cfg: dict, max_retries: int = 8, timeout: float = 120.0):
        super().__init__(cfg)
        self.url = cfg["base_url"].rstrip("/") + "/chat/completions"
        key_env = cfg.get("api_key_env")
        self.api_key = os.environ.get(key_env) if key_env else None
        if key_env and not self.api_key:
            raise RuntimeError(f"environment variable {key_env} is not set")
        self.min_interval = 60.0 / float(cfg.get("requests_per_minute", 30))
        self.max_retries = max_retries
        self.client = httpx.Client(timeout=timeout)
        self._last = 0.0

    def _throttle(self) -> None:
        wait = self._last + self.min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def complete(self, prompt: str, temperature: float = 0.0) -> Completion:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = {"model": self.model, "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}]}
        delay = 2.0
        for attempt in range(self.max_retries + 1):
            self._throttle()
            try:
                r = self.client.post(self.url, json=body, headers=headers)
            except httpx.TransportError:
                if attempt == self.max_retries:
                    raise
            else:
                if r.status_code == 200:
                    data = r.json()
                    text = data["choices"][0]["message"].get("content") or ""
                    usage = data.get("usage") or {}
                    return Completion(text=text, tokens={
                        "prompt": usage.get("prompt_tokens"),
                        "completion": usage.get("completion_tokens")})
                if r.status_code not in RETRY_STATUS or attempt == self.max_retries:
                    r.raise_for_status()
                retry_after = r.headers.get("retry-after")
                if retry_after and retry_after.replace(".", "", 1).isdigit():
                    delay = max(delay, float(retry_after))
            time.sleep(delay + random.uniform(0, 1))
            delay = min(delay * 2, 120.0)
        raise RuntimeError("unreachable")
