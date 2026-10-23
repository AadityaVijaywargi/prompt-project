"""Response cache: sha256(model id, full prompt text, inputs) -> stored provider response.

A cache hit never calls the provider. Entries are written once and never overwritten.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

from .config import CACHE


def cache_key(model: str, prompt: str, inputs: dict) -> str:
    payload = json.dumps({"model": model, "prompt": prompt, "inputs": inputs},
                         ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class Cache:
    def __init__(self, root: Path = CACHE):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def get(self, key: str) -> Optional[dict]:
        p = self._path(key)
        if not p.exists():
            return None
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def put(self, key: str, value: dict) -> None:
        p = self._path(key)
        if p.exists():
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=1)
        tmp.replace(p)

    def __contains__(self, key: str) -> bool:
        return self._path(key).exists()
