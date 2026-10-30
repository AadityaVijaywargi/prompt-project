"""E4: human grading of the E1 answers and judge-human agreement (analysis/plan.md, E4; brief 4.5).

    python -m lb.e4 sheets [--annotators a1,a2]    blind grading sheets -> data/e4/sheet_<annotator>.csv
    python -m lb.e4 import data/e4/sheet_a1.csv    graded sheet -> data/human_grades.csv (that annotator's rows)
    python -m lb.e4                                tables -> results/tables/main_baseline_e4_*.csv, main_baseline_e4.md

Sample: 100 items, all 60 E5-subset items (so E5 can measure its accuracy cost on them) filled to the full
set's type mix (67 factual, 33 open-ended) round-robin across subjects, seed 20261023. Each annotator grades
every sampled item in all four forms (400 rows) on the E1 rubric, seeing what the judge saw: the English
question, the English reference for factual items, and the answer.

Blinding: a sheet has no item or form column. Its rows come in 4 blocks with every item once per block and
each form in a quarter of each block, shuffled within blocks with a per-annotator seed, so one item's four
versions sit about 100 rows apart. Import rebuilds the row -> (item, form) key from the seed and checks it
against the answer text, so no key file exists.
"""
from __future__ import annotations

import argparse
import csv
import math
import random
import unicodedata
from collections import defaultdict
from itertools import combinations
from pathlib import Path

from .analysis import CRITERIA, SEED, e1_scores, exploratory, fmt, judges_in, load_calls, pval, write_csv
from .config import DATA, RAW, TABLES, experiments_config
from .data import load_quadruples, reference_for
from .runners.common import question_text
from .runners.e5_mitigation import NON_EN, subset_for
from .schema import FORMS, HumanGrade
from .stats import bootstrap_agreement_ci, bootstrap_agreement_diff_ci, paired_bootstrap_ci, wilcoxon_p

N_ITEMS = 100
E4_DIR = DATA / "e4"
GRADES = DATA / "human_grades.csv"
DEFAULT_ANNOTATORS = ("a1", "a2")
MIN_RATERS = 2              # a cell enters judge-human agreement only with this many human grades
SHEET_COLUMNS = ["row_id", "question", "reference_answer", "answer", *CRITERIA, "notes"]
GRADE_COLUMNS = list(HumanGrade.model_fields)


# ---------- sample and sheets ----------

def e4_sample(items, exp_cfg: dict, size: int = N_ITEMS) -> list:
    """The E5 subset plus a seeded fill to `size` items, per type in proportion to the full set, round-robin
    across subjects. Returned in data order."""
    picked = {q.item_id for q in subset_for(exp_cfg, items)}
    rng = random.Random(f"{exp_cfg['seed']}-e4-sample")
    quota = {"factual": round(size * sum(q.type == "factual" for q in items) / len(items))}
    quota["open_ended"] = size - quota["factual"]
    for t in ("factual", "open_ended"):
        have = sum(q.type == t for q in items if q.item_id in picked)
        by_subject = defaultdict(list)
        for q in sorted((q for q in items if q.type == t and q.item_id not in picked), key=lambda q: q.item_id):
            by_subject[q.subject].append(q.item_id)
        subjects = sorted(by_subject)
        rng.shuffle(subjects)
        for s in subjects:
            rng.shuffle(by_subject[s])
        while have < quota[t] and any(by_subject.values()):
            for s in subjects:
                if by_subject[s] and have < quota[t]:
                    picked.add(by_subject[s].pop())
                    have += 1
    return [q for q in items if q.item_id in picked]


def layout(sample, annotator: str) -> list[tuple[str, str, str]]:
    """[(row_id, item_id, form)] for one annotator's sheet: 4 blocks, each item once per block, forms balanced
    within blocks (item i gets form (offset_i + block) mod 4), rows shuffled within each block."""
    rng = random.Random(f"{SEED}-e4-{annotator}")
    offsets = [k % len(FORMS) for k in range(len(sample))]
    rng.shuffle(offsets)
    rows = []
    for block in range(len(FORMS)):
        cells = [(q.item_id, FORMS[(o + block) % len(FORMS)]) for q, o in zip(sample, offsets)]
        rng.shuffle(cells)
        rows += cells
    return [(f"{annotator}-{n:03d}", item_id, form) for n, (item_id, form) in enumerate(rows, 1)]


