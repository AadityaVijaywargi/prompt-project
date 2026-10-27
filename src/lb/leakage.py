"""Section B of analysis/plan.md: criterion leakage (B1-B3) and judge-comment coding (B4-B5).

    python -m lb.leakage                           # every judge with main (non-pilot) baseline E1 results
    python -m lb.leakage --judges gpt-oss-120b

Reads only the E1 baseline records (no judge calls) and writes results/tables/main_<variant>_b_*.csv, a
markdown summary main_<variant>_b.md, and a seeded comment sample for the human coder check.
"""
from __future__ import annotations

import argparse
import csv
import math
import random
import re
from pathlib import Path

import numpy as np

from .analysis import SEED, e1_scores, exploratory, fmt, judges_in, load_calls, prop, pval, write_csv
from .config import RAW, TABLES
from .data import load_quadruples
from .stats import binom_test_half, bootstrap_slope_ci, holm, log_length_ratio_slope, paired_bootstrap_ci

FORMS = ("hi", "hi_rom", "hinglish")
SAMPLE_PER_CELL = 25

# Fixed in analysis/plan.md (section B) before any comment was read. B4/B5 use language, script and mixing.
MENTION_PATTERNS = {
    "language": [r"\blanguage", r"\blinguistic", r"\bhindi\b", r"\benglish\b", r"\btranslat",
                 r"भाषा", r"हिंदी", r"हिन्दी", r"अंग्रेज़ी", r"अंग्रेजी"],
    "script": [r"\bscript", r"\bdevanagari", r"\broman(i[sz]ed|i[sz]ation)?\b", r"\btransliterat",
               r"लिपि", r"देवनागरी"],
    "mixing": [r"\bhinglish", r"\bcode[- ]?mix", r"\bcode[- ]?switch", r"\bmixed language",
               r"\bmix(ture)? of (hindi|english)"],
    "fluency": [r"\bfluen", r"\bgrammar", r"\bgrammatical", r"\bspelling", r"\binformal", r"\bcolloquial",
                r"\bawkward", r"\bunnatural", r"\bslang", r"व्याकरण"],
}
_COMPILED = {cat: [re.compile(p, re.IGNORECASE) for p in pats] for cat, pats in MENTION_PATTERNS.items()}
BIAS_CATEGORIES = ("language", "script", "mixing")


def code_comment(text: str | None) -> dict:
    """{category: bool} for each lexicon category, plus 'mention' = any of language, script, mixing."""
    t = text or ""
    codes = {cat: any(p.search(t) for p in pats) for cat, pats in _COMPILED.items()}
    codes["mention"] = any(codes[c] for c in BIAS_CATEGORIES)
    return codes


def comments(calls: dict, judge: str, items) -> dict:
    """{item_id: {form: comment}} for E1 calls that parsed."""
    out = {}
    for q in items:
        for form in ("en", *FORMS):
            p = calls.get(("e1", judge, q.item_id, (form,), None))
            if p is not None:
                out.setdefault(q.item_id, {})[form] = p.get("comment") or ""
    return out


# ---------- B1-B3: leakage ----------

def paired_deltas(scores: dict, items, form: str, criterion: str) -> tuple[list[float], list[float]]:
    """(dL, dX): language_quality and criterion differences, form minus en, items with both scored."""
    dl, dx = [], []
    for q in items:
        s = scores.get(q.item_id, {})
        if form in s and "en" in s:
            dl.append(s[form]["language_quality"] - s["en"]["language_quality"])
            dx.append(s[form][criterion] - s["en"][criterion])
    return dl, dx


def slope_row(dl: list[float], dx: list[float]) -> dict:
    slope, lo, hi = bootstrap_slope_ci(dl, dx, seed=SEED)
    estimable = not math.isnan(slope)
    ols = log_length_ratio_slope(dx, dl) if estimable else {}
    return {"n": len(dl), "sd_dL": float(np.std(dl)) if dl else float("nan"), "slope": slope,
            "ci_low": lo, "ci_high": hi, "slope_p": ols.get("slope_p", float("nan")), "estimable": estimable,
            "exploratory": exploratory(len(dl))}


