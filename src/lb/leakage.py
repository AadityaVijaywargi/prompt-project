"""Section B of analysis/plan.md: criterion leakage (B0-B3) and judge-comment coding (B4-B5).

    python -m lb.leakage                           # every judge with main (non-pilot) baseline E1 results
    python -m lb.leakage --judges gpt-oss-120b

Reads only the E1 baseline records (no judge calls) and writes results/tables/main_<variant>_b_*.csv, a
markdown summary main_<variant>_b.md, and a seeded, blind comment sample for two human raters. The additions
of 2026-10-27 (item-type split, B0, copy check, Kendall's tau-b, Chinese lexicon, two raters) are post hoc
deviations logged in analysis/plan.md and labelled as such in the output.
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
from .stats import (binom_test_half, bootstrap_slope_ci, cohen_kappa_binary_ci, holm, kendall_tau_b,
                    log_length_ratio_slope, paired_bootstrap_ci)

FORMS = ("hi", "hi_rom", "hinglish")
CRITERIA = ("correctness", "completeness", "clarity")
SUBSETS = ("all", "factual", "open_ended")   # "all" is pre-registered; the item-type split is post hoc
SAMPLE_PER_CELL = 25
# Post hoc (2026-10-27): a criterion copies language_quality when the two are identical on at least this share
# of a judge's calls where either score is below 5 (at the ceiling, 5 = 5 says nothing).
DEGENERATE_SHARE = 0.90

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
# Post hoc (2026-10-27, logged in analysis/plan.md): qwen wrote some comments in Chinese, which the fixed
# lexicon cannot match. Reported as lexicon "v1+zh" next to the fixed "v1", never in place of it.
MENTION_PATTERNS_ZH = {
    "language": [r"语言", r"印地语", r"印地文", r"英语", r"英文", r"中文", r"翻译"],
    "script": [r"天城文", r"罗马字", r"罗马化", r"罗马拼音", r"音译", r"转写"],
    "mixing": [r"混合", r"混用", r"夹杂", r"语码"],
    "fluency": [r"流畅", r"语法", r"拼写", r"通顺", r"口语"],
}


def _compile(patterns: dict) -> dict:
    return {cat: [re.compile(p, re.IGNORECASE) for p in pats] for cat, pats in patterns.items()}


LEXICONS = {"v1": _compile(MENTION_PATTERNS),
            "v1+zh": _compile({c: MENTION_PATTERNS[c] + MENTION_PATTERNS_ZH[c] for c in MENTION_PATTERNS})}
BIAS_CATEGORIES = ("language", "script", "mixing")
CJK = re.compile(r"[一-鿿]")


def code_comment(text: str | None, lexicon: str = "v1") -> dict:
    """{category: bool} for each lexicon category, plus 'mention' = any of language, script, mixing."""
    t = text or ""
    codes = {cat: any(p.search(t) for p in pats) for cat, pats in LEXICONS[lexicon].items()}
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


def in_subset(items, subset: str) -> list:
    return [q for q in items if subset == "all" or q.type == subset]


# ---------- B0-B3: halo baseline, copy check, leakage ----------

def paired_deltas(scores: dict, items, form: str, criterion: str) -> tuple[list[float], list[float]]:
    """(dL, dX): language_quality and criterion differences, form minus en, items with both scored."""
    dl, dx = [], []
    for q in items:
        s = scores.get(q.item_id, {})
        if form in s and "en" in s:
            dl.append(s[form]["language_quality"] - s["en"]["language_quality"])
            dx.append(s[form][criterion] - s["en"][criterion])
    return dl, dx


def slope_row(x: list[float], y: list[float]) -> dict:
    """OLS slope of y on x (bootstrap CI, OLS p) and Kendall's tau-b as the rank-based check."""
    slope, lo, hi = bootstrap_slope_ci(x, y, seed=SEED)
    estimable = not math.isnan(slope)
    ols = log_length_ratio_slope(y, x) if estimable else {}
    tau, tau_p = kendall_tau_b(x, y)
    return {"n": len(x), "sd_x": float(np.std(x)) if x else float("nan"), "slope": slope,
            "ci_low": lo, "ci_high": hi, "slope_p": ols.get("slope_p", float("nan")), "estimable": estimable,
            "y_constant": bool(y) and float(np.var(y)) == 0, "kendall_tau": tau, "kendall_p": tau_p,
            "exploratory": exploratory(len(x))}