def sheet_rows(sample, annotator: str, exp_cfg: dict) -> list[dict]:
    by_id = {q.item_id: q for q in sample}
    out = []
    for row_id, item_id, form in layout(sample, annotator):
        q = by_id[item_id]
        out.append({"row_id": row_id, "question": question_text(q, exp_cfg),
                    "reference_answer": reference_for(q, exp_cfg["reference_guided"]) or "",
                    "answer": q.answers.get(form).text, **{c: "" for c in CRITERIA}, "notes": ""})
    return out


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:   # utf-8-sig: Excel adds a BOM on save
        return list(csv.DictReader(f))


def write_sheet(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:   # BOM so Excel shows Devanagari
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)


def write_sheets(annotators, items=None, exp_cfg: dict | None = None, out_dir: Path = E4_DIR) -> list[Path]:
    """One sheet per annotator plus data/e4/sample.csv. A sheet that already holds a grade is left as it is."""
    exp_cfg = exp_cfg or experiments_config()
    items = items if items is not None else load_quadruples()
    sample = e4_sample(items, exp_cfg)
    e5 = {q.item_id for q in subset_for(exp_cfg, items)}
    write_sheet(out_dir / "sample.csv", [{"item_id": q.item_id, "type": q.type, "subject": q.subject,
                                          "in_e5_subset": q.item_id in e5} for q in sample],
                ["item_id", "type", "subject", "in_e5_subset"])
    written = []
    for a in annotators:
        path = out_dir / f"sheet_{a}.csv"
        if path.exists() and any((r.get(c) or "").strip() for r in read_csv(path) for c in CRITERIA):
            print(f"{path} already holds grades: left as it is")
            continue
        write_sheet(path, sheet_rows(sample, a, exp_cfg), SHEET_COLUMNS)
        written.append(path)
    return written


# ---------- import ----------

def same_text(a: str, b: str) -> bool:
    """Equal up to Unicode normalisation and whitespace (spreadsheets may rewrap or change line endings)."""
    norm = lambda s: " ".join(unicodedata.normalize("NFC", s or "").split())
    return norm(a) == norm(b)


def grade_value(v: str) -> int | None:
    v = (v or "").strip()
    if not v:
        return None
    try:
        x = float(v)                 # spreadsheets may save 4 as 4.0
    except ValueError:
        raise ValueError(f"not a number: {v!r}") from None
    if x != int(x) or not 1 <= x <= 5:
        raise ValueError(f"grades are whole numbers 1-5, got {v!r}")
    return int(x)


def parse_sheet(rows: list[dict], items=None, exp_cfg: dict | None = None) -> tuple[str, list[HumanGrade]]:
    """Graded sheet rows -> (annotator, grades). Rows with no grade are skipped; any other problem (unknown
    row id, changed answer text, a partly graded row, a value outside 1-5) stops the import with every
    problem listed."""
    exp_cfg = exp_cfg or experiments_config()
    items = items if items is not None else load_quadruples()
    sample = e4_sample(items, exp_cfg)
    annotators = {r["row_id"].rsplit("-", 1)[0] for r in rows if (r.get("row_id") or "").strip()}
    if len(annotators) != 1:
        raise SystemExit(f"a sheet holds one annotator's rows; found row ids for {sorted(annotators) or 'none'}")
    annotator = annotators.pop()
    key = {row_id: (item_id, form) for row_id, item_id, form in layout(sample, annotator)}
    by_id = {q.item_id: q for q in sample}
    grades, problems = [], []
    for r in rows:
        row_id = (r.get("row_id") or "").strip()
        if row_id not in key:
            problems.append(f"{row_id or '(blank row_id)'}: not a row of {annotator}'s sheet")
            continue
        item_id, form = key[row_id]
        if not same_text(r.get("answer", ""), by_id[item_id].answers.get(form).text):
            problems.append(f"{row_id}: answer text differs from the sheet as written (rows moved or text "
                            "changed? save as CSV UTF-8)")
            continue
        try:
            values = {c: grade_value(r.get(c)) for c in CRITERIA}
        except ValueError as e:
            problems.append(f"{row_id}: {e}")
            continue
        if all(v is None for v in values.values()):
            continue
        if any(v is None for v in values.values()):
            problems.append(f"{row_id}: grade all four criteria or none")
            continue
        grades.append(HumanGrade(annotator_id=annotator, item_id=item_id, form=form, **values,
                                 notes=(r.get("notes") or "").strip()))
    if problems:
        raise SystemExit("nothing imported; fix these rows first:\n  " + "\n  ".join(problems))
    return annotator, grades