SIGNS = (("dL < 0", lambda v: v < 0), ("dL = 0", lambda v: v == 0), ("dL > 0", lambda v: v > 0))


def analyse_leakage(calls: dict, judges: list[str], items) -> dict:
    leakage, by_sign = [], []
    for j in judges:
        scores = e1_scores(calls, j, items)
        b1, b2 = [], []
        for form in FORMS:
            dl, dc = paired_deltas(scores, items, form, "correctness")
            b1.append({"judge": j, "id": "B1", "form": form, "criterion": "correctness", **slope_row(dl, dc)})
            for crit in ("completeness", "clarity"):
                b2.append({"judge": j, "id": "B2", "form": form, "criterion": crit,
                           **slope_row(*paired_deltas(scores, items, form, crit))})
            for sign, keep in SIGNS:
                cell = [c for l, c in zip(dl, dc) if keep(l)]
                mean, lo, hi = paired_bootstrap_ci(cell, seed=SEED)
                by_sign.append({"judge": j, "id": "B3", "form": form, "dL_sign": sign, "n": len(cell),
                                "mean_dC": mean, "ci_low": lo, "ci_high": hi})
        adj = iter(holm([r["slope_p"] for r in b1 if r["estimable"]]))
        for r in b1:
            r["holm_p"] = next(adj) if r["estimable"] else float("nan")
        leakage += b1 + b2
    return {"b_leakage": leakage, "b_by_sign": by_sign}


# ---------- B4-B5: comments ----------

def analyse_comments(calls: dict, judges: list[str], items) -> list[dict]:
    rows = []
    for j in judges:
        scores, texts = e1_scores(calls, j, items), comments(calls, j, items)
        codes = {i: {f: code_comment(t) for f, t in by_form.items()} for i, by_form in texts.items()}
        en_rate = [c["en"]["mention"] for c in codes.values() if "en" in c]
        rows.append({"judge": j, "id": "B4", "form": "en", "measure": "language-mention rate",
                     **prop(sum(en_rate), len(en_rate)), "exploratory": exploratory(len(en_rate))})
        b4 = []
        for form in FORMS:
            cells = [c for c in codes.values() if form in c]
            k = sum(c[form]["mention"] for c in cells)
            paired = [c for c in cells if "en" in c]
            only_f = sum(c[form]["mention"] and not c["en"]["mention"] for c in paired)
            only_en = sum(c["en"]["mention"] and not c[form]["mention"] for c in paired)
            r = {"judge": j, "id": "B4", "form": form, "measure": "language-mention rate", **prop(k, len(cells)),
                 "only_form": only_f, "only_en": only_en, "mcnemar_p": binom_test_half(only_f, only_f + only_en),
                 "exploratory": exploratory(len(cells))}
            b4.append(r)
            for cat in (*BIAS_CATEGORIES, "fluency"):
                rows.append({"judge": j, "id": "B4-cat", "form": form, "measure": f"{cat} mention rate",
                             **prop(sum(c[form][cat] for c in cells), len(cells))})
            dropped = [i for i, s in scores.items() if form in s and "en" in s
                       and s[form]["content"] < s["en"]["content"] and form in codes.get(i, {})]
            silent = sum(not codes[i][form]["mention"] for i in dropped)
            rows.append({"judge": j, "id": "B5", "form": form, "measure": "silent penalty rate",
                         **prop(silent, len(dropped)), "exploratory": exploratory(len(dropped))})
        for r, p in zip(b4, holm([r["mcnemar_p"] for r in b4])):
            r["holm_p"] = p
        rows += b4
    order = {"B4": 0, "B4-cat": 1, "B5": 2}
    forms = ("en", *FORMS)
    return sorted(rows, key=lambda r: (judges.index(r["judge"]), order[r["id"]], forms.index(r["form"])))


