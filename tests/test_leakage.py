import json
import math

import pytest

from lb import leakage
from lb.data import load_quadruples
from lb.stats import bootstrap_slope_ci, cohen_kappa_binary_ci, kendall_tau_b

JUDGE = "judge-x"


def e1(item_id, form, corr=5, lq=5, comment="Clear and correct.", run_id="baseline-x", **crit):
    parsed = {"correctness": corr, "completeness": 5, "clarity": 5, "language_quality": lq, "comment": comment,
              **crit}
    return {"run_id": run_id, "experiment": "e1", "judge": JUDGE, "prompt_variant": "baseline",
            "item_id": item_id, "forms": [form], "order": None, "parse_ok": True, "parsed": parsed}


def write_raw(tmp_path, recs):
    raw = tmp_path / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "x.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs), encoding="utf-8")
    return raw


def run(tmp_path, recs):
    """Run section B into tmp_path/tables; rerunning into the same tmp_path keeps the existing tables."""
    return leakage.run(raw_dir=write_raw(tmp_path, recs), tables_dir=tmp_path / "tables")


def rows(out, table, **match):
    return [r for r in out[table] if all(r.get(k) == v for k, v in match.items())]


@pytest.mark.parametrize("text,lexicon,mention,cat", [
    ("The Hinglish answer is correct.", "v1", True, "mixing"),
    ("Uses a code-mixed style but is accurate.", "v1", True, "mixing"),
    ("Written in Romanized Hindi, fully correct.", "v1", True, "script"),
    ("उत्तर सही है पर भाषा थोड़ी कठिन है।", "v1", True, "language"),
    ("Mentions a romance novel; correct.", "v1", False, None),
    ("Fluent and grammatical.", "v1", False, "fluency"),
    ("Clear and correct.", "v1", False, None),
    (None, "v1", False, None),
    ("全面准确，语言流畅自然。", "v1", False, None),            # the fixed lexicon cannot read Chinese
    ("全面准确，语言流畅自然。", "v1+zh", True, "language"),
    ("准确解释了罗马帝国的衰落。", "v1+zh", False, None),        # Roman Empire is not a script mention
    ("表达清晰流畅。", "v1+zh", False, "fluency"),
    ("Written in Romanized Hindi, fully correct.", "v1+zh", True, "script"),
])
def test_comment_coder(text, lexicon, mention, cat):
    codes = leakage.code_comment(text, lexicon)
    assert codes["mention"] is mention
    if cat:
        assert codes[cat]


def test_bootstrap_slope_exact_line_and_no_variance():
    assert bootstrap_slope_ci([0, -1, -2, 0, -1, -2], [0, -2, -4, 0, -2, -4]) == (2.0, 2.0, 2.0)
    assert all(math.isnan(v) for v in bootstrap_slope_ci([1, 1, 1, 1], [0, 1, 2, 3]))


def test_kendall_and_kappa_helpers():
    tau, p = kendall_tau_b([0, -1, -2, 0, -1, -2, 1], [0, -2, -4, 0, -2, -4, 1])
    assert tau == pytest.approx(1.0) and p < 0.05
    assert all(math.isnan(v) for v in kendall_tau_b([1, 2, 3, 4], [5, 5, 5, 5]))
    assert cohen_kappa_binary_ci([1, 0, 1, 0], [1, 0, 1, 0])[0] == pytest.approx(1.0)
    # po = 0.75, pe = 0.5 -> kappa 0.5
    assert cohen_kappa_binary_ci([1, 1, 0, 0], [1, 0, 0, 0])[0] == pytest.approx((0.75 - 0.5) / 0.5)
    assert math.isnan(cohen_kappa_binary_ci([1, 1, 1], [1, 1, 1])[0])


