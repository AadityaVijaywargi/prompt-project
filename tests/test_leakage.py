import json
import math

import pytest

from lb import leakage
from lb.data import load_quadruples
from lb.stats import bootstrap_slope_ci

JUDGE = "judge-x"


def e1(item_id, form, corr=5, lq=5, comment="Clear and correct.", run_id="baseline-x"):
    parsed = {"correctness": corr, "completeness": 5, "clarity": 5, "language_quality": lq, "comment": comment}
    return {"run_id": run_id, "experiment": "e1", "judge": JUDGE, "prompt_variant": "baseline",
            "item_id": item_id, "forms": [form], "order": None, "parse_ok": True, "parsed": parsed}


def run(tmp_path, recs):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "x.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs), encoding="utf-8")
    return leakage.run(raw_dir=raw, tables_dir=tmp_path / "tables")


def run_again(tmp_path, recs):
    """Rerun into an existing tables dir (raw records rewritten in place)."""
    raw = tmp_path / "raw"
    (raw / "x.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs), encoding="utf-8")
    return leakage.run(raw_dir=raw, tables_dir=tmp_path / "tables")


@pytest.mark.parametrize("text,mention,cat", [
    ("The Hinglish answer is correct.", True, "mixing"),
    ("Uses a code-mixed style but is accurate.", True, "mixing"),
    ("Written in Romanized Hindi, fully correct.", True, "script"),
    ("उत्तर सही है पर भाषा थोड़ी कठिन है।", True, "language"),
    ("Mentions a romance novel; correct.", False, None),
    ("Fluent and grammatical.", False, "fluency"),
    ("Clear and correct.", False, None),
    (None, False, None),
])
def test_comment_coder(text, mention, cat):
    codes = leakage.code_comment(text)
    assert codes["mention"] is mention
    if cat:
        assert codes[cat]


def test_bootstrap_slope_exact_line_and_no_variance():
    assert bootstrap_slope_ci([0, -1, -2, 0, -1, -2], [0, -2, -4, 0, -2, -4]) == (2.0, 2.0, 2.0)
    assert all(math.isnan(v) for v in bootstrap_slope_ci([1, 1, 1, 1], [0, 1, 2, 3]))


def test_leakage_slope_one_when_correctness_tracks_language_quality(tmp_path):
    items = load_quadruples()
    recs = [e1(q.item_id, "en") for q in items]
    recs += [e1(q.item_id, "hi", corr=5 - k % 3, lq=5 - k % 3) for k, q in enumerate(items)]
    recs += [e1(q.item_id, "hi_rom", corr=4, lq=3) for q in items]            # dL constant: not estimable
    recs.append(e1(items[0].item_id, "hi", corr=1, lq=1, run_id="pilot-baseline-x"))   # pilot: ignored
    out = run(tmp_path, recs)
    b1 = {r["form"]: r for r in out["b_leakage"] if r["id"] == "B1"}
    assert b1["hi"]["n"] == len(items) and b1["hi"]["slope"] == pytest.approx(1.0)
    assert b1["hi"]["ci_low"] == pytest.approx(1.0) and b1["hi"]["ci_high"] == pytest.approx(1.0)
    assert not b1["hi_rom"]["estimable"] and b1["hinglish"]["n"] == 0
    zero = next(r for r in out["b_by_sign"] if r["form"] == "hi" and r["dL_sign"] == "dL = 0")
    assert zero["mean_dC"] == 0 and zero["n"] == sum(1 for k in range(len(items)) if k % 3 == 0)
    assert (tmp_path / "tables" / "main_baseline_b.md").exists()


def test_mention_rate_mcnemar_and_silent_penalty(tmp_path):
    items = load_quadruples()
    half = len(items) // 2
    recs = [e1(q.item_id, "en") for q in items]
    # every hi comment names the language; the first half also lose a correctness point
    recs += [e1(q.item_id, "hi", corr=4 if k < half else 5, comment="Correct, but written in Hindi.")
             for k, q in enumerate(items)]
    # hinglish loses a point everywhere without ever naming language, script or mixing
    recs += [e1(q.item_id, "hinglish", corr=4, comment="Slightly imprecise.") for q in items]
    rows = run(tmp_path, recs)["b_comments"]
    get = {(r["id"], r["form"]): r for r in rows if r["id"] in ("B4", "B5")}
    assert get[("B4", "en")]["rate"] == 0
    assert get[("B4", "hi")]["rate"] == 1 and get[("B4", "hi")]["only_form"] == len(items)
    assert get[("B4", "hi")]["mcnemar_p"] < 0.001
    assert get[("B5", "hi")]["n"] == half and get[("B5", "hi")]["rate"] == 0
    assert get[("B5", "hinglish")]["n"] == len(items) and get[("B5", "hinglish")]["rate"] == 1


def test_comment_sample_is_seeded_and_capped(tmp_path):
    items = load_quadruples()
    recs = [e1(q.item_id, f, comment=f"{q.item_id} {f}") for q in items for f in ("en", "hi", "hi_rom", "hinglish")]
    run(tmp_path, recs)
    first = (tmp_path / "tables" / "main_baseline_b_comment_sample.csv").read_text(encoding="utf-8")
    again = tmp_path / "again"
    again.mkdir()
    run(again, recs)
    second = (again / "tables" / "main_baseline_b_comment_sample.csv").read_text(encoding="utf-8")
    assert first == second
    assert len(first.strip().splitlines()) == 1 + 4 * min(leakage.SAMPLE_PER_CELL, len(items))


def test_comment_sample_does_not_depend_on_judge_order():
    calls = {("e1", j, q.item_id, (f,), None): {"comment": f"{j} {q.item_id} {f}"}
             for j in ("a", "b") for q in load_quadruples() for f in ("en", "hi", "hi_rom", "hinglish")}
    key = lambda rows: sorted((r["judge"], r["item_id"], r["form"]) for r in rows)
    items = load_quadruples()
    assert key(leakage.comment_sample(calls, ["a", "b"], items)) == key(leakage.comment_sample(calls, ["b", "a"], items))


def hi_comments(items):
    """en comments never mention language; hi comments alternate between naming Hindi and not."""
    recs = [e1(q.item_id, "en") for q in items]
    return recs + [e1(q.item_id, "hi", comment="Correct, in Hindi." if k % 2 else "Reads oddly but correct.")
                   for k, q in enumerate(items)]


def test_rerun_keeps_a_human_coded_sample_and_scores_the_coder(tmp_path):
    recs = hi_comments(load_quadruples())
    run(tmp_path, recs)
    path = tmp_path / "tables" / "main_baseline_b_comment_sample.csv"
    sample = leakage.read_sample(path)
    # human agrees with the coder everywhere except: says yes to every "Reads oddly" hi comment (coder misses)
    for r in sample:
        r["human_mention"] = "1" if r["form"] == "hi" else ("yes" if r["coder_mention"] == "True" else "no")
    leakage.write_csv(path, sample)
    coded = path.read_text(encoding="utf-8")

    out = run_again(tmp_path, recs)
    assert path.read_text(encoding="utf-8") == coded          # human coding survives the rerun
    check = {r["measure"]: r for r in out["b_coder_check"] if r["judge"] == "all"}
    hits = sum(r["coder_mention"] == "True" for r in sample)
    misses = sum(r["form"] == "hi" and r["coder_mention"] == "False" for r in sample)
    assert check["precision"]["coded"] == len(sample)
    assert check["precision"]["rate"] == 1 and check["precision"]["fp"] == 0
    assert check["recall"]["k"] == hits and check["recall"]["n"] == hits + misses and misses > 0
    assert "validated by the coder check" in (tmp_path / "tables" / "main_baseline_b.md").read_text(encoding="utf-8")


def test_uncoded_sample_reports_unvalidated_and_rejects_bad_labels(tmp_path):
    recs = hi_comments(load_quadruples())
    out = run(tmp_path, recs)
    assert all(r["coded"] == 0 for r in out["b_coder_check"])
    md = (tmp_path / "tables" / "main_baseline_b.md").read_text(encoding="utf-8")
    assert "unvalidated: 0 of" in md
    path = tmp_path / "tables" / "main_baseline_b_comment_sample.csv"
    sample = leakage.read_sample(path)
    sample[0]["human_mention"] = "maybe"
    leakage.write_csv(path, sample)
    with pytest.raises(ValueError, match="human_mention"):
        run_again(tmp_path, recs)
