"""E5: prompt-level mitigations. Reruns E1-E3 on the E5 subset under one prompt variant.

    python -m lb.runners.e5_mitigation --variant bias_aware                     # prints the budget only
    python -m lb.runners.e5_mitigation --variant bias_aware --judges qwen2.5-7b-local --yes
    python -m lb.runners.e5_mitigation --variant translate_then_judge --yes     # translates first, then judges

Subset: SUBSET_SIZE items stratified by type (in proportion to the full set) and spread across subjects;
the factual picks are items with a verified wrong twin, so E3 runs on the subset's own items. The subset
depends only on the data and the seed, so every judge and variant sees the same items, and --shard splits
the subset (not the full item list). translate_then_judge first translates the subset's hi, hi_rom and
hinglish answers with the one fixed translator (experiments.yaml e5.translator; English passes through),
then judges the translations with the baseline English rubric. Variant majority_vote needs no calls
(lb.mitigation builds it from baseline records).
"""
from __future__ import annotations

import random
from collections import defaultdict

from .. import prompts
from ..analysis import load_calls
from ..config import experiments_config
from ..data import load_quadruples
from .common import CallSpec, answer_text, plan_pairwise, plan_pointwise, run, runner_args, select_shard

TRANSLATE = "e5_translate"
TRANSLATE_VARIANT = "translate_then_judge"
NON_EN = ("hi", "hi_rom", "hinglish")


def e5_subset(items, size: int, seed: int) -> list:
    """Stratified, seeded subset: per type a quota in proportion to the full set, filled round-robin across
    subjects. Factual picks come from items with a verified wrong twin first. Returned in data order."""
    rng = random.Random(f"{seed}-e5-subset")
    picked = set()
    types = ("factual", "open_ended")
    quota = {"factual": round(size * sum(q.type == "factual" for q in items) / len(items))}
    quota["open_ended"] = size - quota["factual"]
    for t in types:
        pool = [q for q in items if q.type == t]
        if t == "factual":   # twins first, so E3 can run on the subset's own items
            pool = [q for q in pool if q.wrong_usable] or pool
        by_subject = defaultdict(list)
        for q in sorted(pool, key=lambda q: q.item_id):
            by_subject[q.subject].append(q)
        subjects = sorted(by_subject)
        rng.shuffle(subjects)
        for s in subjects:
            rng.shuffle(by_subject[s])
        taken = 0
        while taken < quota[t] and any(by_subject.values()):
            for s in subjects:
                if by_subject[s] and taken < quota[t]:
                    picked.add(by_subject[s].pop().item_id)
                    taken += 1
    return [q for q in items if q.item_id in picked]


def subset_for(exp_cfg: dict, items=None, shard: str | None = None) -> list:
    e5 = exp_cfg["experiments"]["e5"]
    subset = e5_subset(items if items is not None else load_quadruples(), e5["subset_size"], exp_cfg["seed"])
    return select_shard(subset, shard)


def plan_translations(subset, translator: str) -> list[CallSpec]:
    return [CallSpec(TRANSLATE, translator, TRANSLATE_VARIANT, q.item_id, "text", (f,), None,
                     prompts.render_translation(answer_text(q, f)))
            for q in subset for f in NON_EN]


def translations(calls: dict, translator: str) -> dict:
    """{(item_id, form): English text} from parsed translator records."""
    return {(k[2], k[3][0]): p["text"] for k, p in calls.items() if k[0] == TRANSLATE and k[1] == translator}


def translated_text_of(texts: dict):
    """Answer text for translate_then_judge: non-English correct answers come from the translations."""
    def text_of(q, selector: str) -> str:
        if selector in NON_EN:
            if (q.item_id, selector) not in texts:
                raise SystemExit(f"no translation of {q.item_id} {selector}: run the translation step first "
                                 f"(--variant {TRANSLATE_VARIANT} --yes)")
            return texts[(q.item_id, selector)]
        return answer_text(q, selector)
    return text_of


def plan(subset, judges, exp_cfg, variant, text_of=answer_text) -> list[CallSpec]:
    if variant not in exp_cfg["experiments"]["e5"]["variants"]:
        raise SystemExit(f"--variant must be one of {exp_cfg['experiments']['e5']['variants']}, got {variant!r}")
    ex = exp_cfg["experiments"]
    specs = plan_pointwise("e1", subset, judges, variant, exp_cfg, text_of=text_of)
    specs += plan_pairwise("e2", subset, judges, variant, exp_cfg, [tuple(p) for p in ex["e2"]["pairs"]],
                           text_of=text_of)
    pairs = [("wrong:en", f) for f in ex["e3"]["correct_forms"]] + [("wrong:en", "en")]   # control: accuracy cost
    specs += plan_pairwise("e3", [q for q in subset if q.wrong_usable], judges, variant, exp_cfg, pairs,
                           text_of=text_of)
    return specs


def main() -> None:
    p = runner_args(__doc__)
    args = p.parse_args()
    if args.pilot or args.include_unverified:
        raise SystemExit("E5 runs on the verified main-study subset only (no --pilot, no --include-unverified)")
    exp_cfg = experiments_config()
    e5 = exp_cfg["experiments"]["e5"]
    judges = args.judges or e5["judges"]
    subset = subset_for(exp_cfg, shard=args.shard)
    text_of = answer_text
    if args.variant == TRANSLATE_VARIANT:
        translator = e5["translator"]
        run(args, TRANSLATE, plan_translations(subset, translator))
        texts = translations(load_calls(TRANSLATE_VARIANT, [translator]), translator)
        if len(texts) < len(subset) * len(NON_EN):
            print("translations incomplete; judging waits until every subset answer is translated")
            return
        text_of = translated_text_of(texts)
    run(args, "e5", plan(subset, judges, exp_cfg, args.variant, text_of))


if __name__ == "__main__":
    main()
