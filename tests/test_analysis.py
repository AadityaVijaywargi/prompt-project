import json

import pytest

from lb import analysis
from lb.data import load_quadruples

JUDGE = "judge-x"


def e1(item_id, form, score, run_id="baseline-x"):
    return {"run_id": run_id, "experiment": "e1", "judge": JUDGE, "prompt_variant": "baseline",
            "item_id": item_id, "forms": [form], "order": None, "parse_ok": True,
            "parsed": {c: score for c in analysis.CRITERIA}}


def pw(exp, item_id, forms, order, winner):
    return {"run_id": "baseline-x", "experiment": exp, "judge": JUDGE, "prompt_variant": "baseline",
            "item_id": item_id, "forms": list(forms), "order": order, "parse_ok": True,
            "parsed": {"winner": winner}}


def run(tmp_path, recs):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "x.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
    return analysis.run(raw_dir=raw, tables_dir=tmp_path / "tables", thresholds_path=tmp_path / "thr.json")


@pytest.mark.parametrize("winner,order,expected", [
    ("A", "AB", "en"), ("B", "AB", "hi"), ("A", "BA", "hi"), ("B", "BA", "en"), ("tie", "BA", "tie")])
def test_slot_verdict_maps_to_form(winner, order, expected):
    assert analysis.underlying_winner(winner, order, "en", "hi") == expected


def test_e1_gap_excludes_pilot_and_counts_missing(tmp_path):
    items = load_quadruples()
    recs = [e1(q.item_id, "en", 5) for q in items] + [e1(q.item_id, "hi", 3) for q in items[1:]]
    recs.append(e1(items[0].item_id, "hi", 1, run_id="pilot-baseline-x"))   # pilot: must be ignored
    out = run(tmp_path, recs)
    row = next(r for r in out["e1"] if r["id"] == "E1.1" and r["measure"] == "content")
    assert row["n"] == len(items) - 1 and row["mean_d"] == -2 and row["ci_low"] == row["ci_high"] == -2
    missing = {r["form"]: r["missing"] for r in out["e1_missing"]}
    assert missing == {"en": 0, "hi": 1, "hi_rom": len(items), "hinglish": len(items)}
    assert out["thresholds"][JUDGE] == {"p95_abs_content_gap": 2.0, "n_pairs": len(items) - 1}
    assert (tmp_path / "tables" / "main_baseline.md").exists()


def test_e1_bootstrap_resamples_items_not_rows(tmp_path):
    # Scores differ a lot between items but en and hi agree within every item. Resampling whole items keeps
    # each pair together, so the CI is exactly 0; resampling form rows independently would make it wide.
    items = load_quadruples()
    recs = [e1(q.item_id, form, 1 + i % 5) for i, q in enumerate(items) for form in ("en", "hi")]
    row = next(r for r in run(tmp_path, recs)["e1"] if r["id"] == "E1.1" and r["measure"] == "content")
    assert row["n"] == len(items) and row["mean_d"] == row["ci_low"] == row["ci_high"] == 0


def test_e2_slot_a_always_wins(tmp_path):
    items = load_quadruples()
    recs = [pw("e2", q.item_id, ("en", "hi"), o, "A") for q in items for o in ("AB", "BA")]
    rows = {r["id"]: r for r in run(tmp_path, recs)["e2"] if r["pair"] == "en vs hi"}
    assert rows["E2.1"]["rate"] == 0.5 and rows["E2.1"]["n"] == 2 * len(items)
    assert rows["E2.4"]["rate"] == 1.0
    assert rows["E2.3"]["rate"] == 0.0 and rows["E2.5"]["n"] == 0


def test_e3_rates_need_both_orders(tmp_path):
    items = [q for q in load_quadruples() if q.wrong_usable]
    recs = [pw("e3", q.item_id, ("wrong:en", "hi"), "AB", "A") for q in items]        # wrong wins in AB
    recs += [pw("e3", q.item_id, ("wrong:en", "hi"), "BA", "A") for q in items[1:]]   # correct hi wins in BA
    rows = [r for r in run(tmp_path, recs)["e3"] if r["form"] == "hi"]
    any_order, consistent = rows
    assert any_order["n"] == len(items) - 1 and any_order["rate"] == 1.0
    assert consistent["rate"] == 0.0
