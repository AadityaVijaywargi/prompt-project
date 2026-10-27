"""Judge interface: score() for pointwise rubric grading, compare() for pairwise preference.

Every call goes through the cache and is logged as one line in results/raw/. A failed parse is retried
up to two times; each retry is a distinct cached call (the attempt number is part of the cache key).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from . import prompts
from .cache import Cache, cache_key
from .config import RAW, append_jsonl
from .parse import parse_pairwise, parse_pointwise, parse_text
from .providers import Provider, make_provider
from .schema import PairwiseVerdict, PointwiseScore, RawCall

MAX_PARSE_RETRIES = 2


@dataclass
class CallMeta:
    run_id: str
    experiment: str
    prompt_variant: str
    item_id: str
    forms: list[str] = field(default_factory=list)
    order: Optional[str] = None


class Judge:
    def __init__(self, name: str, cfg: dict, cache: Optional[Cache] = None, offline: bool = False,
                 provider: Optional[Provider] = None, temperature: float = 0.0, raw_dir: Path = RAW):
        self.name = name
        self.cfg = cfg
        self.model = cfg["model"]
        self.cache = cache or Cache()
        self.offline = offline
        self.temperature = temperature
        self.raw_dir = Path(raw_dir)
        self._provider = provider

    @property
    def provider(self) -> Provider:
        if self._provider is None:            # created lazily so budget/offline runs need no keys
            self._provider = make_provider(self.cfg, offline=self.offline)
        return self._provider

    def key(self, prompt: str, attempt: int = 0) -> str:
        return cache_key(self.model, prompt, {"temperature": self.temperature, "attempt": attempt})

    # ----- public interface -----

    def score(self, question: str, answer: str, meta: CallMeta, reference: str | None = None,
              prompt_name: str = "pointwise_en", suffix: str | None = None) -> Optional[PointwiseScore]:
        prompt = prompts.render_pointwise(prompt_name, question, answer, reference, suffix)
        return self.run_prompt(prompt, parse_pointwise, meta)

    def compare(self, question: str, answer_a: str, answer_b: str, meta: CallMeta,
                reference: str | None = None, prompt_name: str = "pairwise_en",
                suffix: str | None = None) -> Optional[PairwiseVerdict]:
        prompt = prompts.render_pairwise(prompt_name, question, answer_a, answer_b, reference, suffix)
        return self.run_prompt(prompt, parse_pairwise, meta)

    def complete_text(self, prompt: str, meta: CallMeta) -> Optional[str]:
        """Plain-text call (the E5(b) translator). Any non-empty response counts as parsed."""
        return self.run_prompt(prompt, parse_text, meta)

    # ----- internals -----

    def run_prompt(self, prompt: str, parser: Callable, meta: CallMeta):
        for attempt in range(MAX_PARSE_RETRIES + 1):
            key = self.key(prompt, attempt)
            cached = self.cache.get(key)
            if cached is not None:
                text, tokens, hit = cached["text"], cached.get("tokens", {}), True
            else:
                try:
                    completion = self.provider.complete(prompt, self.temperature)
                except Exception as e:
                    self._log(meta, attempt, key, None, None, False, f"provider error: {e}", {}, False)
                    raise
                text, tokens, hit = completion.text, completion.tokens, False
                self.cache.put(key, {"model": self.model, "provider": self.cfg["provider"],
                                     "text": text, "tokens": tokens,
                                     "created": datetime.now(timezone.utc).isoformat()})
            try:
                result = parser(text)
            except ValueError as e:
                self._log(meta, attempt, key, text, None, False, str(e), tokens, hit)
                continue
            parsed = result.model_dump() if hasattr(result, "model_dump") else {"text": result}
            self._log(meta, attempt, key, text, parsed, True, None, tokens, hit)
            return result
        return None

    def _log(self, meta: CallMeta, attempt: int, key: str, raw: Optional[str], parsed: Optional[dict],
             ok: bool, error: Optional[str], tokens: dict, hit: bool) -> None:
        rec = RawCall(run_id=meta.run_id, experiment=meta.experiment, judge=self.name,
                      model=self.model, provider=self.cfg["provider"],
                      prompt_variant=meta.prompt_variant, item_id=meta.item_id, forms=meta.forms,
                      order=meta.order, attempt=attempt, raw_response=raw, parsed=parsed,
                      parse_ok=ok, error=error, tokens=tokens or {},
                      timestamp=datetime.now(timezone.utc).isoformat(), cache_hit=hit, cache_key=key)
        append_jsonl(self.raw_dir / f"{meta.experiment}__{meta.run_id}.jsonl", rec.model_dump())
