"""make data-check: validate every data record (brief section 10).

Errors (exit 1): schema violations, non-UTF-8 bytes, duplicate ids, missing forms, script mismatches,
drafting model listed as a judge. Warnings: word-count ratio vs en outside 0.6-1.8, items not qc.passed.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

from pydantic import ValidationError

from .config import DATA, judges_config
from .schema import FORMS, FourForms, HumanGrade, Quadruple, Question

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
RATIO_RANGE = (0.6, 1.8)


class Report:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def read_utf8_lines(path: Path, rep: Report) -> list[tuple[int, str]]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        rep.error(f"{path.name}: not valid UTF-8 at byte {e.start}")
        text = raw.decode("utf-8", errors="replace")
    return [(n, line) for n, line in enumerate(text.splitlines(), 1) if line.strip()]


def check_forms(item_id: str, label: str, forms: FourForms, rep: Report) -> None:
    en_words = forms.en.words
    for f in FORMS:
        t = forms.get(f).text
        has_deva = bool(DEVANAGARI.search(t))
        if f == "hi" and not has_deva:
            rep.error(f"{item_id} {label}.hi has no Devanagari characters")
        if f in ("en", "hi_rom", "hinglish") and has_deva:
            rep.error(f"{item_id} {label}.{f} contains Devanagari characters")
        if f != "en":
            ratio = forms.get(f).words / en_words
            if not RATIO_RANGE[0] <= ratio <= RATIO_RANGE[1]:
                rep.warn(f"{item_id} {label}.{f} word ratio vs en = {ratio:.2f} (outside 0.6-1.8)")


def check_quadruples(path: Path, rep: Report, judge_models: set[str]) -> list[Quadruple]:
    items, seen = [], set()
    for n, line in read_utf8_lines(path, rep):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            rep.error(f"{path.name}:{n}: invalid JSON ({e})")
            continue
        missing = [f for f in FORMS if f not in (obj.get("answers") or {})]
        if missing:
            rep.error(f"{path.name}:{n} {obj.get('item_id')}: missing forms {missing}")
            continue
        try:
            q = Quadruple.model_validate(obj)
        except ValidationError as e:
            for err in e.errors():
                rep.error(f"{path.name}:{n} {obj.get('item_id')}: {'.'.join(map(str, err['loc']))}: {err['msg']}")
            continue
        if q.item_id in seen:
            rep.error(f"duplicate item_id {q.item_id}")
        seen.add(q.item_id)
        if q.drafted_by in judge_models:
            rep.error(f"{q.item_id}: drafted_by {q.drafted_by} is also an enabled judge (self-preference)")
        check_forms(q.item_id, "answers", q.answers, rep)
        if q.wrong is not None:
            check_forms(q.item_id, "wrong", q.wrong, rep)
        if not q.qc.passed:
            rep.warn(f"{q.item_id}: not passed_qc (excluded from analysis)")
        if q.wrong is not None and not q.wrong_usable:
            rep.warn(f"{q.item_id}: wrong twin not passed_qc (excluded from E3)")
        items.append(q)
    return items


def check_questions(path: Path, rep: Report) -> None:
    seen = set()
    for n, line in read_utf8_lines(path, rep):
        try:
            q = Question.model_validate(json.loads(line))
        except (json.JSONDecodeError, ValidationError) as e:
            rep.error(f"{path.name}:{n}: {e}")
            continue
        if q.item_id in seen:
            rep.error(f"{path.name}: duplicate item_id {q.item_id}")
        seen.add(q.item_id)


def check_human_grades(path: Path, rep: Report) -> None:
    read_utf8_lines(path, rep)
    with open(path, encoding="utf-8-sig", newline="") as f:
        for n, row in enumerate(csv.DictReader(f), 2):
            try:
                HumanGrade.model_validate(row)
            except ValidationError as e:
                rep.error(f"{path.name}:{n}: {e.errors()[0]['msg']}")


def run(data_dir: Path = DATA) -> Report:
    rep = Report()
    jc = judges_config()
    judge_models = {j["model"] for j in jc["judges"].values() if j.get("enabled")}
    if jc.get("drafting_model") in judge_models:
        rep.error(f"drafting model {jc['drafting_model']} is an enabled judge")
    if (data_dir / "questions.jsonl").exists():
        check_questions(data_dir / "questions.jsonl", rep)
    quads = data_dir / "quadruples.jsonl"
    if not quads.exists():
        rep.error("data/quadruples.jsonl not found")
        return rep
    items = check_quadruples(quads, rep, judge_models)
    if (data_dir / "human_grades.csv").exists():
        check_human_grades(data_dir / "human_grades.csv", rep)
    passed = sum(q.qc.passed for q in items)
    by_type = {t: sum(q.type == t for q in items) for t in ("factual", "open_ended")}
    print(f"quadruples: {len(items)} valid records ({by_type['factual']} factual, {by_type['open_ended']} open-ended), "
          f"{passed} qc.passed, {sum(q.wrong is not None for q in items)} with wrong twins "
          f"({sum(q.wrong_usable for q in items)} verified), {sum(q.pilot for q in items)} pilot")
    return rep


def main() -> None:
    rep = run()
    ratio = [w for w in rep.warnings if "ratio" in w]
    qc = [w for w in rep.warnings if "passed_qc" in w and "wrong twin" not in w]
    wqc = [w for w in rep.warnings if "wrong twin not passed_qc" in w]
    for w in ratio:
        print("WARN ", w)
    if qc:
        print(f"WARN  {len(qc)} items not passed_qc (excluded from analysis until verified)")
    if wqc:
        print(f"WARN  {len(wqc)} wrong twins not passed_qc (excluded from E3 until verified)")
    for e in rep.errors:
        print("ERROR", e)
    print(f"\n{len(rep.errors)} errors, {len(ratio)} length warnings, {len(qc)} unverified items, "
          f"{len(wqc)} unverified wrong twins")
    sys.exit(1 if rep.errors else 0)


if __name__ == "__main__":
    main()