def same_move(dl: list[float], dx: list[float]) -> dict:
    """How often the criterion moved by exactly dL, among items where language_quality moved."""
    moved = [(l, x) for l, x in zip(dl, dx) if l != 0]
    return {"moved": len(moved), "same_move": sum(l == x for l, x in moved)}


def copy_check(calls: dict, judges: list[str], items) -> list[dict]:
    """Per judge and criterion, over all forms: share of calls with criterion == language_quality among calls
    where either is below 5. At or above DEGENERATE_SHARE the criterion is flagged as a copy."""
    rows = []
    for j in judges:
        cells = [by_form[f] for by_form in e1_scores(calls, j, items).values() for f in by_form]
        for crit in CRITERIA:
            off = [c for c in cells if min(c[crit], c["language_quality"]) < 5]
            r = {"judge": j, "criterion": crit, **prop(sum(c[crit] == c["language_quality"] for c in off), len(off))}
            r["degenerate"] = bool(off) and r["rate"] >= DEGENERATE_SHARE
            rows.append(r)
    return rows


def halo_baseline(scores: dict, judge: str, items) -> list[dict]:
    """B0: slope of each criterion on language_quality across English answers, where no form changes."""
    rows = []
    for subset in SUBSETS:
        en = [scores[q.item_id]["en"] for q in in_subset(items, subset) if "en" in scores.get(q.item_id, {})]
        lq = [e["language_quality"] for e in en]
        for crit in CRITERIA:
            rows.append({"judge": judge, "id": "B0", "subset": subset, "form": "en", "criterion": crit,
                         **slope_row(lq, [e[crit] for e in en])})
    return rows


SIGNS = (("dL < 0", lambda v: v < 0), ("dL = 0", lambda v: v == 0), ("dL > 0", lambda v: v > 0))


def analyse_leakage(calls: dict, judges: list[str], items) -> dict:
    halo, leakage, by_sign = [], [], []
    for j in judges:
        scores = e1_scores(calls, j, items)
        halo += halo_baseline(scores, j, items)
        for subset in SUBSETS:
            sub = in_subset(items, subset)
            b1, b2 = [], []
            for form in FORMS:
                for crit in CRITERIA:
                    dl, dx = paired_deltas(scores, sub, form, crit)
                    (b1 if crit == "correctness" else b2).append(
                        {"judge": j, "id": "B1" if crit == "correctness" else "B2", "subset": subset, "form": form,
                         "criterion": crit, **slope_row(dl, dx), **same_move(dl, dx)})
                dl, dc = paired_deltas(scores, sub, form, "correctness")
                for sign, keep in SIGNS:
                    cell = [c for l, c in zip(dl, dc) if keep(l)]
                    mean, lo, hi = paired_bootstrap_ci(cell, seed=SEED)
                    by_sign.append({"judge": j, "id": "B3", "subset": subset, "form": form, "dL_sign": sign,
                                    "n": len(cell), "mean_dC": mean, "ci_low": lo, "ci_high": hi})
            if subset == "all":   # Holm only over the pre-registered family
                adj = iter(holm([r["slope_p"] for r in b1 if r["estimable"]]))
                for r in b1:
                    r["holm_p"] = next(adj) if r["estimable"] else float("nan")
            leakage += b1 + b2
    copies = copy_check(calls, judges, items)
    degenerate = {(r["judge"], r["criterion"]) for r in copies if r["degenerate"]}
    for r in halo + leakage:
        r["degenerate"] = (r["judge"], r["criterion"]) in degenerate
    return {"b_halo": halo, "b_copy": copies, "b_leakage": leakage, "b_by_sign": by_sign}


