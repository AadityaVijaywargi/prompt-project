"""E1: pointwise rubric scoring of every item in all four forms."""
from __future__ import annotations

from .common import plan_pointwise, resolve, run, runner_args

EXPERIMENT = "e1"


def plan(items, judges, exp_cfg, variant="baseline"):
    return plan_pointwise(EXPERIMENT, items, judges, variant, exp_cfg)


def main() -> None:
    args = runner_args(__doc__).parse_args()
    items, judges, exp_cfg = resolve(args, EXPERIMENT)
    run(args, EXPERIMENT, plan(items, judges, exp_cfg, args.variant))


if __name__ == "__main__":
    main()
