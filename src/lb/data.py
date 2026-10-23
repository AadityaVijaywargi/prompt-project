"""Loading quadruples. Only qc.passed items enter any analysis unless include_unverified is set."""
from __future__ import annotations

from pathlib import Path

from .config import DATA, read_jsonl
from .schema import Quadruple

QUADRUPLES = DATA / "quadruples.jsonl"


def load_quadruples(path: Path = QUADRUPLES, include_unverified: bool = False,
                    pilot_only: bool = False) -> list[Quadruple]:
    items = [Quadruple.model_validate(r) for r in read_jsonl(path)]
    if not include_unverified:
        items = [q for q in items if q.qc.passed]
    if pilot_only:
        items = [q for q in items if q.pilot]
    return items


def reference_for(q: Quadruple, mode: str) -> str | None:
    """Reference-guided judging flag (brief section 12): factual | all | none."""
    if mode == "none" or not q.reference_en:
        return None
    if mode == "factual" and q.type != "factual":
        return None
    return q.reference_en