def import_sheet(path: Path, grades_path: Path = GRADES, items=None, exp_cfg: dict | None = None) -> list[HumanGrade]:
    """Replace the sheet's annotator's rows in human_grades.csv with the graded rows of the sheet."""
    annotator, grades = parse_sheet(read_csv(path), items, exp_cfg)
    kept = [r for r in (read_csv(grades_path) if grades_path.exists() else []) if r["annotator_id"] != annotator]
    rows = kept + [g.model_dump() for g in grades]
    rows.sort(key=lambda r: (r["annotator_id"], r["item_id"], FORMS.index(r["form"])))
    grades_path.parent.mkdir(parents=True, exist_ok=True)
    with open(grades_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=GRADE_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    per_form = {f: sum(g.form == f for g in grades) for f in FORMS}
    print(f"{annotator}: {len(grades)} graded rows imported into {grades_path} ({per_form})")
    return grades


def load_grades(path: Path = GRADES) -> list[HumanGrade]:
    return [HumanGrade.model_validate({**r, **{c: int(r[c]) for c in CRITERIA}}) for r in read_csv(path)] \
        if path.exists() else []


# ---------- analysis ----------

def round_half_up(x: float) -> int:
    return math.floor(x + 0.5)


def with_content(s: dict) -> dict:
    return {**s, "content": (s["correctness"] + s["completeness"] + s["clarity"]) / 3}


def human_scores(grades: list[HumanGrade]) -> dict:
    """{annotator: {(item_id, form): {criterion..., content}}}"""
    out = defaultdict(dict)
    for g in grades:
        out[g.annotator_id][(g.item_id, g.form)] = with_content({c: float(getattr(g, c)) for c in CRITERIA})
    return out


def consensus(by_annotator: dict) -> dict:
    """{(item_id, form): mean human scores} over cells graded by at least MIN_RATERS annotators."""
    cells = defaultdict(list)
    for scores in by_annotator.values():
        for cell, s in scores.items():
            cells[cell].append(s)
    return {cell: {k: sum(s[k] for s in ss) / len(ss) for k in ss[0]} | {"raters": len(ss)}
            for cell, ss in cells.items() if len(ss) >= MIN_RATERS}


def agreement_row(measure: str, x: list[float], y: list[float]) -> dict:
    est, lo, hi = bootstrap_agreement_ci(measure, x, y, seed=SEED)
    return {"n": len(x), "agreement": est, "ci_low": lo, "ci_high": hi, "exploratory": exploratory(len(x))}


def coverage(by_annotator: dict, mean: dict, sample) -> list[dict]:
    rows = [{"who": a, "form": f, "graded": sum(1 for (i, ff) in s if ff == f), "of": len(sample)}
            for a, s in sorted(by_annotator.items()) for f in FORMS]
    rows += [{"who": f"consensus (>= {MIN_RATERS} raters)", "form": f,
              "graded": sum(1 for (i, ff) in mean if ff == f), "of": len(sample)} for f in FORMS]
    return rows


def inter_annotator(by_annotator: dict, sample) -> list[dict]:
    """E4.1: quadratic-weighted kappa per annotator pair, criterion and form; bootstrap CI over items."""
    rows = []
    for a, b in combinations(sorted(by_annotator), 2):
        for form in FORMS:
            cells = [(q.item_id, form) for q in sample
                     if (q.item_id, form) in by_annotator[a] and (q.item_id, form) in by_annotator[b]]
            for c in CRITERIA:
                rows.append({"pair": f"{a} vs {b}", "form": form, "criterion": c,
                             **agreement_row("qwk", [by_annotator[a][k][c] for k in cells],
                                             [by_annotator[b][k][c] for k in cells])})
    return rows


def judge_human_pairs(judge_scores: dict, mean: dict, sample, form: str, key: str) -> list[tuple[str, float, float]]:
    """[(item_id, judge, human)] for cells with both; criteria compare against the rounded human mean."""
    out = []
    for q in sample:
        j, h = judge_scores.get(q.item_id, {}).get(form), mean.get((q.item_id, form))
        if j is not None and h is not None:
            out.append((q.item_id, j[key], h[key] if key == "content" else round_half_up(h[key])))
    return out


MEASURES = (("content", "spearman"), *((c, "qwk") for c in CRITERIA))


def judge_human(scores: dict, mean: dict, judges: list[str], sample) -> list[dict]:
    """E4.2: per judge and form, Spearman on content and quadratic-weighted kappa per criterion against the
    mean human score (rounded half up for kappa)."""
    rows = []
    for j in judges:
        for form in FORMS:
            for key, measure in MEASURES:
                p = judge_human_pairs(scores[j], mean, sample, form, key)
                rows.append({"judge": j, "form": form, "score": key, "measure": measure,
                             **agreement_row(measure, [x for _, x, _ in p], [y for _, _, y in p])})
    return rows


def form_drop(scores: dict, mean: dict, judges: list[str], sample) -> list[dict]:
    """E4.3: judge-human agreement in each form minus in en, on items with both; items resampled together."""
    rows = []
    for j in judges:
        for form in NON_EN:
            for key, measure in MEASURES:
                p = {i: (x, y) for i, x, y in judge_human_pairs(scores[j], mean, sample, form, key)}
                p0 = {i: (x, y) for i, x, y in judge_human_pairs(scores[j], mean, sample, "en", key)}
                ids = [i for i in p if i in p0]
                new, base, diff, lo, hi = bootstrap_agreement_diff_ci(
                    measure, [p[i][0] for i in ids], [p[i][1] for i in ids],
                    [p0[i][0] for i in ids], [p0[i][1] for i in ids], seed=SEED)
                rows.append({"judge": j, "comparison": f"{form} vs en", "score": key, "measure": measure,
                             "n": len(ids), "agreement": new, "agreement_en": base, "change": diff,
                             "ci_low": lo, "ci_high": hi, "exploratory": exploratory(len(ids))})
    return rows


def form_gap(scores: dict, mean: dict, judges: list[str], sample) -> list[dict]:
    """E4.4: content(form) - content(en) per item for the mean human grade, and for each judge on the same
    items, so the judges' E1 gap can be read against the human one."""
    rows = []
    for form in NON_EN:
        ids = [q.item_id for q in sample if (q.item_id, form) in mean and (q.item_id, "en") in mean]
        for who in ("human (mean)", *judges):
            if who == "human (mean)":
                s = {i: {f: mean[(i, f)] for f in (form, "en")} for i in ids}
            else:
                s = {i: scores[who][i] for i in ids if {form, "en"} <= set(scores[who].get(i, {}))}
            d = [s[i][form]["content"] - s[i]["en"]["content"] for i in s]
            m, lo, hi = paired_bootstrap_ci(d, seed=SEED)
            rows.append({"who": who, "comparison": f"{form} vs en", "n": len(d), "mean_d": m, "ci_low": lo,
                         "ci_high": hi, "wilcoxon_p": wilcoxon_p(d) if d else float("nan"),
                         "exploratory": exploratory(len(d))})
    return rows


# ---------- output ----------

def flag(r: dict) -> str:
    return " (exploratory)" if r.get("exploratory") else ""


def ci(r: dict, key: str) -> str:
    return f"{fmt(r[key])} [{fmt(r['ci_low'])}, {fmt(r['ci_high'])}]"


def render_markdown(tables: dict, judges: list[str], annotators: list[str], n_sample: int) -> str:
    L = ["# E4: human grading and judge-human agreement (baseline prompt)", "",
         f"Generated by `python -m lb.e4` from data/human_grades.csv and the E1 baseline records (pilot runs "
         f"excluded), per analysis/plan.md. Sample: {n_sample} items in four forms (data/e4/sample.csv). "
         f"Annotators: {', '.join(annotators) or 'none yet'}. Judges: {', '.join(judges)}. Bootstrap 95% CIs over "
         f"items (10,000 resamples, seed {SEED}); cells with fewer than 30 items are exploratory. Judge-human "
         f"agreement uses cells graded by at least {MIN_RATERS} annotators.", ""]
    if not annotators:
        L += ["**No human grades yet.** Grading sheets: data/e4/sheet_<annotator>.csv; import them with "
              "`python -m lb.e4 import <sheet>`.", ""]
    L += ["## Coverage", "", "| Who | Form | Graded | Of |", "|---|---|---|---|"]
    L += [f"| {r['who']} | {r['form']} | {r['graded']} | {r['of']} |" for r in tables["e4_coverage"]]
    L += ["", "## E4.1: inter-annotator agreement (quadratic-weighted kappa)", "",
          "| Pair | Form | Criterion | n | kappa [95% CI] |", "|---|---|---|---|---|"]
    L += [f"| {r['pair']} | {r['form']} | {r['criterion']} | {r['n']}{flag(r)} | {ci(r, 'agreement')} |"
          for r in tables["e4_iaa"]]
    L += ["", "## E4.2: judge vs mean human score", "",
          "Content: Spearman. Criteria: quadratic-weighted kappa, human mean rounded half up.", "",
          "| Judge | Form | Score | Measure | n | Agreement [95% CI] |", "|---|---|---|---|---|---|"]
    L += [f"| {r['judge']} | {r['form']} | {r['score']} | {r['measure']} | {r['n']}{flag(r)} | {ci(r, 'agreement')} |"
          for r in tables["e4_judge_human"]]
    L += ["", "## E4.3: does judge-human agreement drop outside English?", "",
          "Agreement in the form minus agreement in en, on items with both; paired bootstrap.", "",
          "| Judge | Comparison | Score | Measure | n | Form | en | Change [95% CI] |",
          "|---|---|---|---|---|---|---|---|"]
    L += [f"| {r['judge']} | {r['comparison']} | {r['score']} | {r['measure']} | {r['n']}{flag(r)} | "
          f"{fmt(r['agreement'])} | {fmt(r['agreement_en'])} | {ci(r, 'change')} |" for r in tables["e4_form_drop"]]
    L += ["", "## E4.4: form gap in content, humans and judges on the same items", "",
          "d = content(form) - content(en); paired bootstrap, two-sided Wilcoxon. Descriptive.", "",
          "| Who | Comparison | n | mean d [95% CI] | Wilcoxon p |", "|---|---|---|---|---|"]
    L += [f"| {r['who']} | {r['comparison']} | {r['n']}{flag(r)} | {ci(r, 'mean_d')} | {pval(r['wilcoxon_p'])} |"
          for r in tables["e4_form_gap"]]
    return "\n".join(L) + "\n"


def run(grades_path: Path = GRADES, raw_dir: Path = RAW, tables_dir: Path = TABLES, items=None,
        exp_cfg: dict | None = None) -> dict:
    exp_cfg = exp_cfg or experiments_config()
    items = items if items is not None else load_quadruples()
    sample = e4_sample(items, exp_cfg)
    calls = load_calls("baseline", None, raw_dir)
    judges = judges_in({k: v for k, v in calls.items() if k[0] == "e1"})
    scores = {j: e1_scores(calls, j, sample) for j in judges}
    by_annotator = human_scores(load_grades(grades_path))
    mean = consensus(by_annotator)
    tables = {"e4_coverage": coverage(by_annotator, mean, sample),
              "e4_iaa": inter_annotator(by_annotator, sample),
              "e4_judge_human": judge_human(scores, mean, judges, sample),
              "e4_form_drop": form_drop(scores, mean, judges, sample),
              "e4_form_gap": form_gap(scores, mean, judges, sample)}
    for name, rows in tables.items():
        write_csv(tables_dir / f"main_baseline_{name}.csv", rows)
    (tables_dir / "main_baseline_e4.md").write_text(
        render_markdown(tables, judges, sorted(by_annotator), len(sample)), encoding="utf-8")
    return tables


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("sheets")
    s.add_argument("--annotators", default=",".join(DEFAULT_ANNOTATORS))
    i = sub.add_parser("import")
    i.add_argument("sheet", type=Path)
    args = p.parse_args()
    if args.cmd == "sheets":
        for path in write_sheets(args.annotators.split(",")):
            print(f"wrote {path}")
    elif args.cmd == "import":
        import_sheet(args.sheet)
    else:
        t = run()
        print(f"wrote results/tables/main_baseline_e4_*.csv and main_baseline_e4.md "
              f"({sum(r['graded'] for r in t['e4_coverage'] if not r['who'].startswith('consensus'))} human grades)")


if __name__ == "__main__":
    main()
