"""Build data/questions.jsonl, data/quadruples.jsonl and data/wrong_twins.jsonl from data/drafts/*.yaml.

Draft files hold either `items:` (four-form quadruples) or `wrong_twins:` (four-form wrong answers keyed by
item_id). Files named pilot_* produce pilot items. Word counts are computed here and all text is NFC.

Merge rules, so human verification is never lost:
  - a new item_id is added;
  - an existing section that is verified (passed) or has checker edits is kept exactly as it is
    (a warning is printed if the draft text has since changed);
  - an existing unverified, unedited section is refreshed from the draft.

    python scripts/build_data.py
"""
from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from lb.config import DATA, read_jsonl, write_jsonl  # noqa: E402
from lb.schema import FORMS, Quadruple, Question, word_count  # noqa: E402

DRAFTS = DATA / "drafts"
SOURCES = DATA / "sources"
FRESH_QC = {"verified_by": [], "verified_on": None, "edits": 0, "passed": False, "notes": ""}


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", " ".join(str(text).split()))


def four_forms(d: dict) -> dict:
    out = {}
    for f in FORMS:
        text = nfc(d[f])
        out[f] = {"text": text, "words": word_count(text)}
    return out


def mmmlu_question(c: dict) -> str:
    options = "\n".join(f"({letter}) {choice}" for letter, choice in zip("ABCD", c["choices_en"]))
    return f"{c['question_en'].strip()}\nOptions:\n{options}"


def load_sources() -> tuple[dict, dict, dict]:
    mmmlu = {}
    for name in ("mmmlu_candidates.jsonl", "mmmlu_candidates_phase1.jsonl"):
        if (SOURCES / name).exists():
            mmmlu.update({r["source_id"]: r for r in read_jsonl(SOURCES / name)})
    mtb = {r["source_id"]: r for r in read_jsonl(SOURCES / "mt_bench_prompts.jsonl")}
    mtbhi = {}
    if (SOURCES / "mt_bench_hi_prompts.jsonl").exists():
        mtbhi = {r["source_id"]: r for r in read_jsonl(SOURCES / "mt_bench_hi_prompts.jsonl")}
    return mmmlu, mtb, mtbhi


def make_question(d: dict, mmmlu: dict, mtb: dict, mtbhi: dict) -> Question:
    iid, sid = d["item_id"], str(d["source_id"])
    if iid.startswith("mmmlu-"):
        c = mmmlu[sid]
        if not c["aligned"]:
            raise SystemExit(f"{sid}: English/Hindi MMMLU rows not aligned")
        if not str(d["reference_en"]).startswith(f"({c['answer_letter']})"):
            raise SystemExit(f"{iid}: reference does not start with the keyed answer ({c['answer_letter']})")
        return Question(item_id=iid, source="MMMLU", source_id=sid, subject=c["subject"], domain=c["domain"],
                        type="factual", question_en=mmmlu_question(c), question_hi_source=c["question_hi_source"],
                        choices_en=c["choices_en"], answer_letter=c["answer_letter"])
    if iid.startswith("mtbhi-"):
        m = mtbhi[sid]
        if m["translated"]:
            raise SystemExit(f"{iid}: MT-Bench-Hi prompt {sid} is a translation; use the English original")
        return Question(item_id=iid, source="MT-Bench-Hi", source_id=sid, subject=m["category"],
                        domain="open_ended", type="open_ended", question_en=nfc(d["question_en"]),
                        question_hi_source=m["prompt_hi"].strip())
    m = mtb[sid]
    return Question(item_id=iid, source="MT-Bench", source_id=sid, subject=m["category"], domain="open_ended",
                    type="open_ended", question_en=d.get("question_en") and nfc(d["question_en"]) or m["prompt"].strip())


def locked(qc: dict | None) -> bool:
    return bool(qc) and (qc.get("passed") or qc.get("edits", 0) > 0)