def comment_sample(calls: dict, judges: list[str], items) -> list[dict]:
    """Seeded sample of SAMPLE_PER_CELL comments per judge and form for the human coder check. Each cell has
    its own seed, so the sample does not depend on judge order or on which other judges are included."""
    rows = []
    for j in judges:
        texts = comments(calls, j, items)
        for form in ("en", *FORMS):
            rng = random.Random(f"{SEED}-{j}-{form}")
            pool = sorted((i, t[form]) for i, t in texts.items() if form in t)
            for item_id, text in rng.sample(pool, min(SAMPLE_PER_CELL, len(pool))):
                rows.append({"judge": j, "item_id": item_id, "form": form, "comment": text,
                             "coder_mention": code_comment(text)["mention"], "human_mention": ""})
    return rows


HUMAN_YES, HUMAN_NO = {"1", "y", "yes", "true"}, {"0", "n", "no", "false"}


def human_label(value: str | None) -> bool | None:
    """human_mention cell -> True / False, or None if not coded yet. Accepts 1/0, y/n, yes/no, true/false."""
    v = (value or "").strip().lower()
    if not v:
        return None
    if v in HUMAN_YES or v in HUMAN_NO:
        return v in HUMAN_YES
    raise ValueError(f"human_mention must be one of {sorted(HUMAN_YES | HUMAN_NO)} or blank, got {value!r}")


