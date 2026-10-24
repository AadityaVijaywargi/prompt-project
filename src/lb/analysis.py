"""Main-study E1-E3 tables, exactly as fixed in analysis/plan.md, plus results/thresholds.json.

    python -m lb.analysis                          # every judge with main (non-pilot) baseline results
    python -m lb.analysis --judges qwen2.5-7b-local --variant baseline

Reads results/raw (pilot runs excluded), keeps only qc.passed items (E3: only verified wrong twins), and
writes CSVs plus a markdown summary to results/tables/main_<variant>_*. A planned call with no parsed
record is missing: its item is dropped from that comparison only, and missing counts are reported.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

from .config import RAW, RESULTS, TABLES, read_jsonl
from .data import load_quadruples
from .stats import binom_test_half, holm, log_length_ratio_slope, paired_bootstrap_ci, wilcoxon_p, wilson_ci

SEED = 20261023
EXPLORATORY_N = 30
CRITERIA = ("correctness", "completeness", "clarity", "language_quality")
E1_COMPARISONS = [  # id, form, baseline form
    ("E1.1", "hi", "en"),
    ("E1.2", "hi_rom", "en"),
    ("E1.3", "hinglish", "en"),
    ("E1.4", "hi", "hi_rom"),
    ("E1.5", "hi_rom", "hinglish"),
]
E2_PAIRS = [("en", "hi"), ("en", "hi_rom"), ("en", "hinglish")]
E3_FORMS = ["hi", "hi_rom", "hinglish", "en"]   # "en" is the control: correct en vs wrong en
WRONG = "wrong:en"


# ---------- loading ----------

def load_calls(variant: str = "baseline", judges: list[str] | None = None, raw_dir: Path = RAW) -> dict:
    """{(experiment, judge, item_id, forms, order): parsed} for main-study calls that parsed.

    Pilot runs are excluded. Re-logged cache hits and retries collapse onto one key; a key counts as
    parsed if any of its records parsed."""
    calls = {}
    for f in sorted(raw_dir.glob("*.jsonl")):
        for r in read_jsonl(f):
            if r.get("prompt_variant") != variant or str(r.get("run_id", "")).startswith("pilot-"):
                continue
            if judges and r["judge"] not in judges:
                continue
            if r["parse_ok"] and r.get("parsed"):
                calls[(r["experiment"], r["judge"], r["item_id"], tuple(r["forms"]), r.get("order"))] = r["parsed"]
    return calls


def judges_in(calls: dict) -> list[str]:
    return sorted({k[1] for k in calls})


def exploratory(n: int) -> bool:
    return n < EXPLORATORY_N


# ---------- E1 ----------

def e1_scores(calls: dict, judge: str, items) -> dict:
    """{item_id: {form: {criterion..., content, overall}}} for one judge."""
    out = defaultdict(dict)
    for q in items:
        for form in ("en", "hi", "hi_rom", "hinglish"):
            p = calls.get(("e1", judge, q.item_id, (form,), None))
            if p is None:
                continue
            s = {c: float(p[c]) for c in CRITERIA}
            s["content"] = (s["correctness"] + s["completeness"] + s["clarity"]) / 3
            s["overall"] = sum(s[c] for c in CRITERIA) / 4
            out[q.item_id][form] = s
    return out


def gap(scores: dict, items, form: str, base: str, measure: str) -> tuple[list[float], list[float]]:
    """Paired d = score(form) - score(base) and log(words_form / words_base), items with both scored."""
    diffs, log_ratios = [], []
    for q in items:
        s = scores.get(q.item_id, {})
        if form in s and base in s:
            diffs.append(s[form][measure] - s[base][measure])
            log_ratios.append(math.log(q.answers.get(form).words / q.answers.get(base).words))
    return diffs, log_ratios


def gap_row(diffs: list[float]) -> dict:
    mean, lo, hi = paired_bootstrap_ci(diffs, seed=SEED)
    return {"n": len(diffs), "mean_d": mean, "ci_low": lo, "ci_high": hi,
            "wilcoxon_p": wilcoxon_p(diffs) if diffs else float("nan"),
            "exploratory": exploratory(len(diffs))}


def analyse_e1(calls: dict, judges: list[str], items) -> dict:
    main, by_type, criteria, missing = [], [], [], []
    for j in judges:
        scores = e1_scores(calls, j, items)
        for form in ("en", "hi", "hi_rom", "hinglish"):
            n_missing = sum(1 for q in items if form not in scores.get(q.item_id, {}))
            missing.append({"judge": j, "form": form, "planned": len(items), "missing": n_missing})

        rows = []
        for cid, form, base in E1_COMPARISONS:
            diffs, log_ratios = gap(scores, items, form, base, "content")
            ols = log_length_ratio_slope(diffs, log_ratios) if len(diffs) > 2 else {}
            rows.append({"judge": j, "id": cid, "comparison": f"{form} vs {base}", "measure": "content",
                         **gap_row(diffs), "verbosity_slope": ols.get("slope", float("nan")),
                         "verbosity_slope_p": ols.get("slope_p", float("nan")),
                         "gap_at_equal_length": ols.get("intercept", float("nan"))})
        for r, p in zip(rows, holm([r["wilcoxon_p"] for r in rows])):
            r["holm_p"] = p
        main += rows
        for cid, form, base in E1_COMPARISONS[:3]:      # overall score is secondary, for the en contrasts
            diffs, _ = gap(scores, items, form, base, "overall")
            main.append({"judge": j, "id": cid, "comparison": f"{form} vs {base}", "measure": "overall",
                         **gap_row(diffs)})

        for t in ("factual", "open_ended"):
            sub = [q for q in items if q.type == t]
            for cid, form, base in E1_COMPARISONS:
                diffs, _ = gap(scores, sub, form, base, "content")
                by_type.append({"judge": j, "type": t, "id": cid, "comparison": f"{form} vs {base}",
                                **gap_row(diffs), "exploratory": True})

        for crit in CRITERIA:
            for cid, form, base in E1_COMPARISONS[:3]:
                diffs, _ = gap(scores, items, form, base, crit)
                mean, lo, hi = paired_bootstrap_ci(diffs, seed=SEED)
                criteria.append({"judge": j, "criterion": crit, "id": cid, "comparison": f"{form} vs {base}",
                                 "n": len(diffs), "mean_d": mean, "ci_low": lo, "ci_high": hi})
    return {"e1": main, "e1_by_type": by_type, "e1_criteria": criteria, "e1_missing": missing}


def thresholds(calls: dict, judges: list[str], items) -> dict:
    """Per judge: 95th percentile of |content(form) - content(en)| over matched (item, form) pairs."""
    out = {}
    for j in judges:
        scores = e1_scores(calls, j, items)
        absd = [abs(d) for f in ("hi", "hi_rom", "hinglish") for d in gap(scores, items, f, "en", "content")[0]]
        if absd:
            out[j] = {"p95_abs_content_gap": float(np.percentile(absd, 95)), "n_pairs": len(absd)}
    return out


# ---------- pairwise helpers (E2, E3) ----------

def underlying_winner(winner: str, order: str, x: str, y: str) -> str:
    """Map a slot verdict to the form that won. AB shows x in slot A, BA shows y in slot A."""
    if winner == "tie":
        return "tie"
    a, b = (x, y) if order == "AB" else (y, x)
    return a if winner == "A" else b


def pair_verdicts(calls: dict, experiment: str, judge: str, items, x: str, y: str) -> dict:
    """{item_id: {order: (slot_winner, form_winner)}} for the orders that parsed."""
    out = defaultdict(dict)
    for q in items:
        for order in ("AB", "BA"):
            p = calls.get((experiment, judge, q.item_id, (x, y), order))
            if p is not None:
                out[q.item_id][order] = (p["winner"], underlying_winner(p["winner"], order, x, y))
    return out


def prop(k: int, n: int) -> dict:
    lo, hi = wilson_ci(k, n)
    return {"k": k, "n": n, "rate": k / n if n else float("nan"), "ci_low": lo, "ci_high": hi}


# ---------- E2 ----------

def analyse_e2(calls: dict, judges: list[str], items) -> list[dict]:
    rows = []
    for j in judges:
        e21 = []
        for x, y in E2_PAIRS:
            v = pair_verdicts(calls, "e2", j, items, x, y)
            judgments = [w for cell in v.values() for w in cell.values()]
            en_win = sum(1 for _, f in judgments if f == x)
            en_loss = sum(1 for _, f in judgments if f == y)
            ties = sum(1 for _, f in judgments if f == "tie")
            non_tie = [(s, f) for s, f in judgments if f != "tie"]
            both = [cell for cell in v.values() if len(cell) == 2]
            consistent = [cell for cell in both if cell["AB"][1] == cell["BA"][1]]
            consistent_non_tie = [cell for cell in consistent if cell["AB"][1] != "tie"]
            pair = f"{x} vs {y}"
            base = {"judge": j, "pair": pair, "items": len(v), "items_both_orders": len(both),
                    "exploratory": exploratory(len(both))}
            r1 = {**base, "id": "E2.1", "measure": "English win-rate", **prop(en_win, en_win + en_loss),
                  "binom_p": binom_test_half(en_win, en_win + en_loss)}
            e21.append(r1)
            rows += [r1,
                     {**base, "id": "E2.2", "measure": "tie rate", **prop(ties, len(judgments))},
                     {**base, "id": "E2.3", "measure": "position consistency", **prop(len(consistent), len(both))},
                     {**base, "id": "E2.4", "measure": "A-slot rate",
                      **prop(sum(1 for s, _ in non_tie if s == "A"), len(non_tie))},
                     {**base, "id": "E2.5", "measure": "order-consistent English win-rate",
                      **prop(sum(1 for c in consistent_non_tie if c["AB"][1] == x), len(consistent_non_tie))}]
        for r, p in zip(e21, holm([r["binom_p"] for r in e21])):
            r["holm_p"] = p
    return rows


# ---------- E3 ----------

def analyse_e3(calls: dict, judges: list[str], items) -> list[dict]:
    items = [q for q in items if q.wrong_usable]
    rows = []
    for j in judges:
        for form in E3_FORMS:
            v = pair_verdicts(calls, "e3", j, items, WRONG, form)
            both = [cell for cell in v.values() if len(cell) == 2]   # a cell missing an order is dropped
            wins = [sum(1 for o in ("AB", "BA") if cell[o][1] == WRONG) for cell in both]
            base = {"judge": j, "form": form, "control": form == "en", "items_planned": len(items),
                    "items_both_orders": len(both), "exploratory": exploratory(len(both))}
            rows += [{**base, "id": "E3.3" if form == "en" else "E3.1", "measure": "any-order wrong-English rate",
                      **prop(sum(1 for w in wins if w >= 1), len(both))},
                     {**base, "id": "E3.3" if form == "en" else "E3.2", "measure": "consistent wrong-English rate",
                      **prop(sum(1 for w in wins if w == 2), len(both))}]
    return rows


# ---------- output ----------

def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()} for r in rows)


def fmt(x: float, nd: int = 2) -> str:
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.{nd}f}"


def pval(p: float) -> str:
    return "n/a" if math.isnan(p) else ("<0.001" if p < 0.001 else f"{p:.3f}")


def flag(r: dict) -> str:
    return " (exploratory)" if r.get("exploratory") else ""


def render_markdown(tables: dict, variant: str, judges: list[str], thr: dict) -> str:
    L = [f"# Main study: E1-E3 ({variant} prompt)", "",
         f"Judges: {', '.join(judges)}. Generated by `python -m lb.analysis` from results/raw (pilot runs "
         "excluded), per analysis/plan.md. 95% CIs; cells with fewer than 30 paired items are exploratory.", ""]
    L += ["## Missing calls (E1, per form)", "", "| Judge | Form | Planned | Missing |", "|---|---|---|---|"]
    L += [f"| {r['judge']} | {r['form']} | {r['planned']} | {r['missing']} |" for r in tables["e1_missing"]]
    L += ["", "## E1: pointwise gap, d = score(form) - score(base)", "",
          "Content = mean(correctness, completeness, clarity). Bootstrap CI over items (10,000 resamples, seed "
          "20261023); two-sided Wilcoxon; Holm across E1.1-E1.5 per judge (content only).", "",
          "| Judge | ID | Comparison | Measure | n | mean d [95% CI] | Wilcoxon p | Holm p | "
          "Gap at equal length | Length slope (p) |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in tables["e1"]:
        L.append(f"| {r['judge']} | {r['id']} | {r['comparison']} | {r['measure']} | {r['n']}{flag(r)} | "
                 f"{fmt(r['mean_d'])} [{fmt(r['ci_low'])}, {fmt(r['ci_high'])}] | {pval(r['wilcoxon_p'])} | "
                 f"{pval(r['holm_p']) if 'holm_p' in r else '-'} | {fmt(r.get('gap_at_equal_length', float('nan')))} | "
                 + (f"{fmt(r['verbosity_slope'])} ({pval(r['verbosity_slope_p'])})" if 'verbosity_slope' in r else "-")
                 + " |")
    L += ["", "### E1 per criterion (descriptive)", "", "| Judge | Criterion | Comparison | n | mean d [95% CI] |",
          "|---|---|---|---|---|"]
    L += [f"| {r['judge']} | {r['criterion']} | {r['comparison']} | {r['n']} | "
          f"{fmt(r['mean_d'])} [{fmt(r['ci_low'])}, {fmt(r['ci_high'])}] |" for r in tables["e1_criteria"]]
    L += ["", "### E1 by item type (exploratory)", "", "| Judge | Type | Comparison | n | mean d [95% CI] | Wilcoxon p |",
          "|---|---|---|---|---|---|"]
    L += [f"| {r['judge']} | {r['type']} | {r['comparison']} | {r['n']} | "
          f"{fmt(r['mean_d'])} [{fmt(r['ci_low'])}, {fmt(r['ci_high'])}] | {pval(r['wilcoxon_p'])} |"
          for r in tables["e1_by_type"]]
    L += ["", "## E2: pairwise preference (each order counts as one judgment)", "",
          "| Judge | Pair | ID | Measure | k / n | Rate [95% CI] | p (Holm) |", "|---|---|---|---|---|---|---|"]
    for r in tables["e2"]:
        p = f"{pval(r['binom_p'])} ({pval(r['holm_p'])})" if "binom_p" in r else "-"
        L.append(f"| {r['judge']} | {r['pair']} | {r['id']} | {r['measure']}{flag(r)} | {r['k']} / {r['n']} | "
                 f"{fmt(r['rate'])} [{fmt(r['ci_low'])}, {fmt(r['ci_high'])}] | {p} |")
    L += ["", "## E3: wrong English vs correct answer", "",
          "Cells (item, form) need both orders parsed; `en` is the control (correct en vs wrong en, expected near 0).",
          "", "| Judge | Correct form | ID | Measure | k / n | Rate [95% CI] |", "|---|---|---|---|---|---|"]
    L += [f"| {r['judge']} | {r['form']} | {r['id']} | {r['measure']}{flag(r)} | {r['k']} / {r['n']} | "
          f"{fmt(r['rate'])} [{fmt(r['ci_low'])}, {fmt(r['ci_high'])}] |" for r in tables["e3"]]
    L += ["", "## App thresholds (results/thresholds.json)", "", "| Judge | p95 of abs content gap | Pairs |",
          "|---|---|---|"]
    L += [f"| {j} | {fmt(t['p95_abs_content_gap'])} | {t['n_pairs']} |" for j, t in thr.items()]
    return "\n".join(L) + "\n"


def run(variant: str = "baseline", judges: list[str] | None = None, raw_dir: Path = RAW,
        tables_dir: Path = TABLES, thresholds_path: Path | None = RESULTS / "thresholds.json") -> dict:
    calls = load_calls(variant, judges, raw_dir)
    judges = judges or judges_in(calls)
    if not judges:
        raise SystemExit(f"no main-study {variant} results in {raw_dir}")
    items = load_quadruples()
    tables = {**analyse_e1(calls, judges, items), "e2": analyse_e2(calls, judges, items),
              "e3": analyse_e3(calls, judges, items)}
    thr = thresholds(calls, judges, items)
    for name, rows in tables.items():
        write_csv(tables_dir / f"main_{variant}_{name}.csv", rows)
    (tables_dir / f"main_{variant}.md").write_text(render_markdown(tables, variant, judges, thr), encoding="utf-8")
    if thresholds_path and variant == "baseline":
        thresholds_path.write_text(json.dumps(thr, indent=2) + "\n", encoding="utf-8")
    return {**tables, "thresholds": thr}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--variant", default="baseline")
    p.add_argument("--judges", default=None, help="comma-separated; default: every judge with results")
    args = p.parse_args()
    judges = args.judges.split(",") if args.judges else None
    out = run(args.variant, judges)
    print(f"wrote results/tables/main_{args.variant}_*.csv and main_{args.variant}.md "
          f"({len(out['e1'])} E1 rows, {len(out['e2'])} E2 rows, {len(out['e3'])} E3 rows)")


if __name__ == "__main__":
    main()
