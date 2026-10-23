"""E2 (and optional E2b): pairwise comparison of matched answers, both orders."""
from __future__ import annotations

from .common import plan_pairwise, resolve, run, runner_args


def plan(items, judges, exp_cfg, variant="baseline", experiment="e2"):
    pairs = [tuple(p) for p in exp_cfg["experiments"][experiment]["pairs"]]
    return plan_pairwise(experiment, items, judges, variant, exp_cfg, pairs)


def main() -> None:
    p = runner_args(__doc__)
    p.add_argument("--e2b", action="store_true", help="run the script / mixing contrasts instead")
    args = p.parse_args()
    experiment = "e2b" if args.e2b else "e2"
    items, judges, exp_cfg = resolve(args, experiment)
    run(args, experiment, plan(items, judges, exp_cfg, args.variant, experiment))


if __name__ == "__main__":
    main()
