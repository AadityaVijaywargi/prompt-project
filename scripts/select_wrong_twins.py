"""Choose the E3 wrong-twin subset: a seeded random sample of factual items, stratified STEM / humanities.

Selection depends only on the seed and the item list, never on judge outputs.
Writes data/sources/wrong_twin_selection.json.

    python scripts/select_wrong_twins.py
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from lb.config import DATA, experiments_config, read_jsonl  # noqa: E402


def main() -> None:
    cfg = experiments_config()
    per_stratum = cfg["targets"]["wrong_twins"] // 2
    qs = [q for q in read_jsonl(DATA / "questions.jsonl") if q["type"] == "factual"]
    rng = random.Random(cfg["seed"] + 2)
    chosen = {}
    for domain in ("stem", "humanities"):
        ids = sorted(q["item_id"] for q in qs if q["domain"] == domain)
        chosen[domain] = sorted(rng.sample(ids, per_stratum))
    out = DATA / "sources" / "wrong_twin_selection.json"
    out.write_text(json.dumps({"seed": cfg["seed"] + 2, "items": chosen}, indent=1), encoding="utf-8")
    print(f"selected {sum(len(v) for v in chosen.values())} items -> {out}")


if __name__ == "__main__":
    main()