def read_sample(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:   # utf-8-sig: Excel adds a BOM on save
        return list(csv.DictReader(f))


def coder_check(sample: list[dict], judges: list[str]) -> list[dict]:
    """Keyword coder vs human_mention on the coded sample rows: precision and recall per judge and pooled."""
    rows = []
    for j in (*judges, "all"):
        coded = [(r["coder_mention"].strip().lower() == "true", human_label(r["human_mention"]))
                 for r in sample if j in ("all", r["judge"])]
        coded = [(c, h) for c, h in coded if h is not None]
        tp = sum(c and h for c, h in coded)
        fp = sum(c and not h for c, h in coded)
        fn = sum(h and not c for c, h in coded)
        for measure, k, n in (("precision", tp, tp + fp), ("recall", tp, tp + fn)):
            rows.append({"judge": j, "measure": measure, "coded": len(coded), "tp": tp, "fp": fp, "fn": fn,
                         **prop(k, n)})
    return rows


# ---------- output ----------

def flag(r: dict) -> str:
    return " (exploratory)" if r.get("exploratory") else ""


def render_markdown(tables: dict, variant: str, judges: list[str], sample_size: int) -> str:
    coded = next((r["coded"] for r in tables["b_coder_check"] if r["judge"] == "all"), 0)
    status = ("validated by the coder check below" if sample_size and coded == sample_size
              else f"unvalidated: {coded} of {sample_size} sample comments human-coded")
    L = [f"# Section B: criterion leakage and judge comments ({variant} prompt, post hoc)", "",
         f"Judges: {', '.join(judges)}. Generated by `python -m lb.leakage` from the E1 records in results/raw "
         "(pilot runs excluded), per analysis/plan.md section B. No new judge calls. dC and dL are "
         "correctness and language_quality, form minus en, on the same item.", "",
         "## B1-B2: leakage slope (OLS of d-criterion on dL)", "",
         "Bootstrap 95% CI over items (10,000 resamples, seed 20261023). Holm across forms per judge for B1.", "",
         "| Judge | ID | Form | Criterion | n | SD of dL | slope [95% CI] | OLS p | Holm p |",
         "|---|---|---|---|---|---|---|---|---|"]
    for r in tables["b_leakage"]:
        s = (f"{fmt(r['slope'])} [{fmt(r['ci_low'])}, {fmt(r['ci_high'])}]" if r["estimable"]
             else "not estimable (dL constant)")
        L.append(f"| {r['judge']} | {r['id']} | {r['form']} | {r['criterion']} | {r['n']}{flag(r)} | "
                 f"{fmt(r['sd_dL'])} | {s} | {pval(r['slope_p'])} | "
                 f"{pval(r['holm_p']) if 'holm_p' in r else '-'} |")
    L += ["", "## B3: mean dC by the sign of dL (descriptive)", "", "| Judge | Form | dL | n | mean dC [95% CI] |",
          "|---|---|---|---|---|"]
    L += [f"| {r['judge']} | {r['form']} | {r['dL_sign']} | {r['n']} | "
          f"{fmt(r['mean_dC'])} [{fmt(r['ci_low'])}, {fmt(r['ci_high'])}] |" for r in tables["b_by_sign"]]
    L += ["", f"## B4-B5: judge comments (keyword coder, {status})", "",
          "Mention = the comment names language, script or code-mixing. B4 p is an exact McNemar test vs the "
          "same item's en comment, Holm across forms per judge. B5 = share of content drops vs en whose comment "
          "names none of these.", "",
          "| Judge | ID | Form | Measure | k / n | Rate [95% CI] | McNemar p (Holm) |", "|---|---|---|---|---|---|---|"]
    for r in tables["b_comments"]:
        p = f"{pval(r['mcnemar_p'])} ({pval(r['holm_p'])})" if "mcnemar_p" in r else "-"
        L.append(f"| {r['judge']} | {r['id']} | {r['form']} | {r['measure']}{flag(r)} | {r['k']} / {r['n']} | "
                 f"{fmt(r['rate'])} [{fmt(r['ci_low'])}, {fmt(r['ci_high'])}] | {p} |")
    L += ["", "## Coder check: keyword coder vs human_mention", "",
          f"Seeded sample of {SAMPLE_PER_CELL} comments per judge and form in main_{variant}_b_comment_sample.csv; "
          "fill human_mention with 1/0 (yes/no). Positive = the comment names language, script or code-mixing. "
          "Wilson 95% CI.", "",
          "| Judge | Measure | coded | TP / FP / FN | Rate [95% CI] |", "|---|---|---|---|---|"]
    L += [f"| {r['judge']} | {r['measure']} | {r['coded']} | {r['tp']} / {r['fp']} / {r['fn']} | "
          f"{fmt(r['rate'])} [{fmt(r['ci_low'])}, {fmt(r['ci_high'])}] |" for r in tables["b_coder_check"]]
    return "\n".join(L) + "\n"


def run(variant: str = "baseline", judges: list[str] | None = None, raw_dir: Path = RAW,
        tables_dir: Path = TABLES) -> dict:
    calls = load_calls(variant, judges, raw_dir)
    judges = judges or judges_in({k: v for k, v in calls.items() if k[0] == "e1"})
    if not judges:
        raise SystemExit(f"no main-study {variant} E1 results in {raw_dir}")
    items = load_quadruples()
    tables = {**analyse_leakage(calls, judges, items), "b_comments": analyse_comments(calls, judges, items)}
    # Never overwrite human coding: once any human_mention is filled in, the sample file is left as it is.
    sample_path = tables_dir / f"main_{variant}_b_comment_sample.csv"
    sample = read_sample(sample_path)
    if not any(human_label(r.get("human_mention")) is not None for r in sample):
        sample = comment_sample(calls, judges, items)
        write_csv(sample_path, sample)
        sample = read_sample(sample_path)
    tables["b_coder_check"] = coder_check(sample, judges)
    for name, rows in tables.items():
        write_csv(tables_dir / f"main_{variant}_{name}.csv", rows)
    (tables_dir / f"main_{variant}_b.md").write_text(render_markdown(tables, variant, judges, len(sample)),
                                                       encoding="utf-8")
    return tables


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--variant", default="baseline")
    p.add_argument("--judges", default=None, help="comma-separated; default: every judge with E1 results")
    args = p.parse_args()
    out = run(args.variant, args.judges.split(",") if args.judges else None)
    print(f"wrote results/tables/main_{args.variant}_b_*.csv and main_{args.variant}_b.md "
          f"({len(out['b_leakage'])} leakage rows, {len(out['b_comments'])} comment rows)")


if __name__ == "__main__":
    main()
