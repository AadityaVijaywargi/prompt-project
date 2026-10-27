import json
import math

import pytest

from lb import budget, wrong_leniency
from lb.config import experiments_config
from lb.data import load_quadruples
from lb.runners import a_wrong_pointwise
from lb.runners.common import select_shard
from scripts.check_shard import check

JUDGE = "judge-x"


def wrong_items():
    return [q for q in load_quadruples() if q.wrong_usable]


def rec(experiment, item_id, selector, corr, run_id="baseline-x"):
    parsed = {"correctness": corr, "completeness": 5, "clarity": 5, "language_quality": 5, "comment": "ok"}
    return {"run_id": run_id, "experiment": experiment, "judge": JUDGE, "prompt_variant": "baseline",
            "item_id": item_id, "forms": [selector], "order": None, "parse_ok": True, "attempt": 0, "parsed": parsed}


def run(tmp_path, recs):
    raw = tmp_path / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "x.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs), encoding="utf-8")
    return wrong_leniency.run(raw_dir=raw, tables_dir=tmp_path / "tables")


def by(rows, **match):
    return {r["form"]: r for r in rows if all(r.get(k) == v for k, v in match.items())}


def test_runner_plans_every_verified_wrong_twin_in_four_forms():
    items = load_quadruples()
    specs = a_wrong_pointwise.plan(items, [JUDGE], experiments_config())
    twins = wrong_items()
    assert len(twins) == 60 and len(specs) == 4 * len(twins)
    assert {s.forms for s in specs} == {(f"wrong:{f}",) for f in wrong_leniency.FORMS}
    assert {s.experiment for s in specs} == {"a_wrong"} and {s.kind for s in specs} == {"pointwise"}
    q, spec = twins[0], specs[0]
    assert q.wrong.en.text in spec.prompt and q.reference_en in spec.prompt   # reference-guided, as in E1


def test_false_acceptance_leniency_and_margin(tmp_path):
    twins = wrong_items()
    half = len(twins) // 2
    recs = []
    for k, q in enumerate(twins):
        recs.append(rec("a_wrong", q.item_id, "wrong:en", 1))
        recs.append(rec("a_wrong", q.item_id, "wrong:hi", 1))
        recs.append(rec("a_wrong", q.item_id, "wrong:hi_rom", 2))
        recs.append(rec("a_wrong", q.item_id, "wrong:hinglish", 4 if k < half else 1))   # half accepted
        recs += [rec("e1", q.item_id, f, 5) for f in wrong_leniency.FORMS]
    recs.append(rec("a_wrong", twins[0].item_id, "wrong:en", 5, run_id="pilot-baseline-x"))   # pilot: ignored
    out = run(tmp_path, recs)
    a1 = by(out["a_false_acceptance"])
    assert a1["en"]["rate"] == 0 and a1["hi"]["rate"] == 0 and a1["hi_rom"]["rate"] == 0
    assert a1["hinglish"]["k"] == half and a1["hinglish"]["only_form"] == half and a1["hinglish"]["only_en"] == 0
    assert a1["hinglish"]["mcnemar_p"] < 0.001 and a1["hinglish"]["diff_vs_en"] == pytest.approx(half / len(twins))
    assert math.isnan(a1["hi"]["mcnemar_p"])                      # no discordant items
    a2 = by(out["a_leniency"])
    assert a2["hi"]["mean"] == 0 and a2["hi_rom"]["mean"] == 1
    assert a2["hinglish"]["mean"] == pytest.approx(3 * half / len(twins))
    margin = by(out["a_margin"], id="A3")
    assert margin["en"]["mean"] == 4 and margin["hi_rom"]["mean"] == 3
    assert by(out["a_margin"], id="A3-diff")["hi_rom"]["mean"] == -1
    contrasts = {r["id"]: r for r in out["a_contrasts"]}
    assert contrasts["A4.1"]["mean"] == -1                        # hi minus hi_rom
    dist = by(out["a_distribution"])
    assert dist["hinglish"]["score_4"] == half and dist["hinglish"]["score_1"] == len(twins) - half
    assert all(r["missing"] == 0 for r in out["a_missing"])
    assert (tmp_path / "tables" / "main_baseline_a.md").exists()


def test_missing_calls_are_counted_and_dropped_pairwise(tmp_path):
    twins = wrong_items()
    recs = [rec("a_wrong", q.item_id, f"wrong:{f}", 1) for q in twins for f in wrong_leniency.FORMS]
    recs = [r for r in recs if not (r["item_id"] == twins[0].item_id and r["forms"] == ["wrong:hi"])]
    out = run(tmp_path, recs)
    missing = by(out["a_missing"])
    assert missing["hi"]["missing"] == 1 and missing["en"]["missing"] == 0
    assert by(out["a_leniency"])["hi"]["n"] == len(twins) - 1
    assert by(out["a_margin"], id="A3")["en"]["n"] == 0             # no E1 records: margin has no pairs


def test_no_gap_a_results_is_an_error(tmp_path):
    with pytest.raises(SystemExit, match="no main-study"):
        run(tmp_path, [rec("e1", wrong_items()[0].item_id, "en", 5)])


def test_check_shard_and_budget_know_gap_a(tmp_path):
    cfg = experiments_config()
    specs = a_wrong_pointwise.plan(select_shard(load_quadruples(), "2/4"), [JUDGE], cfg)
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "a.jsonl").write_text("".join(json.dumps(rec("a_wrong", s.item_id, s.forms[0], 1)) + "\n"
                                         for s in specs[:-1]), encoding="utf-8")
    row = check(JUDGE, "2/4", raw_dir=raw, experiments=["a_wrong"])[0]
    assert row == {"experiment": "a_wrong", "planned": len(specs), "parsed_ok": len(specs) - 1,
                   "unparsed": 0, "missing": 1}
    assert [r["experiment"] for r in check(JUDGE, "2/4", raw_dir=raw)] == ["e1", "e2", "e3"]   # default unchanged
    rows = {name: calls for name, _, calls in budget.planned_counts(cfg, 150, 60)}
    assert rows["Gap A wrong twins"] == 60 * 4 * len(cfg["experiments"]["a_wrong"]["judges"])
