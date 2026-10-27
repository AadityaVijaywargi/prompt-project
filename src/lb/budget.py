"""Call budget (brief section 6).

    python -m lb.budget                      planned sizes from experiments.yaml + counts from current data
    python -m lb.budget --pilot              Phase 0 pilot (pilot items, pilot judges, E1 and E2)
    python -m lb.budget --include-unverified count unverified items too (dry run)

Runners call confirm(): it prints the exact number of new (uncached) calls and refuses to proceed
without --yes. Parse retries are not included; each failed parse can add up to 2 more calls.
"""
from __future__ import annotations

import argparse
from collections import Counter

from .config import experiments_config

N_FORMS = 4


def planned_counts(exp_cfg: dict, n: int, w: int) -> list[tuple[str, str, int]]:
    ex = exp_cfg["experiments"]
    rows = []
    j = len(ex["e1"]["judges"])
    rows.append(("E1", f"N x 4 x J = {n} x 4 x {j}", n * N_FORMS * j))
    j = len(ex["e2"]["judges"])
    p = len(ex["e2"]["pairs"])
    rows.append(("E2", f"{p} pairs x 2 orders x N x J = {p} x 2 x {n} x {j}", p * 2 * n * j))
    if ex["e2b"].get("enabled"):
        j = len(ex["e2b"]["judges"])
        p = len(ex["e2b"]["pairs"])
        rows.append(("E2b", f"{p} x 2 x {n} x {j}", p * 2 * n * j))
    j = len(ex["e3"]["judges"])
    c = len(ex["e3"]["correct_forms"])
    rows.append(("E3", f"{c} x 2 x W x J = {c} x 2 x {w} x {j}", c * 2 * w * j))
    if ex["e3"].get("control"):
        rows.append(("E3 control", f"1 x 2 x {w} x {j}", 2 * w * j))
    if "a_wrong" in ex:
        j = len(ex["a_wrong"]["judges"])
        rows.append(("Gap A wrong twins", f"W x 4 x J = {w} x 4 x {j}", w * N_FORMS * j))
    e5 = ex["e5"]
    j5, n5 = len(e5["judges"]), min(e5["subset_size"], n)
    w5 = min(w, round(n5 * 2 / 3))   # the subset's factual two thirds, drawn from wrong-twin items
    e3_5 = (c + 1) * 2 * w5 * j5     # + the control (correct en vs wrong en), the accuracy cost
    per_variant = n5 * N_FORMS * j5 + 3 * 2 * n5 * j5 + e3_5
    for v in e5["variants"]:
        rows.append((f"E5 {v}", f"E1 {n5*4*j5} + E2 {6*n5*j5} + E3 {e3_5} ({j5} judges, {n5} items, {w5} twins)",
                     per_variant))
    if "translate_then_judge" in e5["variants"]:
        rows.append(("E5 translations", f"{n5} items x 3 non-English forms (once, shared by judges)", n5 * 3))
    return rows


def print_planned(exp_cfg: dict, n: int, w: int, title: str) -> int:
    rows = planned_counts(exp_cfg, n, w)
    print(f"\n{title}")
    print(f"  {'experiment':<26}{'formula':<62}{'calls':>8}")
    for name, formula, calls in rows:
        print(f"  {name:<26}{formula:<62}{calls:>8,}")
    total = sum(r[2] for r in rows)
    print(f"  {'TOTAL':<88}{total:>8,}")
    return total


def summarize(specs, judges) -> tuple[Counter, Counter]:
    total, cached = Counter(), Counter()
    for s in specs:
        total[(s.experiment, s.judge)] += 1
        if judges[s.judge].key(s.prompt) in judges[s.judge].cache:
            cached[(s.experiment, s.judge)] += 1
    return total, cached


def print_specs(specs, judges) -> int:
    total, cached = summarize(specs, judges)
    print(f"  {'experiment':<12}{'judge':<22}{'calls':>8}{'cached':>8}{'new':>8}")
    for key in sorted(total):
        print(f"  {key[0]:<12}{key[1]:<22}{total[key]:>8,}{cached[key]:>8,}{total[key]-cached[key]:>8,}")
    new = sum(total.values()) - sum(cached.values())
    print(f"  {'TOTAL':<34}{sum(total.values()):>8,}{sum(cached.values()):>8,}{new:>8,}")
    return new


def confirm(specs, judges, yes: bool) -> bool:
    print("Call budget for this run:")
    new = print_specs(specs, judges)
    if new == 0:
        print("All calls are cached; no network calls will be made.")
        return True
    if not yes:
        print(f"\nNot running. Re-run with --yes to send {new:,} new calls "
              "(plus up to 2 retries per unparseable response).")
        return False
    return True


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pilot", action="store_true")
    p.add_argument("--include-unverified", action="store_true")
    args = p.parse_args()
    exp_cfg = experiments_config()

    if not args.pilot:
        pl = exp_cfg["planned"]
        print_planned(exp_cfg, pl["n_items"], pl["n_wrong_twins"],
                      f"Planned budget (N={pl['n_items']}, W={pl['n_wrong_twins']}, from experiments.yaml)")

    from .data import load_quadruples
    from .runners import a_wrong_pointwise, e1_pointwise, e2_pairwise, e3_wrong
    from .runners.common import build_judges

    items = load_quadruples(include_unverified=args.include_unverified, pilot_only=args.pilot)
    if args.pilot:
        items = items[: exp_cfg["pilot"]["n_items"]]
    label = "all items (incl. unverified)" if args.include_unverified else "qc.passed items only"
    print(f"\nFrom current data: {len(items)} {label}"
          f", {sum(q.wrong_usable for q in items)} with verified wrong twins")
    if not items:
        print("  No eligible items yet. Items need qc.passed=true (use --include-unverified for a dry run).")
        return

    ex = exp_cfg["experiments"]
    pick = (lambda e: exp_cfg["pilot"]["judges"]) if args.pilot else (lambda e: ex[e]["judges"])
    wanted = exp_cfg["pilot"]["experiments"] if args.pilot else (
        ["e1", "e2", "e3"] + (["e2b"] if ex["e2b"].get("enabled") else []) + (["a_wrong"] if "a_wrong" in ex else []))
    specs = []
    for e in wanted:
        if e == "e1":
            specs += e1_pointwise.plan(items, pick(e), exp_cfg)
        elif e in ("e2", "e2b"):
            specs += e2_pairwise.plan(items, pick(e), exp_cfg, experiment=e)
        elif e == "e3":
            specs += e3_wrong.plan(items, pick(e), exp_cfg)
        elif e == "a_wrong":
            specs += a_wrong_pointwise.plan(items, pick(e), exp_cfg)
    judges = build_judges(sorted({s.judge for s in specs}), offline=True)
    print_specs(specs, judges)
    print("\nNothing was run. Each runner prints its own budget and needs --yes to make calls.")


if __name__ == "__main__":
    main()
