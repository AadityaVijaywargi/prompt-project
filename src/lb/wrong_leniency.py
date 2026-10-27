"""Gap A of analysis/plan.md: error-detection leniency on matched wrong answers (A1-A4).

    python -m lb.wrong_leniency                    # every judge with main (non-pilot) baseline gap A results
    python -m lb.wrong_leniency --judges qwen2.5-7b-local

Reads the a_wrong records (each verified wrong twin scored pointwise in all four forms) and, for the
discrimination margin, the E1 baseline score of the same item's correct answer in the same form. Writes
results/tables/main_<variant>_a_*.csv and a markdown summary main_<variant>_a.md. No judge calls.
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from .analysis import SEED, exploratory, fmt, judges_in, load_calls, prop, pval, write_csv
from .config import RAW, TABLES
from .data import load_quadruples
from .stats import binom_test_half, holm, paired_bootstrap_ci, wilcoxon_p

EXPERIMENT = "a_wrong"
FORMS = ("en", "hi", "hi_rom", "hinglish")
NON_EN = FORMS[1:]
# Fixed in analysis/plan.md (gap A) before any gap A call: a wrong twin is falsely accepted when its
# correctness score is at least this (1 = wrong, 5 = fully correct on the rubric).
ACCEPT_AT = 3
CONTRASTS = (("A4.1", "hi", "hi_rom"), ("A4.2", "hi_rom", "hinglish"))   # script, then mixing


def wrong_scores(calls: dict, judge: str, items) -> dict:
    """{item_id: {form: correctness}} for parsed wrong-twin calls."""
    out = {}
    for q in items:
        for form in FORMS:
            p = calls.get((EXPERIMENT, judge, q.item_id, (f"wrong:{form}",), None))
            if p is not None:
                out.setdefault(q.item_id, {})[form] = p["correctness"]
    return out


def correct_scores(calls: dict, judge: str, items) -> dict:
    """{item_id: {form: correctness}} for the same items' correct answers in E1."""
    out = {}
    for q in items:
        for form in FORMS:
            p = calls.get(("e1", judge, q.item_id, (form,), None))
            if p is not None:
                out.setdefault(q.item_id, {})[form] = p["correctness"]
    return out


def mean_row(diffs: list[float]) -> dict:
    mean, lo, hi = paired_bootstrap_ci(diffs, seed=SEED)
    return {"n": len(diffs), "mean": mean, "ci_low": lo, "ci_high": hi, "exploratory": exploratory(len(diffs))}


def analyse(calls: dict, judges: list[str], items) -> dict:
    items = [q for q in items if q.wrong_usable]
    missing, dist, a1, a2, a3, a4 = [], [], [], [], [], []
    for j in judges:
        w, c = wrong_scores(calls, j, items), correct_scores(calls, j, items)
        for form in FORMS:
            scored = [s[form] for s in w.values() if form in s]
            missing.append({"judge": j, "form": form, "planned": len(items), "missing": len(items) - len(scored)})
            counts = Counter(scored)
            dist.append({"judge": j, "form": form, **{f"score_{k}": counts.get(k, 0) for k in range(1, 6)}})
            a1.append({"judge": j, "id": "A1", "form": form, **prop(sum(v >= ACCEPT_AT for v in scored), len(scored))})
            m = [c[i][form] - s[form] for i, s in w.items() if form in s and form in c.get(i, {})]
            a3.append({"judge": j, "id": "A3", "form": form, "measure": "margin (correct minus wrong)", **mean_row(m)})
        en = a1[-4]
        for r in a1[-3:]:
            paired = [s for s in w.values() if r["form"] in s and "en" in s]
            only_f = sum(s[r["form"]] >= ACCEPT_AT > s["en"] for s in paired)
            only_en = sum(s["en"] >= ACCEPT_AT > s[r["form"]] for s in paired)
            r.update({"diff_vs_en": r["rate"] - en["rate"], "only_form": only_f, "only_en": only_en,
                      "mcnemar_p": binom_test_half(only_f, only_f + only_en)})
        for r, p in zip(a1[-3:], holm([r["mcnemar_p"] for r in a1[-3:]])):
            r["holm_p"] = p
        b2 = []
        for form in NON_EN:
            d = [s[form] - s["en"] for s in w.values() if form in s and "en" in s]
            b2.append({"judge": j, "id": "A2", "form": form, "measure": "wrong-twin correctness, form minus en",
                       **mean_row(d), "wilcoxon_p": wilcoxon_p(d)})
            both = [i for i, s in w.items() if form in s and "en" in s
                    and form in c.get(i, {}) and "en" in c.get(i, {})]
            d = [(c[i][form] - w[i][form]) - (c[i]["en"] - w[i]["en"]) for i in both]
            a3.append({"judge": j, "id": "A3-diff", "form": form, "measure": "margin, form minus en", **mean_row(d)})
        for r, p in zip(b2, holm([r["wilcoxon_p"] for r in b2])):
            r["holm_p"] = p
        a2 += b2
        for cid, x, y in CONTRASTS:
            d = [s[x] - s[y] for s in w.values() if x in s and y in s]
            a4.append({"judge": j, "id": cid, "form": f"{x} vs {y}", "measure": "wrong-twin correctness difference",
                       **mean_row(d), "wilcoxon_p": wilcoxon_p(d)})
    return {"a_missing": missing, "a_distribution": dist, "a_false_acceptance": a1, "a_leniency": a2,
            "a_margin": a3, "a_contrasts": a4}


