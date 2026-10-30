import json
import random
from collections import Counter

import pytest

from lb import e4
from lb.config import experiments_config
from lb.data import load_quadruples
from lb.runners.e5_mitigation import subset_for
from lb.schema import FORMS
from lb.stats import bootstrap_agreement_ci, bootstrap_agreement_diff_ci, quadratic_weighted_kappa, spearman

JUDGE = "judge-x"


@pytest.fixture(scope="module")
def items():
    return load_quadruples()


@pytest.fixture(scope="module")
def sample(items):
    return e4.e4_sample(items, experiments_config())


def test_sample_holds_the_e5_subset_and_keeps_the_type_mix(items, sample):
    cfg = experiments_config()
    ids = {q.item_id for q in sample}
    assert len(sample) == 100 and ids >= {q.item_id for q in subset_for(cfg, items)}
    assert Counter(q.type for q in sample) == {"factual": 67, "open_ended": 33}
    assert [q.item_id for q in sample] == [q.item_id for q in e4.e4_sample(items, cfg)]   # seeded
    assert len({q.subject for q in sample}) >= 20


def test_layout_is_blind_balanced_and_differs_per_annotator(sample):
    rows = e4.layout(sample, "a1")
    assert len(rows) == 400 and len({(i, f) for _, i, f in rows}) == 400        # every (item, form) once
    for b in range(4):
        block = rows[b * 100:(b + 1) * 100]
        assert len({i for _, i, _ in block}) == 100                             # each item once per block
        assert Counter(f for _, _, f in block) == {f: 25 for f in FORMS}         # forms balanced per block
    assert [r[1:] for r in rows] != [r[1:] for r in e4.layout(sample, "a2")]
    assert rows == e4.layout(sample, "a1")
    sheet = e4.sheet_rows(sample, "a1", experiments_config())
    assert list(sheet[0]) == e4.SHEET_COLUMNS and not {"item_id", "form"} & set(sheet[0])


def graded(sample, annotator, score=lambda item_id, form: 4):
    rows = e4.sheet_rows(sample, annotator, experiments_config())
    key = {r: (i, f) for r, i, f in e4.layout(sample, annotator)}
    for r in rows:
        v = score(*key[r["row_id"]])
        if v is not None:
            r.update({c: str(v) for c in e4.CRITERIA})
    return rows


def test_import_maps_rows_back_and_rejects_bad_rows(items, sample, tmp_path):
    rows = graded(sample, "a1", lambda i, f: 5 if f == "en" else (None if f == "hinglish" else 3))
    rows[0]["answer"] = rows[0]["answer"].replace(" ", "\n  ")                  # rewrapped by a spreadsheet: fine
    sheet, grades = tmp_path / "sheet_a1.csv", tmp_path / "human_grades.csv"
    e4.write_sheet(sheet, rows, e4.SHEET_COLUMNS)
    out = e4.import_sheet(sheet, grades, items)
    assert len(out) == 300 and {g.form for g in out} == {"en", "hi", "hi_rom"}
    assert all(g.correctness == (5 if g.form == "en" else 3) for g in out)
    assert len(e4.load_grades(grades)) == 300
    e4.import_sheet(sheet, grades, items)                                      # re-import replaces, not appends
    assert len(e4.load_grades(grades)) == 300

    bad = [dict(r) for r in rows]
    bad[1]["correctness"], bad[2]["clarity"], bad[3]["answer"] = "6", "", "something else"
    with pytest.raises(SystemExit) as e:
        e4.parse_sheet(bad, items)
    msg = str(e.value)
    assert "a1-002" in msg and "a1-003" in msg and "a1-004" in msg
    swapped = [dict(r) for r in rows]
    swapped[0]["answer"], swapped[1]["answer"] = rows[1]["answer"], rows[0]["answer"]   # rows sorted by hand
    with pytest.raises(SystemExit, match="answer text differs"):
        e4.parse_sheet(swapped, items)