# ---------- B4-B5: comments ----------

def comment_rows(scores: dict, texts: dict, judge: str, lexicon: str) -> list[dict]:
    codes = {i: {f: code_comment(t, lexicon) for f, t in by_form.items()} for i, by_form in texts.items()}
    base = {"lexicon": lexicon, "judge": judge}
    en_rate = [c["en"]["mention"] for c in codes.values() if "en" in c]
    rows = [{**base, "id": "B4", "form": "en", "measure": "language-mention rate",
             **prop(sum(en_rate), len(en_rate)), "exploratory": exploratory(len(en_rate))}]
    b4 = []
    for form in FORMS:
        cells = [c for c in codes.values() if form in c]
        k = sum(c[form]["mention"] for c in cells)
        paired = [c for c in cells if "en" in c]
        only_f = sum(c[form]["mention"] and not c["en"]["mention"] for c in paired)
        only_en = sum(c["en"]["mention"] and not c[form]["mention"] for c in paired)
        b4.append({**base, "id": "B4", "form": form, "measure": "language-mention rate", **prop(k, len(cells)),
                   "only_form": only_f, "only_en": only_en, "mcnemar_p": binom_test_half(only_f, only_f + only_en),
                   "exploratory": exploratory(len(cells))})
        for cat in (*BIAS_CATEGORIES, "fluency"):
            rows.append({**base, "id": "B4-cat", "form": form, "measure": f"{cat} mention rate",
                         **prop(sum(c[form][cat] for c in cells), len(cells))})
        dropped = [i for i, s in scores.items() if form in s and "en" in s
                   and s[form]["content"] < s["en"]["content"] and form in codes.get(i, {})]
        silent = sum(not codes[i][form]["mention"] for i in dropped)
        rows.append({**base, "id": "B5", "form": form, "measure": "silent penalty rate",
                     **prop(silent, len(dropped)), "exploratory": exploratory(len(dropped))})
    for r, p in zip(b4, holm([r["mcnemar_p"] for r in b4])):
        r["holm_p"] = p
    return rows + b4


def analyse_comments(calls: dict, judges: list[str], items) -> dict:
    rows, written = [], []
    for j in judges:
        scores, texts = e1_scores(calls, j, items), comments(calls, j, items)
        for lexicon in LEXICONS:
            rows += comment_rows(scores, texts, j, lexicon)
        for form in ("en", *FORMS):
            cells = [t[form] for t in texts.values() if form in t]
            written.append({"judge": j, "form": form, "measure": "comments written in Chinese",
                            **prop(sum(bool(CJK.search(t)) for t in cells), len(cells))})
    order, forms, lexicons = {"B4": 0, "B4-cat": 1, "B5": 2}, ("en", *FORMS), list(LEXICONS)
    rows.sort(key=lambda r: (lexicons.index(r["lexicon"]), judges.index(r["judge"]), order[r["id"]],
                             forms.index(r["form"])))
    return {"b_comments": rows, "b_comment_language": written}


# ---------- human check: two blind raters ----------

LABEL_COLUMNS = ("rater_a", "rater_b", "adjudicated")
HUMAN_YES, HUMAN_NO = {"1", "y", "yes", "true"}, {"0", "n", "no", "false"}


def comment_sample(calls: dict, judges: list[str], items) -> list[dict]:
    """Seeded sample of SAMPLE_PER_CELL comments per judge and form for the two-rater check. Each cell has its
    own seed, so the sample does not depend on judge order or on which other judges are included. The sample
    holds no automated label, so raters code blind to the keyword coder."""
    rows = []
    for j in judges:
        texts = comments(calls, j, items)
        for form in ("en", *FORMS):
            rng = random.Random(f"{SEED}-{j}-{form}")
            pool = sorted((i, t[form]) for i, t in texts.items() if form in t)
            for item_id, text in rng.sample(pool, min(SAMPLE_PER_CELL, len(pool))):
                rows.append({"judge": j, "item_id": item_id, "form": form, "comment": text,
                             **{c: "" for c in LABEL_COLUMNS}})
    return rows


