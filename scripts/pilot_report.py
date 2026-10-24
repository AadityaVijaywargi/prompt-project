"""Generates pilot report tables and markdown from results/raw/*pilot*.jsonl.

Implements the Phase 0 pilot analysis specified in HANDOFF.pdf (Task A7)
and analysis/plan.md (E1 and E2 comparisons).
"""
from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Optional

from lb.config import DATA, RAW, TABLES, read_jsonl
from lb.data import load_quadruples
from lb.stats import (
    binom_test_half,
    holm,
    log_length_ratio_slope,
    paired_bootstrap_ci,
    wilcoxon_p,
    wilson_ci,
)


def load_raw_calls(raw_dir: Path, pattern: str = "*pilot*.jsonl", variant: str = "baseline") -> list[dict]:
    # Only one prompt variant per report: mixing variants would let one overwrite the other
    # during the last-attempt dedup below.
    files = sorted(raw_dir.glob(pattern))
    calls = []
    for f in files:
        calls.extend(c for c in read_jsonl(f) if c.get("prompt_variant") == variant)
    return calls


def compute_e1(calls: list[dict], items_by_id: dict) -> list[dict]:
    """Compute E1 pointwise metrics per judge and comparison."""
    # Filter for E1 calls
    e1_calls = [c for c in calls if c.get("experiment") == "e1"]
    if not e1_calls:
        return []

    # Keep only the last attempt for each (judge, item_id, form)
    calls_by_key = {}
    for c in e1_calls:
        judge = c["judge"]
        item_id = c["item_id"]
        form = c["forms"][0] if c.get("forms") else None
        if not form:
            continue
        key = (judge, item_id, form)
        if key not in calls_by_key or c.get("attempt", 0) >= calls_by_key[key].get("attempt", 0):
            calls_by_key[key] = c

    # Group scores by judge and item_id
    by_judge_item = defaultdict(lambda: defaultdict(dict))
    parse_failures = defaultdict(int)

    for (judge, item_id, form), c in calls_by_key.items():
        if not c.get("parse_ok") or not c.get("parsed"):
            parse_failures[judge] += 1
            continue
        parsed = c["parsed"]
        corr = float(parsed.get("correctness", 0))
        comp = float(parsed.get("completeness", 0))
        clar = float(parsed.get("clarity", 0))
        qual = float(parsed.get("language_quality", 0))
        content = (corr + comp + clar) / 3.0
        overall = (corr + comp + clar + qual) / 4.0

        q = items_by_id.get(item_id)
        words = q.answers.get(form).words if q and hasattr(q, "answers") else 1

        by_judge_item[judge][item_id][form] = {
            "content": content,
            "overall": overall,
            "words": words,
        }

    results = []
    comparisons = [
        ("E1.1", "hi vs en", "hi", "en", "content"),
        ("E1.2", "hi_rom vs en", "hi_rom", "en", "content"),
        ("E1.3", "hinglish vs en", "hinglish", "en", "content"),
        ("E1.4", "hi vs hi_rom (script)", "hi", "hi_rom", "content"),
        ("E1.5", "hi_rom vs hinglish (mixing)", "hi_rom", "hinglish", "content"),
        ("E1.1_ov", "hi vs en (overall)", "hi", "en", "overall"),
        ("E1.2_ov", "hi_rom vs en (overall)", "hi_rom", "en", "overall"),
        ("E1.3_ov", "hinglish vs en (overall)", "hinglish", "en", "overall"),
    ]

    for judge in sorted(by_judge_item.keys()):
        items_map = by_judge_item[judge]
        judge_pvalues = []
        judge_rows = []

        for cid, label, f1, f2, measure in comparisons:
            diffs = []
            log_ratios = []
            for item_id, forms_dict in items_map.items():
                if f1 in forms_dict and f2 in forms_dict:
                    d = forms_dict[f1][measure] - forms_dict[f2][measure]
                    diffs.append(d)
                    w1 = max(1, forms_dict[f1]["words"])
                    w2 = max(1, forms_dict[f2]["words"])
                    log_ratios.append(math.log(w1 / w2))

            n = len(diffs)
            if n > 0:
                mean_d, lo, hi = paired_bootstrap_ci(diffs, seed=20261023)
                p_val = wilcoxon_p(diffs)
                try:
                    ols = log_length_ratio_slope(diffs, log_ratios)
                except Exception:
                    ols = {"intercept": float("nan"), "slope": float("nan"), "slope_p": float("nan"), "r2": float("nan")}
            else:
                mean_d, lo, hi = float("nan"), float("nan"), float("nan")
                p_val = float("nan")
                ols = {"intercept": float("nan"), "slope": float("nan"), "slope_p": float("nan"), "r2": float("nan")}

            row = {
                "judge": judge,
                "comparison_id": cid,
                "comparison": label,
                "measure": measure,
                "n": n,
                "mean_gap": mean_d,
                "ci_lo": lo,
                "ci_hi": hi,
                "wilcoxon_p": p_val,
                "holm_p": float("nan"),
                "intercept": ols["intercept"],
                "slope": ols["slope"],
                "slope_p": ols["slope_p"],
                "r2": ols["r2"],
                "parse_failures": parse_failures[judge],
            }
            judge_rows.append(row)
            if cid in {"E1.1", "E1.2", "E1.3", "E1.4", "E1.5"}:
                judge_pvalues.append(p_val)

        # Holm correction across the 5 primary comparisons
        adj_p = holm(judge_pvalues)
        for i, row in enumerate(judge_rows[:5]):
            row["holm_p"] = adj_p[i]

        results.extend(judge_rows)

    return results