def test_grade_values():
    assert e4.grade_value("4") == 4 and e4.grade_value(" 4.0 ") == 4 and e4.grade_value("") is None
    for v in ("0", "6", "3.5", "four"):
        with pytest.raises(ValueError):
            e4.grade_value(v)
    assert [e4.round_half_up(x) for x in (2.5, 3.5, 4.49, 4.5)] == [3, 4, 4, 5]


def test_vectorised_agreement_matches_the_scalar_versions():
    rng = random.Random(1)
    a = [rng.randint(1, 5) for _ in range(80)]
    b = [min(5, max(1, x + rng.choice((-1, 0, 0, 1)))) for x in a]
    k, lo, hi = bootstrap_agreement_ci("qwk", a, b, n_boot=500)
    assert k == pytest.approx(quadratic_weighted_kappa(a, b)) and lo <= k <= hi
    r, lo, hi = bootstrap_agreement_ci("spearman", a, b, n_boot=500)
    assert r == pytest.approx(spearman(a, b)) and lo <= r <= hi
    assert bootstrap_agreement_ci("qwk", [5] * 10, [5] * 10, n_boot=50)[0] != bootstrap_agreement_ci(
        "qwk", [5] * 10, [5] * 10, n_boot=50)[0]                                 # no variance: NaN, not 1
    new, base, diff, lo, hi = bootstrap_agreement_diff_ci("qwk", a, a, a, b, n_boot=500)
    assert new == 1 and diff == pytest.approx(1 - base) and lo <= diff <= hi


def e1_rec(item_id, form, score):
    return {"run_id": "baseline-x", "experiment": "e1", "judge": JUDGE, "prompt_variant": "baseline",
            "item_id": item_id, "forms": [form], "order": None, "parse_ok": True,
            "parsed": {c: score for c in e4.CRITERIA} | {"comment": ""}}


def test_tables_from_two_annotators_and_a_judge(items, sample, tmp_path):
    quality = {q.item_id: 2 + k % 4 for k, q in enumerate(sample)}            # 2-5, varies across items
    human = lambda i, f: quality[i] - (f == "hinglish")                        # humans: hinglish one point lower
    for a in ("a1", "a2"):
        e4.write_sheet(tmp_path / f"sheet_{a}.csv", graded(sample, a, human), e4.SHEET_COLUMNS)
        e4.import_sheet(tmp_path / f"sheet_{a}.csv", tmp_path / "grades.csv", items)
    raw = tmp_path / "raw"
    raw.mkdir()
    judge = lambda i, f: {"en": quality[i], "hinglish": 7 - quality[i]}.get(f, 5)   # hi, hi_rom: always 5
    recs = [e1_rec(q.item_id, f, judge(q.item_id, f)) for q in sample for f in FORMS]
    (raw / "x.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
    t = e4.run(tmp_path / "grades.csv", raw, tmp_path / "tables", items)

    assert all(r["agreement"] == 1 for r in t["e4_iaa"]) and len(t["e4_iaa"]) == 16    # identical annotators
    jh = {(r["form"], r["score"]): r for r in t["e4_judge_human"]}
    assert jh[("en", "content")]["agreement"] == pytest.approx(1) and jh[("en", "content")]["n"] == 100
    assert jh[("hi", "content")]["agreement"] != jh[("hi", "content")]["agreement"]    # judge constant: NaN
    drop = {(r["comparison"], r["score"]): r for r in t["e4_form_drop"]}
    assert drop[("hinglish vs en", "content")]["change"] == pytest.approx(-2)   # rank order reversed
    gap = {(r["who"], r["comparison"]): r for r in t["e4_form_gap"]}
    assert gap[("human (mean)", "hinglish vs en")]["mean_d"] == pytest.approx(-1)
    assert gap[(JUDGE, "hinglish vs en")]["mean_d"] == pytest.approx(0)
    assert (tmp_path / "tables" / "main_baseline_e4.md").exists()


def test_tables_without_grades(items, tmp_path):
    t = e4.run(tmp_path / "none.csv", tmp_path, tmp_path / "tables", items)
    assert t["e4_iaa"] == [] and all(r["graded"] == 0 for r in t["e4_coverage"])
    assert "No human grades yet" in (tmp_path / "tables" / "main_baseline_e4.md").read_text(encoding="utf-8")
