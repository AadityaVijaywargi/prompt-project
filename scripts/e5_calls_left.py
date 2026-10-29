"""Prints how many E5 calls of one judge, variant and shard are not in the cache yet, and writes nothing.

    python scripts/e5_calls_left.py --shard 2/3                 # gpt-oss-120b, bias_aware
    python scripts/e5_calls_left.py --variant translate_then_judge --shard 2/4 --by-experiment

For translate_then_judge the count includes the translations (e5_translate). Judging waits for every
translation of the part, so until then all its judge calls count as left.

A dry run of lb.runners.e5_mitigation shows the same count, but once nothing is left it replays every call
from the cache and logs a new run file; this check does not. Exit code 0 only when nothing is left.
"""
import argparse
import sys

from lb.analysis import load_calls
from lb.budget import summarize
from lb.config import experiments_config
from lb.runners.common import build_judges
from lb.runners.e5_mitigation import (TRANSLATE_VARIANT, missing_translations, plan, plan_translations,
                                      subset_for, translated_text_of, translations)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--judge", default="gpt-oss-120b")
    p.add_argument("--variant", default="bias_aware")
    p.add_argument("--shard", default=None)
    p.add_argument("--by-experiment", action="store_true")
    args = p.parse_args()
    cfg = experiments_config()
    subset = subset_for(cfg, shard=args.shard)
    left = {}
    if args.variant == TRANSLATE_VARIANT:
        translator = cfg["experiments"]["e5"]["translator"]
        total, cached = summarize(plan_translations(subset, translator), build_judges([translator], offline=True))
        left.update({k[0]: total[k] - cached[k] for k in total})
        texts = translations(load_calls(TRANSLATE_VARIANT, [translator]), translator)
        if missing_translations(subset, texts):   # judging has not started: every judge call is left
            for s in plan(subset, [args.judge], cfg, args.variant, lambda q, selector: ""):   # count only
                left[s.experiment] = left.get(s.experiment, 0) + 1
            report(left, args.by_experiment)
        specs = plan(subset, [args.judge], cfg, args.variant, translated_text_of(texts))
    else:
        specs = plan(subset, [args.judge], cfg, args.variant)
    total, cached = summarize(specs, build_judges([args.judge], offline=True))
    left.update({k[0]: total[k] - cached[k] for k in total})
    report(left, args.by_experiment)


def report(left: dict, by_experiment: bool) -> None:
    if by_experiment:
        for e in sorted(left):
            print(f"{e} {left[e]}")
    n = sum(left.values())
    print(n)
    sys.exit(0 if n == 0 else 1)


if __name__ == "__main__":
    main()
