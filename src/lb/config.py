"""Paths and config loading. Every file is read and written as UTF-8."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIGS = ROOT / "configs"
PROMPTS = ROOT / "prompts"
DATA = ROOT / "data"
RESULTS = ROOT / "results"
RAW = RESULTS / "raw"
CACHE = RESULTS / "cache"
TABLES = RESULTS / "tables"


def load_yaml(name: str) -> dict:
    with open(CONFIGS / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def judges_config() -> dict:
    return load_yaml("judges.yaml")


def experiments_config() -> dict:
    return load_yaml("experiments.yaml")


def read_jsonl(path: Path) -> Iterator[dict]:
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as e:
                    raise ValueError(f"{path}:{n}: invalid JSON: {e}") from e


def write_jsonl(path: Path, records: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
