"""Gap A: each verified wrong twin scored pointwise in all four forms, with the E1 rubric and prompt."""
from __future__ import annotations

from .common import plan_pointwise, resolve, run, runner_args

EXPERIMENT = "a_wrong"
FORMS = ["wrong:en", "wrong:hi", "wrong:hi_rom", "wrong:hinglish"]


def plan(items, judges, exp_cfg, variant="baseline"):
    items = [q for q in items if q.wrong_usable]
    return plan_pointwise(EXPERIMENT, items, judges, variant, exp_cfg, forms=FORMS)


def main() -> None:
    args = runner_args(__doc__).parse_args()
    items, judges, exp_cfg = resolve(args, EXPERIMENT)
    run(args, EXPERIMENT, plan(items, judges, exp_cfg, args.variant))


if __name__ == "__main__":
    main()
