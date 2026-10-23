"""E3: correct hi / hi_rom / hinglish vs wrong English, both orders; control: correct en vs wrong en."""
from __future__ import annotations

from .common import plan_pairwise, resolve, run, runner_args

EXPERIMENT = "e3"


def plan(items, judges, exp_cfg, variant="baseline"):
    e3 = exp_cfg["experiments"][EXPERIMENT]
    items = [q for q in items if q.wrong_usable]
    pairs = [("wrong:en", f) for f in e3["correct_forms"]]
    if e3.get("control"):
        pairs.append(("wrong:en", "en"))
    return plan_pairwise(EXPERIMENT, items, judges, variant, exp_cfg, pairs)


def main() -> None:
    args = runner_args(__doc__).parse_args()
    items, judges, exp_cfg = resolve(args, EXPERIMENT)
    run(args, EXPERIMENT, plan(items, judges, exp_cfg, args.variant))


if __name__ == "__main__":
    main()
