"""Prints how many E5 calls of one judge, variant and shard are not in the cache yet, and writes nothing.

    python scripts/e5_calls_left.py --shard 2/3                 # gpt-oss-120b, bias_aware
    python scripts/e5_calls_left.py --shard 2/3 --by-experiment

A dry run of lb.runners.e5_mitigation shows the same count, but once nothing is left it replays every call
from the cache and logs a new run file; this check does not. Exit code 0 only when nothing is left.
"""
import argparse
import sys

from lb.budget import summarize
from lb.config import experiments_config
from lb.runners.common import build_judges
from lb.runners.e5_mitigation import plan, subset_for


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--judge", default="gpt-oss-120b")
    p.add_argument("--variant", default="bias_aware")
    p.add_argument("--shard", default=None)
    p.add_argument("--by-experiment", action="store_true")
    args = p.parse_args()
    cfg = experiments_config()
    specs = plan(subset_for(cfg, shard=args.shard), [args.judge], cfg, args.variant)
    total, cached = summarize(specs, build_judges([args.judge], offline=True))
    left = sum(total.values()) - sum(cached.values())
    if args.by_experiment:
        for key in sorted(total):
            print(f"{key[0]} {total[key] - cached[key]}")
    print(left)
    sys.exit(0 if left == 0 else 1)


if __name__ == "__main__":
    main()
