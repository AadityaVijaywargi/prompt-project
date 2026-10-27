"""Parse judge responses. Judges must return JSON only; we tolerate code fences and surrounding prose."""
from __future__ import annotations

import json
import re

from pydantic import ValidationError

from .schema import PairwiseVerdict, PointwiseScore

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json(text: str | None) -> dict:
    if not text or not text.strip():
        raise ValueError("empty response")
    candidates = [m.group(1) for m in _FENCE.finditer(text)] + [text]
    for cand in candidates:
        start = cand.find("{")
        while start != -1:
            depth = 0
            for i in range(start, len(cand)):
                if cand[i] == "{":
                    depth += 1
                elif cand[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            obj = json.loads(cand[start:i + 1])
                        except json.JSONDecodeError:
                            break
                        if isinstance(obj, dict):
                            return obj
                        break
            start = cand.find("{", start + 1)
    raise ValueError("no JSON object found")


def parse_pointwise(text: str | None) -> PointwiseScore:
    obj = extract_json(text)
    for key in ("correctness", "completeness", "clarity", "language_quality"):
        if isinstance(obj.get(key), str) and obj[key].strip().isdigit():
            obj[key] = int(obj[key].strip())
    obj = {k: obj[k] for k in PointwiseScore.model_fields if k in obj}
    try:
        return PointwiseScore.model_validate(obj)
    except ValidationError as e:
        raise ValueError(f"invalid pointwise JSON: {e.errors()[0]['msg']}") from e


def parse_pairwise(text: str | None) -> PairwiseVerdict:
    obj = extract_json(text)
    winner = str(obj.get("winner", "")).strip().strip('"').strip()
    norm = {"a": "A", "b": "B", "tie": "tie", "answer a": "A", "answer b": "B"}.get(winner.lower())
    if norm is None:
        raise ValueError(f"invalid winner: {winner!r}")
    return PairwiseVerdict(winner=norm, reason=str(obj.get("reason", "")))


def parse_text(text: str | None) -> str:
    """Plain-text response (the E5(b) translator): any non-empty text counts as parsed."""
    if not text or not text.strip():
        raise ValueError("empty response")
    return text.strip()