def main() -> None:
    mmmlu, mtb, mtbhi = load_sources()
    out = DATA / "quadruples.jsonl"
    existing = {r["item_id"]: r for r in read_jsonl(out)} if out.exists() else {}
    drafted_by, item_drafts, wrong_drafts = {}, [], {}
    for path in sorted(DRAFTS.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        for d in doc.get("items", []):
            item_drafts.append((d, path.name.startswith("pilot"), doc["drafted_by"]))
        for w in doc.get("wrong_twins", []):
            if w["item_id"] in wrong_drafts:
                raise SystemExit(f"duplicate wrong twin for {w['item_id']}")
            wrong_drafts[w["item_id"]] = (w, doc["drafted_by"])

    ids = [d["item_id"] for d, _, _ in item_drafts]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise SystemExit(f"duplicate item_ids in drafts: {sorted(dupes)}")

    questions, records, kept, warnings = [], {}, 0, []
    for d, pilot, by in item_drafts:
        q = make_question(d, mmmlu, mtb, mtbhi)
        questions.append(q.model_dump(mode="json"))
        draft = {"item_id": q.item_id, "source": q.source, "subject": q.subject, "type": q.type,
                 "question_en": q.question_en,
                 "reference_en": nfc(d["reference_en"]) if d.get("reference_en") else None,
                 "answers": four_forms(d), "wrong": None, "drafted_by": by, "qc": dict(FRESH_QC),
                 "wrong_qc": None, "pilot": pilot}
        old = existing.get(q.item_id)
        if old and locked(old["qc"]):
            kept += 1
            if old["answers"] != draft["answers"] or old["question_en"] != draft["question_en"]:
                warnings.append(f"{q.item_id}: draft changed but item is verified/edited; kept the verified text")
            rec = {**draft, **{k: old[k] for k in ("question_en", "reference_en", "answers", "qc")}}
        else:
            rec = {**draft, "qc": old["qc"] if old else dict(FRESH_QC)}
        if old:
            rec["wrong"], rec["wrong_qc"] = old.get("wrong"), old.get("wrong_qc")
        records[q.item_id] = rec

    for iid, (w, by) in wrong_drafts.items():
        if iid not in records:
            raise SystemExit(f"wrong twin for unknown item {iid}")
        rec = records[iid]
        if rec["type"] != "factual":
            raise SystemExit(f"wrong twin for non-factual item {iid}")
        forms = four_forms(w)
        if locked(rec.get("wrong_qc")):
            if rec["wrong"] != forms:
                warnings.append(f"{iid}: wrong-twin draft changed but it is verified/edited; kept the verified text")
            continue
        rec["wrong"], rec["wrong_qc"] = forms, rec.get("wrong_qc") or dict(FRESH_QC)
        rec["wrong_drafted_by"] = by

    for iid in existing.keys() - records.keys():
        warnings.append(f"{iid}: in quadruples.jsonl but not in any draft; kept as is")
        records[iid] = existing[iid]

    final = []
    for rec in records.values():
        by = rec.pop("wrong_drafted_by", None)
        if by and by != rec["drafted_by"]:
            raise SystemExit(f"{rec['item_id']}: wrong twin drafted by a different model; record it per item")
        final.append(Quadruple.model_validate(rec).model_dump(mode="json"))

    write_jsonl(DATA / "questions.jsonl", questions)
    write_jsonl(out, final)
    write_jsonl(DATA / "wrong_twins.jsonl",
                [{"item_id": r["item_id"], "wrong": r["wrong"], "drafted_by": r["drafted_by"],
                  "wrong_qc": r["wrong_qc"]} for r in final if r["wrong"]])
    for w in warnings:
        print("WARN", w)
    n_f = sum(r["type"] == "factual" for r in final)
    print(f"wrote {len(final)} quadruples ({n_f} factual, {len(final) - n_f} open-ended), "
          f"{sum(r['wrong'] is not None for r in final)} wrong twins; {kept} verified/edited items kept unchanged")


if __name__ == "__main__":
    main()