def flag(r: dict) -> str:
    return " (exploratory)" if r.get("exploratory") else ""


def ci(r: dict, key: str) -> str:
    return f"{fmt(r[key])} [{fmt(r['ci_low'])}, {fmt(r['ci_high'])}]"


def render_markdown(tables: dict, variant: str, judges: list[str]) -> str:
    L = [f"# Gap A: error-detection leniency on matched wrong answers ({variant} prompt)", "",
         f"Judges: {', '.join(judges)}. Generated by `python -m lb.wrong_leniency` from the a_wrong and E1 records "
         "in results/raw (pilot runs excluded), per analysis/plan.md gap A. Each verified wrong twin is scored "
         "pointwise in all four forms with the E1 rubric and prompt; factual items show the English reference, as "
         f"in E1. False acceptance = wrong-twin correctness >= {ACCEPT_AT}.", "",
         "## Missing calls", "", "| Judge | Form | Planned | Missing |", "|---|---|---|---|"]
    L += [f"| {r['judge']} | {r['form']} | {r['planned']} | {r['missing']} |" for r in tables["a_missing"]]
    L += ["", "## Wrong-twin correctness scores (counts)", "", "| Judge | Form | 1 | 2 | 3 | 4 | 5 |",
          "|---|---|---|---|---|---|---|"]
    L += [f"| {r['judge']} | {r['form']} | " + " | ".join(str(r[f'score_{k}']) for k in range(1, 6)) + " |"
          for r in tables["a_distribution"]]
    L += ["", "## A1: false-acceptance rate (primary)", "",
          "Wilson 95% CI. Paired against the same item's wrong English answer with an exact McNemar test; Holm "
          "across the three forms per judge.", "",
          "| Judge | Form | k / n | Rate [95% CI] | vs en | McNemar p (Holm) |", "|---|---|---|---|---|---|"]
    for r in tables["a_false_acceptance"]:
        vs = f"{r['diff_vs_en']:+.2f}" if "diff_vs_en" in r else "-"
        p = f"{pval(r['mcnemar_p'])} ({pval(r['holm_p'])})" if "mcnemar_p" in r else "-"
        L.append(f"| {r['judge']} | {r['form']} | {r['k']} / {r['n']} | {ci(r, 'rate')} | {vs} | {p} |")
    L += ["", "## A2: leniency on wrong answers, form minus en", "",
          "Paired bootstrap 95% CI over items (10,000 resamples, seed 20261023); two-sided Wilcoxon; Holm across "
          "the three forms per judge. Positive = the wrong answer scores higher in that form than in English.", "",
          "| Judge | Form | n | mean d [95% CI] | Wilcoxon p | Holm p |", "|---|---|---|---|---|---|"]
    L += [f"| {r['judge']} | {r['form']} | {r['n']}{flag(r)} | {ci(r, 'mean')} | {pval(r['wilcoxon_p'])} | "
          f"{pval(r['holm_p'])} |" for r in tables["a_leniency"]]
    L += ["", "## A3: discrimination margin (descriptive)", "",
          "Margin = correctness of the correct answer (E1) minus correctness of its wrong twin, same form. "
          "A3-diff = the form's margin minus the English margin.", "",
          "| Judge | ID | Form | Measure | n | mean [95% CI] |", "|---|---|---|---|---|---|"]
    L += [f"| {r['judge']} | {r['id']} | {r['form']} | {r['measure']} | {r['n']}{flag(r)} | {ci(r, 'mean')} |"
          for r in tables["a_margin"]]
    L += ["", "## A4: script and mixing contrasts (descriptive)", "",
          "| Judge | ID | Contrast | n | mean d [95% CI] | Wilcoxon p |", "|---|---|---|---|---|---|"]
    L += [f"| {r['judge']} | {r['id']} | {r['form']} | {r['n']}{flag(r)} | {ci(r, 'mean')} | {pval(r['wilcoxon_p'])} |"
          for r in tables["a_contrasts"]]
    return "\n".join(L) + "\n"


def run(variant: str = "baseline", judges: list[str] | None = None, raw_dir: Path = RAW,
        tables_dir: Path = TABLES) -> dict:
    calls = load_calls(variant, judges, raw_dir)
    judges = judges or judges_in({k: v for k, v in calls.items() if k[0] == EXPERIMENT})
    if not judges:
        raise SystemExit(f"no main-study {variant} gap A ({EXPERIMENT}) results in {raw_dir}")
    tables = analyse(calls, judges, load_quadruples())
    for name, rows in tables.items():
        write_csv(tables_dir / f"main_{variant}_{name}.csv", rows)
    (tables_dir / f"main_{variant}_a.md").write_text(render_markdown(tables, variant, judges), encoding="utf-8")
    return tables


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--variant", default="baseline")
    p.add_argument("--judges", default=None, help="comma-separated; default: every judge with gap A results")
    args = p.parse_args()
    run(args.variant, args.judges.split(",") if args.judges else None)
    print(f"wrote results/tables/main_{args.variant}_a_*.csv and main_{args.variant}_a.md")


if __name__ == "__main__":
    main()