def test_leakage_slope_one_when_correctness_tracks_language_quality(tmp_path):
    items = load_quadruples()
    recs = [e1(q.item_id, "en") for q in items]
    recs += [e1(q.item_id, "hi", corr=5 - k % 3, lq=5 - k % 3) for k, q in enumerate(items)]
    recs += [e1(q.item_id, "hi_rom", corr=4, lq=3) for q in items]            # dL constant: not estimable
    recs.append(e1(items[0].item_id, "hi", corr=1, lq=1, run_id="pilot-baseline-x"))   # pilot: ignored
    out = run(tmp_path, recs)
    b1 = {r["form"]: r for r in rows(out, "b_leakage", id="B1", subset="all")}
    assert b1["hi"]["n"] == len(items) and b1["hi"]["slope"] == pytest.approx(1.0)
    assert b1["hi"]["ci_low"] == pytest.approx(1.0) and b1["hi"]["ci_high"] == pytest.approx(1.0)
    assert b1["hi"]["kendall_tau"] == pytest.approx(1.0) and b1["hi"]["same_move"] == b1["hi"]["moved"] > 0
    assert not b1["hi_rom"]["estimable"] and b1["hinglish"]["n"] == 0
    assert "holm_p" in b1["hi"]
    zero = rows(out, "b_by_sign", subset="all", form="hi", dL_sign="dL = 0")[0]
    assert zero["mean_dC"] == 0 and zero["n"] == sum(1 for k in range(len(items)) if k % 3 == 0)
    assert (tmp_path / "tables" / "main_baseline_b.md").exists()


def test_item_type_split_partitions_items_and_flags_a_constant_criterion(tmp_path):
    items = load_quadruples()
    factual = {q.item_id for q in items if q.type == "factual"}
    recs = [e1(q.item_id, "en") for q in items]
    # factual items keep correctness at 5 (a ceiling); open-ended correctness follows language_quality
    recs += [e1(q.item_id, "hi", lq=5 - k % 2, corr=5 if q.item_id in factual else 5 - k % 2)
             for k, q in enumerate(items)]
    out = run(tmp_path, recs)
    b1 = {r["subset"]: r for r in rows(out, "b_leakage", id="B1", form="hi")}
    assert b1["factual"]["n"] + b1["open_ended"]["n"] == b1["all"]["n"] == len(items)
    assert b1["factual"]["y_constant"] and math.isnan(b1["factual"]["kendall_tau"])
    assert b1["open_ended"]["slope"] == pytest.approx(1.0)
    assert "holm_p" not in b1["factual"]                      # Holm covers the planned pooled rows only
    md = (tmp_path / "tables" / "main_baseline_b.md").read_text(encoding="utf-8")
    assert "(criterion constant)" in md


def test_halo_baseline_and_copy_check(tmp_path):
    items = load_quadruples()
    # English: clarity always equals language_quality (a copy); correctness does not follow it
    recs = [e1(q.item_id, "en", corr=4 + k % 2, lq=3 + k % 3, clarity=3 + k % 3) for k, q in enumerate(items)]
    out = run(tmp_path, recs)
    halo = {r["criterion"]: r for r in rows(out, "b_halo", subset="all")}
    assert halo["clarity"]["slope"] == pytest.approx(1.0) and halo["clarity"]["degenerate"]
    assert not halo["correctness"]["degenerate"]
    copies = {r["criterion"]: r for r in out["b_copy"]}
    assert copies["clarity"]["rate"] == 1 and copies["clarity"]["degenerate"]
    assert copies["correctness"]["rate"] < leakage.DEGENERATE_SHARE and not copies["correctness"]["degenerate"]
    assert "clarity (copies LQ)" in (tmp_path / "tables" / "main_baseline_b.md").read_text(encoding="utf-8")


def test_mention_rate_mcnemar_and_silent_penalty(tmp_path):
    items = load_quadruples()
    half = len(items) // 2
    recs = [e1(q.item_id, "en") for q in items]
    # every hi comment names the language; the first half also lose a correctness point
    recs += [e1(q.item_id, "hi", corr=4 if k < half else 5, comment="Correct, but written in Hindi.")
             for k, q in enumerate(items)]
    # hinglish loses a point everywhere without ever naming language, script or mixing
    recs += [e1(q.item_id, "hinglish", corr=4, comment="Slightly imprecise.") for q in items]
    out = run(tmp_path, recs)
    get = {(r["id"], r["form"]): r for r in rows(out, "b_comments", lexicon="v1") if r["id"] in ("B4", "B5")}
    assert get[("B4", "en")]["rate"] == 0
    assert get[("B4", "hi")]["rate"] == 1 and get[("B4", "hi")]["only_form"] == len(items)
    assert get[("B4", "hi")]["mcnemar_p"] < 0.001
    assert get[("B5", "hi")]["n"] == half and get[("B5", "hi")]["rate"] == 0
    assert get[("B5", "hinglish")]["n"] == len(items) and get[("B5", "hinglish")]["rate"] == 1


