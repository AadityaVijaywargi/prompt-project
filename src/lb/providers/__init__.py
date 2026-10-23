"""One thin module per API. Every provider exposes complete(prompt) -> Completion."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Completion:
    text: str
    tokens: dict = field(default_factory=dict)


class Provider:
    name = "base"

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.model = cfg["model"]

    def complete(self, prompt: str, temperature: float = 0.0) -> Completion:
        raise NotImplementedError


class OfflineProvider(Provider):
    """Used by `make reproduce` and demo mode: any cache miss is an error, never a network call."""
    name = "offline"

    def complete(self, prompt: str, temperature: float = 0.0) -> Completion:
        raise RuntimeError(f"offline mode: cache miss for model {self.model}")


def make_provider(cfg: dict, offline: bool = False) -> Provider:
    if offline:
        return OfflineProvider(cfg)
    if cfg["provider"] == "openai_compat":
        from .openai_compat import OpenAICompatProvider
        return OpenAICompatProvider(cfg)
    raise ValueError(f"unknown provider {cfg['provider']!r}")
