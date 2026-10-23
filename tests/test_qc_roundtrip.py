import csv
import json
from datetime import date

import pytest
from pydantic import ValidationError

from conftest import forms
from lb import qc
from lb.schema import Quadruple

FRESH = {"verified_by": [], "verified_on": None, "edits": 0, "passed": False, "notes": ""}


def setup(tmp_path, monkeypatch, record):
    path = tmp_path / "quadruples.jsonl"
    path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    monkeypatch.setattr(qc, "QUADRUPLES", path)
    monkeypatch.setattr(qc, "QUESTIONS", tmp_path / "missing.jsonl")
    return path, tmp_path / "to_verify.csv"


def read_rows(sheet):
    with open(sheet, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_rows(sheet, rows):
    with open(sheet, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=qc.COLUMNS)
        w.writeheader()
        w.writerows(rows)


def test_export_edit_import(tmp_path, monkeypatch, quad_record):
    path, sheet = setup(tmp_path, monkeypatch, quad_record)
    assert qc.export(sheet) == 3                       # hi, hi_rom, hinglish
    assert sheet.read_bytes().startswith(b"\xef\xbb\xbf")   # BOM so Excel shows Devanagari

    rows = read_rows(sheet)
    for r in rows:
        r.update(ok="Y", verified_by="a1")
    rows[0]["corrected_text"] = "ऑस्ट्रेलिया की राजधानी कैनबरा है, सिडनी नहीं।"
    rows[1]["ok"] = ""                                 # one row not yet checked
    write_rows(sheet, rows)

    qc.import_(sheet, on=date(2026, 10, 30))
    rec = json.loads(path.read_text("utf-8"))
    assert rec["answers"]["hi"]["text"].endswith("सिडनी नहीं।")
    assert rec["answers"]["hi"]["words"] == 7
    assert rec["qc"]["edits"] == 1 and not rec["qc"]["passed"]

    rows[1]["ok"] = "Y"
    rows[0]["corrected_text"] = ""
    write_rows(sheet, rows)
    qc.import_(sheet, on=date(2026, 10, 30))
    rec = json.loads(path.read_text("utf-8"))
    assert rec["qc"]["passed"] and rec["qc"]["verified_by"] == ["a1"]
    assert rec["qc"]["verified_on"] == "2026-10-30"
    assert rec["answers"]["hi"]["text"].endswith("सिडनी नहीं।")   # earlier edit kept


def test_wrong_twin_verified_separately(tmp_path, monkeypatch, quad_record):
    passed = {"verified_by": ["a1"], "verified_on": "2026-10-30", "edits": 0, "passed": True, "notes": ""}
    wrong = forms(en="The capital of Australia is Sydney.", hi="ऑस्ट्रेलिया की राजधानी सिडनी है।",
                  hi_rom="Australia ki rajdhani Sydney hai.", hinglish="Australia ki capital Sydney hai.")
    path, sheet = setup(tmp_path, monkeypatch, dict(quad_record, qc=passed, wrong=wrong, wrong_qc=dict(FRESH)))

    assert qc.export(sheet) == 3                       # answers already passed: only wrong.* rows
    rows = read_rows(sheet)
    assert {r["field"] for r in rows} == {"wrong.hi", "wrong.hi_rom", "wrong.hinglish"}
    for r in rows:
        r.update(ok="Y", verified_by="a2")
    write_rows(sheet, rows)
    qc.import_(sheet, on=date(2026, 11, 2))
    rec = Quadruple.model_validate(json.loads(path.read_text("utf-8")))
    assert rec.wrong_usable and rec.wrong_qc.verified_by == ["a2"]
    assert rec.qc.verified_by == ["a1"] and rec.qc.verified_on == date(2026, 10, 30)   # untouched


def test_wrong_requires_wrong_qc_and_factual(quad_record):
    with pytest.raises(ValidationError, match="together"):
        Quadruple.model_validate(dict(quad_record, wrong=forms()))
    with pytest.raises(ValidationError, match="factual"):
        Quadruple.model_validate(dict(quad_record, type="open_ended", wrong=forms(), wrong_qc=dict(FRESH)))
