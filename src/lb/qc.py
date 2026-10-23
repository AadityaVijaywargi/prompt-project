"""Human verification round trip for the Hindi-fluent checkers.

    python -m lb.qc export [--out data/qc/to_verify.csv]   unverified texts -> CSV (one row per text)
    python -m lb.qc import data/qc/to_verify.csv           apply corrections, mark sections verified

CSV is written as UTF-8 with BOM so Excel and Google Sheets show Devanagari correctly.
Checker columns: corrected_text (leave blank if the text is fine), ok (Y / N), verified_by, notes.

Two sections are verified independently:
  - answers (qc):       answers.hi / answers.hi_rom / answers.hinglish, plus question_en for MT-Bench-Hi items
                        (an English translation of a native Hindi prompt)
  - wrong twin (wrong_qc): wrong.hi / wrong.hi_rom / wrong.hinglish
A section becomes passed only when every one of its rows has ok=Y and a verifier name.
"""
from __future__ import annotations

import argparse
import csv
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path

from .config import DATA, read_jsonl, write_jsonl
from .schema import FORMS, Quadruple, word_count

QUADRUPLES = DATA / "quadruples.jsonl"
QUESTIONS = DATA / "questions.jsonl"
DEFAULT_CSV = DATA / "qc" / "to_verify.csv"
COLUMNS = ["item_id", "field", "compare_with", "text", "corrected_text", "ok", "verified_by", "notes"]
GUIDE = {
    "hi": "Natural written Hindi (Devanagari); same facts as compare_with (English)",
    "hi_rom": "Same Hindi in Roman letters; pure Hindi words, English only for proper nouns",
    "hinglish": "Roman script with natural Hindi-English mixing; same facts, nothing added or dropped",
    "question_en": "English translation of the original Hindi prompt (compare_with); same meaning",
}
SECTION_QC = {"answers": "qc", "question_en": "qc", "wrong": "wrong_qc"}


def _section(field: str) -> str:
    return field.split(".")[0]


def _guide(field: str) -> str:
    return GUIDE[field.split(".")[-1]]


def _fields(q: Quadruple, hi_prompts: dict[str, str], section: str):
    """(field, compare_with, text) rows for one QC section of an item."""
    if section == "qc":
        if q.source == "MT-Bench-Hi":
            yield "question_en", hi_prompts.get(q.item_id, ""), q.question_en
        for f in FORMS[1:]:
            yield f"answers.{f}", q.answers.en.text, q.answers.get(f).text
    elif q.wrong is not None:
        for f in FORMS[1:]:
            yield f"wrong.{f}", q.wrong.en.text, q.wrong.get(f).text


def _hi_prompts() -> dict[str, str]:
    if not QUESTIONS.exists():
        return {}
    return {r["item_id"]: r.get("question_hi_source") or "" for r in read_jsonl(QUESTIONS)}


def export(out: Path) -> int:
    items = [Quadruple.model_validate(r) for r in read_jsonl(QUADRUPLES)]
    hi = _hi_prompts()
    rows = []
    for q in items:
        sections = [s for s, qc in (("qc", q.qc), ("wrong_qc", q.wrong_qc)) if qc is not None and not qc.passed]
        for s in sections:
            for field, cmp, text in _fields(q, hi, s):
                rows.append({"item_id": q.item_id, "field": field, "compare_with": cmp, "text": text,
                             "corrected_text": "", "ok": "", "verified_by": "", "notes": _guide(field)})
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows for {len({r['item_id'] for r in rows})} items to {out}")
    return len(rows)


def _apply_edit(rec: dict, field: str, new: str) -> bool:
    if field == "question_en":
        if new == rec["question_en"]:
            return False
        rec["question_en"] = new
        return True
    section, form = field.split(".")
    if new == rec[section][form]["text"]:
        return False
    rec[section][form] = {"text": new, "words": word_count(new)}
    return True


def import_(path: Path, on: date | None = None) -> None:
    on = on or date.today()
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    by_item = defaultdict(list)
    for r in rows:
        by_item[r["item_id"]].append(r)
    hi = _hi_prompts()
    records = list(read_jsonl(QUADRUPLES))
    changed = passed = 0
    for rec in records:
        item_rows = by_item.get(rec["item_id"])
        if not item_rows:
            continue
        for qc_key in ("qc", "wrong_qc"):
            sec_rows = [r for r in item_rows if SECTION_QC[_section(r["field"])] == qc_key]
            if not sec_rows or rec.get(qc_key) is None:
                continue
            edits = 0
            for r in sec_rows:
                new = unicodedata.normalize("NFC", (r.get("corrected_text") or "").strip())
                if new and _apply_edit(rec, r["field"], new):
                    edits += 1
            qc = rec[qc_key]
            verifiers = sorted({v.strip() for r in sec_rows
                                for v in (r.get("verified_by") or "").split(";") if v.strip()})
            expected = {fld for fld, _, _ in _fields(Quadruple.model_validate(rec), hi, qc_key)}
            all_ok = (expected <= {r["field"] for r in sec_rows}
                      and all((r.get("ok") or "").strip().upper() == "Y" and (r.get("verified_by") or "").strip()
                              for r in sec_rows))
            qc["edits"] = qc.get("edits", 0) + edits
            qc["verified_by"] = sorted(set(qc.get("verified_by", [])) | set(verifiers))
            notes = "; ".join(r["notes"] for r in sec_rows if r.get("notes") and r["notes"] != _guide(r["field"]))
            if notes:
                qc["notes"] = notes
            if all_ok:
                qc["passed"], qc["verified_on"] = True, on.isoformat()
                passed += 1
        Quadruple.model_validate(rec)
        changed += 1
    write_jsonl(QUADRUPLES, records)
    print(f"updated {changed} items; {passed} sections newly marked passed")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--out", type=Path, default=DEFAULT_CSV)
    i = sub.add_parser("import")
    i.add_argument("csv", type=Path)
    args = p.parse_args()
    if args.cmd == "export":
        export(args.out)
    else:
        import_(args.csv)


if __name__ == "__main__":
    main()