def compute_e2(calls: list[dict]) -> list[dict]:
    """Compute E2 pairwise metrics per judge and pair."""
    e2_calls = [c for c in calls if c.get("experiment") == "e2"]
    if not e2_calls:
        return []

    # Keep only the last attempt for each (judge, item_id, pair_tuple, order)
    calls_by_key = {}
    for c in e2_calls:
        judge = c["judge"]
        item_id = c["item_id"]
        forms = tuple(c.get("forms", []))
        order = c.get("order")
        if not forms or not order:
            continue
        key = (judge, item_id, forms, order)
        if key not in calls_by_key or c.get("attempt", 0) >= calls_by_key[key].get("attempt", 0):
            calls_by_key[key] = c

    # Group by judge and pair: (x, y) where x is usually 'en'
    # For order == 'AB', A is x, B is y
    # For order == 'BA', A is y, B is x
    by_judge_pair_item = defaultdict(lambda: defaultdict(dict))
    for (judge, item_id, forms, order), c in calls_by_key.items():
        if not c.get("parse_ok") or not c.get("parsed"):
            continue
        verdict = c["parsed"].get("winner")  # 'A', 'B', or 'tie'
        if verdict not in {"A", "B", "tie"}:
            continue
        pair_name = f"{forms[0]} vs {forms[1]}"
        by_judge_pair_item[judge][pair_name].setdefault(item_id, {})[order] = (verdict, forms)

    results = []
    for judge in sorted(by_judge_pair_item.keys()):
        judge_pvalues = []
        judge_rows = []

        for pair_name in sorted(by_judge_pair_item[judge].keys()):
            items_dict = by_judge_pair_item[judge][pair_name]
            en_wins = 0
            form_wins = 0
            ties = 0
            a_wins = 0
            total_non_tie = 0

            consistent_items = 0
            consistent_en_wins = 0
            consistent_form_wins = 0
            total_items = len(items_dict)

            for item_id, orders in items_dict.items():
                item_underlying_winners = []
                for order in ("AB", "BA"):
                    if order not in orders:
                        continue
                    verdict, forms = orders[order]
                    # forms[0] is 'en', forms[1] is non-en form
                    if order == "AB":
                        if verdict == "A":
                            en_wins += 1
                            a_wins += 1
                            total_non_tie += 1
                            item_underlying_winners.append(forms[0])
                        elif verdict == "B":
                            form_wins += 1
                            total_non_tie += 1
                            item_underlying_winners.append(forms[1])
                        else:
                            ties += 1
                            item_underlying_winners.append("tie")
                    elif order == "BA":
                        if verdict == "A":
                            form_wins += 1
                            a_wins += 1
                            total_non_tie += 1
                            item_underlying_winners.append(forms[1])
                        elif verdict == "B":
                            en_wins += 1
                            total_non_tie += 1
                            item_underlying_winners.append(forms[0])
                        else:
                            ties += 1
                            item_underlying_winners.append("tie")

                # Position consistency: both orders agree on underlying outcome
                if len(item_underlying_winners) == 2:
                    if item_underlying_winners[0] == item_underlying_winners[1]:
                        consistent_items += 1
                        if item_underlying_winners[0] == forms[0]:
                            consistent_en_wins += 1
                        elif item_underlying_winners[0] == forms[1]:
                            consistent_form_wins += 1

            # E2.1 English win-rate
            win_rate = en_wins / total_non_tie if total_non_tie > 0 else float("nan")
            win_lo, win_hi = wilson_ci(en_wins, total_non_tie)
            p_val = binom_test_half(en_wins, total_non_tie)

            # E2.2 Tie rate
            total_judgments = en_wins + form_wins + ties
            tie_rate = ties / total_judgments if total_judgments > 0 else float("nan")
            tie_lo, tie_hi = wilson_ci(ties, total_judgments)

            # E2.3 Position consistency
            pos_cons = consistent_items / total_items if total_items > 0 else float("nan")
            cons_lo, cons_hi = wilson_ci(consistent_items, total_items)

            # E2.4 A-slot rate
            a_slot_rate = a_wins / total_non_tie if total_non_tie > 0 else float("nan")
            a_lo, a_hi = wilson_ci(a_wins, total_non_tie)

            # E2.5 Order-consistent English win-rate
            tot_cons_decisions = consistent_en_wins + consistent_form_wins
            cons_win_rate = consistent_en_wins / tot_cons_decisions if tot_cons_decisions > 0 else float("nan")
            cwin_lo, cwin_hi = wilson_ci(consistent_en_wins, tot_cons_decisions)

            row = {
                "judge": judge,
                "pair": pair_name,
                "n_items": total_items,
                "en_wins": en_wins,
                "form_wins": form_wins,
                "ties": ties,
                "en_win_rate": win_rate,
                "en_win_ci_lo": win_lo,
                "en_win_ci_hi": win_hi,
                "binom_p": p_val,
                "holm_p": float("nan"),
                "tie_rate": tie_rate,
                "tie_ci_lo": tie_lo,
                "tie_ci_hi": tie_hi,
                "position_consistency": pos_cons,
                "consistency_ci_lo": cons_lo,
                "consistency_ci_hi": cons_hi,
                "a_slot_rate": a_slot_rate,
                "a_slot_ci_lo": a_lo,
                "a_slot_ci_hi": a_hi,
                "order_consistent_en_win_rate": cons_win_rate,
                "consistent_en_ci_lo": cwin_lo,
                "consistent_en_ci_hi": cwin_hi,
            }
            judge_rows.append(row)
            judge_pvalues.append(p_val)

        adj_p = holm(judge_pvalues)
        for i, row in enumerate(judge_rows):
            row["holm_p"] = adj_p[i]

        results.extend(judge_rows)

    return results


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def render_markdown_report(e1_rows: list[dict], e2_rows: list[dict], report_path: Path,
                           variant: str = "baseline") -> str:
    lines = [
        "# Pilot Report: Language-Bias Auditor for LLM Judges (Phase 0)",
        "",
        "> [!IMPORTANT]",
        "> **PILOT and exploratory (n = 20, below 30).**",
        f"> Prompt variant: `{variant}`.",
        "> All metrics are generated strictly from the pilot results files under `results/tables/`.",
        "> Pilot items are preliminary and are not pooled with later main results.",
        "",
        "## 1. E1: Pointwise Rubric Grading",
        "",
        "Signed gap vs English (or reference form): `score(form) - score(en)` on 1-5 scale.",
        "Primary measure is **content score** (mean of correctness, completeness, clarity); overall is secondary.",
        "",
        "| Judge | Comparison | Measure | n | Mean Gap | 95% CI | Wilcoxon p | Holm p | Verbosity Intercept | Verbosity Slope |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]

    for r in e1_rows:
        ci_str = f"[{r['ci_lo']:.3f}, {r['ci_hi']:.3f}]" if not math.isnan(r['ci_lo']) else "N/A"
        wilc = f"{r['wilcoxon_p']:.4f}" if not math.isnan(r['wilcoxon_p']) else "N/A"
        hlm = f"{r['holm_p']:.4f}" if not math.isnan(r['holm_p']) else "N/A"
        icpt = f"{r['intercept']:.3f}" if not math.isnan(r['intercept']) else "N/A"
        slp = f"{r['slope']:.3f}" if not math.isnan(r['slope']) else "N/A"
        gap = f"{r['mean_gap']:+.3f}" if not math.isnan(r['mean_gap']) else "N/A"
        lines.append(f"| {r['judge']} | {r['comparison']} | {r['measure']} | {r['n']} | {gap} | {ci_str} | {wilc} | {hlm} | {icpt} | {slp} |")

    lines.extend([
        "",
        "## 2. E2: Pairwise Preference (Both Orders)",
        "",
        "Evaluates whether judges systematically prefer English over semantically identical Hindi/Romanized/Hinglish answers.",
        "",
        "| Judge | Pair | n Items | En Wins | Form Wins | Ties | En Win Rate (95% CI) | Binom p | Holm p | Tie Rate (95% CI) | Position Consistency (95% CI) | A-Slot Rate (95% CI) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ])

    for r in e2_rows:
        en_ci = f"{r['en_win_rate']:.3f} [{r['en_win_ci_lo']:.3f}, {r['en_win_ci_hi']:.3f}]" if not math.isnan(r['en_win_rate']) else "N/A"
        tie_ci = f"{r['tie_rate']:.3f} [{r['tie_ci_lo']:.3f}, {r['tie_ci_hi']:.3f}]" if not math.isnan(r['tie_rate']) else "N/A"
        cons_ci = f"{r['position_consistency']:.3f} [{r['consistency_ci_lo']:.3f}, {r['consistency_ci_hi']:.3f}]" if not math.isnan(r['position_consistency']) else "N/A"
        aslot_ci = f"{r['a_slot_rate']:.3f} [{r['a_slot_ci_lo']:.3f}, {r['a_slot_ci_hi']:.3f}]" if not math.isnan(r['a_slot_rate']) else "N/A"
        bp = f"{r['binom_p']:.4f}" if not math.isnan(r['binom_p']) else "N/A"
        hp = f"{r['holm_p']:.4f}" if not math.isnan(r['holm_p']) else "N/A"
        lines.append(f"| {r['judge']} | {r['pair']} | {r['n_items']} | {r['en_wins']} | {r['form_wins']} | {r['ties']} | {en_ci} | {bp} | {hp} | {tie_ci} | {cons_ci} | {aslot_ci} |")

    lines.extend([
        "",
        "## 3. Notes & Limitations",
        "",
        "- All pilot numbers are strictly sourced from `results/tables/pilot_e1_pointwise.csv` and `results/tables/pilot_e2_pairwise.csv`.",
        "- Due to small sample size (n=20), confidence intervals are wide and p-values are exploratory.",
        "- Main findings will be established in Phase 2 with full dataset (N=150) and complete judge panel.",
        "",
    ])

    report_text = "\n".join(lines)
    report_path.write_text(report_text, encoding="utf-8")
    return report_text


def generate_pilot_report(raw_dir: Path = RAW, tables_dir: Path = TABLES,
                          report_path: Path = Path("pilot_report.md"),
                          variant: str = "baseline") -> tuple[list[dict], list[dict]]:
    calls = load_raw_calls(raw_dir, variant=variant)
    items = load_quadruples(include_unverified=True)
    items_by_id = {q.item_id: q for q in items}

    e1_rows = compute_e1(calls, items_by_id)
    e2_rows = compute_e2(calls)

    e1_csv = tables_dir / "pilot_e1_pointwise.csv"
    e2_csv = tables_dir / "pilot_e2_pairwise.csv"

    write_csv(e1_csv, e1_rows)
    write_csv(e2_csv, e2_rows)

    render_markdown_report(e1_rows, e2_rows, report_path, variant)
    print(f"Wrote {len(e1_rows)} E1 rows to {e1_csv}")
    print(f"Wrote {len(e2_rows)} E2 rows to {e2_csv}")
    print(f"Rendered pilot report to {report_path}")
    return e1_rows, e2_rows


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw-dir", type=Path, default=RAW)
    p.add_argument("--tables-dir", type=Path, default=TABLES)
    p.add_argument("--report", type=Path, default=Path("pilot_report.md"))
    p.add_argument("--variant", default="baseline", help="prompt variant to report on (one per report)")
    args = p.parse_args()
    generate_pilot_report(args.raw_dir, args.tables_dir, args.report, args.variant)


if __name__ == "__main__":
    main()