def test_chinese_comments_counted_and_only_v1_zh_reads_them(tmp_path):
    items = load_quadruples()
    recs = [e1(q.item_id, "en") for q in items]
    recs += [e1(q.item_id, "hi", comment="全面准确，语言流畅自然。") for q in items]
    out = run(tmp_path, recs)
    written = {r["form"]: r for r in out["b_comment_language"]}
    assert written["hi"]["rate"] == 1 and written["en"]["rate"] == 0
    b4 = {r["lexicon"]: r for r in rows(out, "b_comments", id="B4", form="hi")}
    assert b4["v1"]["rate"] == 0 and b4["v1+zh"]["rate"] == 1


def test_comment_sample_is_seeded_capped_and_blind(tmp_path):
    items = load_quadruples()
    recs = [e1(q.item_id, f, comment=f"{q.item_id} {f}") for q in items for f in ("en", "hi", "hi_rom", "hinglish")]
    run(tmp_path / "a", recs)
    run(tmp_path / "b", recs)
    first, second = ((tmp_path / d / "tables" / "main_baseline_b_comment_sample.csv").read_text(encoding="utf-8")
                     for d in ("a", "b"))
    assert first == second
    assert len(first.strip().splitlines()) == 1 + 4 * min(leakage.SAMPLE_PER_CELL, len(items))
    assert first.splitlines()[0] == "judge,item_id,form,comment,rater_a,rater_b,adjudicated"


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


def test_two_raters_kappa_adjudication_and_rerun_keeps_labels(tmp_path):
    recs = hi_comments(load_quadruples())
    run(tmp_path, recs)
    path = tmp_path / "tables" / "main_baseline_b_comment_sample.csv"
    sample = leakage.read_sample(path)
    hi = [r for r in sample if r["form"] == "hi"]
    for r in sample:
        named = "Hindi" in r["comment"]
        r["rater_a"] = "1" if named or r["form"] == "hi" else "0"   # rater a: every hi comment is a mention
        r["rater_b"] = "yes" if named else "no"                     # rater b: only when Hindi is named
    hi[0]["adjudicated"] = "1" if "Hindi" in hi[0]["comment"] else "0"   # one disagreement resolved, if any
    leakage.write_csv(path, sample)
    labelled = path.read_text(encoding="utf-8")

    out = run(tmp_path, recs)
    assert path.read_text(encoding="utf-8") == labelled              # human labels survive the rerun
    disagree = [r for r in hi if "Hindi" not in r["comment"]]
    agreement = rows(out, "b_rater_agreement", judge="all")[0]
    assert agreement["both_coded"] == len(sample) and agreement["agree"] == len(sample) - len(disagree)
    resolved = 1 if hi[0] in disagree else 0
    assert agreement["agreed_labels"] == len(sample) - len(disagree) + resolved
    assert -1 <= agreement["kappa"] < 1
    check = {r["measure"]: r for r in rows(out, "b_coder_check", judge="all", lexicon="v1")}
    assert check["precision"]["rate"] == 1 and check["recall"]["rate"] == 1   # agreed labels match "Hindi"
    md = (tmp_path / "tables" / "main_baseline_b.md").read_text(encoding="utf-8")
    assert ("validated by the two-rater check" in md) is (len(disagree) == resolved)


def test_uncoded_sample_is_unvalidated_and_bad_or_old_labels_are_refused(tmp_path):
    recs = hi_comments(load_quadruples())
    out = run(tmp_path, recs)
    assert all(r["agreed_labels"] == 0 for r in out["b_rater_agreement"])
    assert "unvalidated: 0 of" in (tmp_path / "tables" / "main_baseline_b.md").read_text(encoding="utf-8")
    path = tmp_path / "tables" / "main_baseline_b_comment_sample.csv"
    sample = leakage.read_sample(path)
    sample[0]["rater_a"] = "maybe"
    leakage.write_csv(path, sample)
    with pytest.raises(ValueError, match="labels must be"):
        run(tmp_path, recs)
    old = [{"judge": r["judge"], "item_id": r["item_id"], "form": r["form"], "comment": r["comment"],
            "human_mention": "1"} for r in sample]
    leakage.write_csv(path, old)
    with pytest.raises(SystemExit, match="older format"):
        run(tmp_path, recs)
    assert leakage.read_sample(path)[0]["human_mention"] == "1"       # old labels are not overwritten