def human_label(value: str | None) -> bool | None:
    """Label cell -> True / False, or None if not coded yet. Accepts 1/0, y/n, yes/no, true/false."""
    v = (value or "").strip().lower()
    if not v:
        return None
    if v in HUMAN_YES or v in HUMAN_NO:
        return v in HUMAN_YES
    raise ValueError(f"labels must be one of {sorted(HUMAN_YES | HUMAN_NO)} or blank, got {value!r}")


def gold_label(r: dict) -> bool | None:
    """Agreed human label: the adjudicated label if given, else the two raters' label when they agree."""
    adj = human_label(r.get("adjudicated"))
    if adj is not None:
        return adj
    a, b = human_label(r.get("rater_a")), human_label(r.get("rater_b"))
    return a if a is not None and a == b else None


def read_sample(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:   # utf-8-sig: Excel adds a BOM on save
        return list(csv.DictReader(f))


def has_labels(sample: list[dict]) -> bool:
    return any(human_label(r.get(c)) is not None for r in sample for c in (*LABEL_COLUMNS, "human_mention"))


def coder_check(sample: list[dict], judges: list[str]) -> dict:
    """Rater agreement (Cohen's kappa) and the keyword coder's precision and recall against the agreed labels,
    per judge and pooled, for each lexicon."""
    agreement, accuracy = [], []
    for j in (*judges, "all"):
        rows = [r for r in sample if j in ("all", r["judge"])]
        both = [(human_label(r.get("rater_a")), human_label(r.get("rater_b"))) for r in rows]
        both = [(a, b) for a, b in both if a is not None and b is not None]
        kappa, lo, hi = cohen_kappa_binary_ci([a for a, _ in both], [b for _, b in both], seed=SEED)
        gold = [(r["comment"], g) for r in rows if (g := gold_label(r)) is not None]
        agreement.append({"judge": j, "rows": len(rows), "both_coded": len(both), "agree": sum(a == b for a, b in both),
                          "kappa": kappa, "ci_low": lo, "ci_high": hi, "agreed_labels": len(gold)})
        for lexicon in LEXICONS:
            pairs = [(code_comment(t, lexicon)["mention"], g) for t, g in gold]
            tp = sum(c and g for c, g in pairs)
            fp = sum(c and not g for c, g in pairs)
            fn = sum(g and not c for c, g in pairs)
            for measure, k, n in (("precision", tp, tp + fp), ("recall", tp, tp + fn)):
                accuracy.append({"lexicon": lexicon, "judge": j, "measure": measure, "labelled": len(gold),
                                 "tp": tp, "fp": fp, "fn": fn, **prop(k, n)})
    return {"b_rater_agreement": agreement, "b_coder_check": accuracy}


# ---------- output ----------

def flag(r: dict) -> str:
    return " (exploratory)" if r.get("exploratory") else ""


def ci(r: dict, key: str) -> str:
    return f"{fmt(r[key])} [{fmt(r['ci_low'])}, {fmt(r['ci_high'])}]"


def slope_cell(r: dict) -> str:
    if not r["estimable"]:
        return "not estimable (x constant)"
    return ci(r, "slope") + (" (criterion constant)" if r["y_constant"] else "")


def tau_cell(r: dict) -> str:
    return "n/a" if math.isnan(r["kendall_tau"]) else f"{fmt(r['kendall_tau'])} ({pval(r['kendall_p'])})"


def crit_cell(r: dict) -> str:
    return r["criterion"] + (" (copies LQ)" if r.get("degenerate") else "")


def render_markdown(tables: dict, variant: str, judges: list[str], sample_size: int) -> str:
    agreed = next((r["agreed_labels"] for r in tables["b_rater_agreement"] if r["judge"] == "all"), 0)
    status = ("validated by the two-rater check below" if sample_size and agreed == sample_size
              else f"unvalidated: {agreed} of {sample_size} sample comments have an agreed human label")
    L = [f"# Section B: criterion leakage and judge comments ({variant} prompt, post hoc)", "",
         f"Judges: {', '.join(judges)}. Generated by `python -m lb.leakage` from the E1 records in results/raw "
         "(pilot runs excluded), per analysis/plan.md section B. No new judge calls. dC, dX and dL are "
         "correctness, a given criterion and language_quality (LQ), form minus en, on the same item.", "",
         "All of section B is post hoc and exploratory. The item-type split, B0, the copy check, Kendall's tau-b, "
         "the Chinese lexicon and the two-rater check were added on 2026-10-27 after an external audit and are "
         "logged as deviations in analysis/plan.md. All criteria come from one judge call, so co-movement between "
         "them is not evidence that language quality causes the content score to change.", "",
         "## B0: within-English halo baseline (post hoc)", "",
         "English answers only, across items: slope of each criterion on LQ. This is how far the criteria move "
         "together when the language form does not change; read B1-B2 against it.", "",
         "| Judge | Subset | Criterion | n | SD of LQ | slope [95% CI] | Kendall tau-b (p) |", "|---|---|---|---|---|---|---|"]
    L += [f"| {r['judge']} | {r['subset']} | {crit_cell(r)} | {r['n']}{flag(r)} | {fmt(r['sd_x'])} | {slope_cell(r)} | "
          f"{tau_cell(r)} |" for r in tables["b_halo"]]
    L += ["", "## Copy check: does a criterion repeat LQ? (post hoc)", "",
          f"Share of calls (all four forms) where the criterion equals LQ, among calls where either is below 5. "
          f"At or above {DEGENERATE_SHARE:.0%} (a threshold set after seeing these rates) the criterion is flagged as "
          "a copy: its B0-B2 slopes then compare LQ with itself and say nothing about leakage.", "",
          "| Judge | Criterion | identical k / n | share [95% CI] | copies LQ? |", "|---|---|---|---|---|"]
    L += [f"| {r['judge']} | {r['criterion']} | {r['k']} / {r['n']} | {ci(r, 'rate')} | "
          f"{'**yes**' if r['degenerate'] else 'no'} |" for r in tables["b_copy"]]
    L += ["", "## B1-B2: leakage slope (OLS of dX on dL), by item type", "",
          "Bootstrap 95% CI over items (10,000 resamples, seed 20261023). Subset all is the planned analysis, with "
          "Holm across forms per judge for B1; factual and open_ended are a post-hoc split. Kendall's tau-b is a "
          "post-hoc rank-based check for the bounded 1-5 scale. dX = dL counts the items where the criterion moved "
          "by exactly dL, among items where LQ moved.", "",
          "| Judge | ID | Subset | Form | Criterion | n | SD of dL | slope [95% CI] | OLS p | Holm p | "
          "Kendall tau-b (p) | dX = dL |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in tables["b_leakage"]:
        L.append(f"| {r['judge']} | {r['id']} | {r['subset']} | {r['form']} | {crit_cell(r)} | {r['n']}{flag(r)} | "
                 f"{fmt(r['sd_x'])} | {slope_cell(r)} | {pval(r['slope_p'])} | "
                 f"{pval(r['holm_p']) if 'holm_p' in r else '-'} | {tau_cell(r)} | {r['same_move']} / {r['moved']} |")
    L += ["", "## B3: mean dC by the sign of dL (descriptive)", "",
          "| Judge | Subset | Form | dL | n | mean dC [95% CI] |", "|---|---|---|---|---|---|"]
    L += [f"| {r['judge']} | {r['subset']} | {r['form']} | {r['dL_sign']} | {r['n']} | {ci(r, 'mean_dC')} |"
          for r in tables["b_by_sign"]]
    L += ["", f"## B4-B5: judge comments (keyword coder, {status})", "",
          "Mention = the comment names language, script or code-mixing. Lexicon v1 is the one fixed in the plan; "
          "v1+zh adds Chinese terms (post-hoc deviation, because one judge wrote some comments in Chinese; see the "
          "next table). B4 p is an exact McNemar test vs the same item's en comment, Holm across forms per judge "
          "and lexicon. B5 = share of content drops vs en whose comment names none of these.", "",
          "| Lexicon | Judge | ID | Form | Measure | k / n | Rate [95% CI] | McNemar p (Holm) |",
          "|---|---|---|---|---|---|---|---|"]
    for r in tables["b_comments"]:
        p = f"{pval(r['mcnemar_p'])} ({pval(r['holm_p'])})" if "mcnemar_p" in r else "-"
        L.append(f"| {r['lexicon']} | {r['judge']} | {r['id']} | {r['form']} | {r['measure']}{flag(r)} | "
                 f"{r['k']} / {r['n']} | {ci(r, 'rate')} | {p} |")
    L += ["", "## Comment language (post hoc)", "", "| Judge | Form | Measure | k / n | Rate [95% CI] |",
          "|---|---|---|---|---|"]
    L += [f"| {r['judge']} | {r['form']} | {r['measure']} | {r['k']} / {r['n']} | {ci(r, 'rate')} |"
          for r in tables["b_comment_language"]]
    L += ["", "## Coder check: two raters, then the keyword coder against their agreed labels", "",
          f"Seeded sample of {SAMPLE_PER_CELL} comments per judge and form in main_{variant}_b_comment_sample.csv. "
          "Two raters fill rater_a and rater_b with 1/0 (yes/no) without seeing each other's labels; the sample "
          "holds no automated label. A third person fills adjudicated where they disagree. Positive = the comment "
          "names language, script or code-mixing. Agreed label = adjudicated, else the raters' label when they "
          "agree. Bootstrap 95% CI for kappa, Wilson 95% CI for precision and recall.", "",
          "| Judge | rows | both coded | agree | Cohen's kappa [95% CI] | agreed labels |", "|---|---|---|---|---|---|"]
    L += [f"| {r['judge']} | {r['rows']} | {r['both_coded']} | {r['agree']} | {ci(r, 'kappa')} | {r['agreed_labels']} |"
          for r in tables["b_rater_agreement"]]
    L += ["", "| Lexicon | Judge | Measure | labelled | TP / FP / FN | Rate [95% CI] |", "|---|---|---|---|---|---|"]
    L += [f"| {r['lexicon']} | {r['judge']} | {r['measure']} | {r['labelled']} | {r['tp']} / {r['fp']} / {r['fn']} | "
          f"{ci(r, 'rate')} |" for r in tables["b_coder_check"]]
    return "\n".join(L) + "\n"


def run(variant: str = "baseline", judges: list[str] | None = None, raw_dir: Path = RAW,
        tables_dir: Path = TABLES) -> dict:
    calls = load_calls(variant, judges, raw_dir)
    judges = judges or judges_in({k: v for k, v in calls.items() if k[0] == "e1"})
    if not judges:
        raise SystemExit(f"no main-study {variant} E1 results in {raw_dir}")
    items = load_quadruples()
    tables = {**analyse_leakage(calls, judges, items), **analyse_comments(calls, judges, items)}
    # Never overwrite human coding: once any label is filled in, the sample file is left as it is.
    sample_path = tables_dir / f"main_{variant}_b_comment_sample.csv"
    sample = read_sample(sample_path)
    if has_labels(sample):
        if not all(c in sample[0] for c in LABEL_COLUMNS):
            raise SystemExit(f"{sample_path} holds labels in an older format; move them into the "
                             f"{', '.join(LABEL_COLUMNS)} columns first")
    else:
        write_csv(sample_path, comment_sample(calls, judges, items))
        sample = read_sample(sample_path)
    tables.update(coder_check(sample, judges))
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
