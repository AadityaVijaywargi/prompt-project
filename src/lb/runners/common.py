"""Shared planning and execution for all runners.

Each runner turns (items, judges, config) into a list of CallSpec. budget.py counts the same list, so the
printed budget is exactly what a run would send (excluding parse retries, which add at most 2 per failure).
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from .. import prompts
from ..cache import Cache
from ..config import experiments_config, judges_config
from ..data import load_quadruples, reference_for
from ..judge import CallMeta, Judge
from ..parse import parse_pairwise, parse_pointwise, parse_text
from ..schema import Quadruple


@dataclass(frozen=True)
class CallSpec:
    experiment: str
    judge: str
    variant: str
    item_id: str
    kind: str                  # pointwise | pairwise | text (the E5(b) translator)
    forms: tuple[str, ...]     # answer selectors, e.g. ("en",) or ("wrong:en", "hi")
    order: Optional[str]       # AB | BA for pairwise
    prompt: str


def answer_text(q: Quadruple, selector: str) -> str:
    if selector.startswith("wrong:"):
        if q.wrong is None:
            raise ValueError(f"{q.item_id} has no wrong twin")
        return q.wrong.get(selector.split(":", 1)[1]).text
    return q.answers.get(selector).text


def question_text(q: Quadruple, exp_cfg: dict) -> str:
    if exp_cfg.get("question_language", "en") != "en":
        raise NotImplementedError("question_language=answer needs per-form question texts in the data")
    return q.question_en


def variant_prompts(variant: str, exp_cfg: dict) -> dict:
    return exp_cfg["prompt_variants"][variant]


TextOf = Callable[[Quadruple, str], str]


def check_text_of(vp: dict, text_of: TextOf) -> None:
    if "translate" in vp and text_of is answer_text:
        raise NotImplementedError("translate_then_judge needs the E5 runner's translated texts (text_of)")


def plan_pointwise(experiment: str, items: list[Quadruple], judges: list[str], variant: str,
                   exp_cfg: dict, forms: Optional[list[str]] = None, text_of: TextOf = answer_text) -> list[CallSpec]:
    vp = variant_prompts(variant, exp_cfg)
    check_text_of(vp, text_of)
    specs = []
    for q in items:
        ref = reference_for(q, exp_cfg["reference_guided"])
        for form in forms or exp_cfg["forms"]:
            prompt = prompts.render_pointwise(vp["pointwise"], question_text(q, exp_cfg),
                                              text_of(q, form), ref, vp.get("suffix"))
            for j in judges:
                specs.append(CallSpec(experiment, j, variant, q.item_id, "pointwise", (form,), None, prompt))
    return specs


def plan_pairwise(experiment: str, items: list[Quadruple], judges: list[str], variant: str,
                  exp_cfg: dict, pairs: list[tuple[str, str]], text_of: TextOf = answer_text) -> list[CallSpec]:
    """Each pair (x, y) runs in both orders: AB shows x as A, BA shows y as A. forms keeps (x, y)."""
    vp = variant_prompts(variant, exp_cfg)
    check_text_of(vp, text_of)
    specs = []
    for q in items:
        ref = reference_for(q, exp_cfg["reference_guided"])
        for x, y in pairs:
            for order, (a, b) in (("AB", (x, y)), ("BA", (y, x))):
                prompt = prompts.render_pairwise(vp["pairwise"], question_text(q, exp_cfg),
                                                 text_of(q, a), text_of(q, b), ref, vp.get("suffix"))
                for j in judges:
                    specs.append(CallSpec(experiment, j, variant, q.item_id, "pairwise", (x, y), order, prompt))
    return specs


def build_judges(names: list[str], offline: bool = False, cache: Optional[Cache] = None) -> dict[str, Judge]:
    cfg = judges_config()
    drafter = cfg.get("drafting_model")
    judges = {}
    for n in names:
        jc = cfg["judges"][n]
        if jc["model"] == drafter:
            raise SystemExit(f"self-preference guard: judge {n} uses the drafting model {drafter}")
        judges[n] = Judge(n, jc, cache=cache, offline=offline,
                          temperature=experiments_config().get("temperature", 0))
    return judges


def execute(specs: list[CallSpec], judges: dict[str, Judge], run_id: str) -> dict:
    stats = {"ok": 0, "failed": 0}
    for i, s in enumerate(specs, 1):
        meta = CallMeta(run_id, s.experiment, s.variant, s.item_id, list(s.forms), s.order)
        parser = {"pointwise": parse_pointwise, "pairwise": parse_pairwise, "text": parse_text}[s.kind]
        result = judges[s.judge].run_prompt(s.prompt, parser, meta)
        stats["ok" if result is not None else "failed"] += 1
        if i % 25 == 0 or i == len(specs):
            print(f"  {i}/{len(specs)} done ({stats['failed']} unparsed)", flush=True)
    return stats


# ----- CLI plumbing shared by runners -----

def runner_args(description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--pilot", action="store_true", help="pilot items and pilot judges only")
    p.add_argument("--judges", nargs="+", help="override the judge list")
    p.add_argument("--variant", default="baseline")
    p.add_argument("--include-unverified", action="store_true",
                   help="count unverified items too (budget dry run only; refused with --yes)")
    p.add_argument("--offline", action="store_true", help="cache only; a miss is an error")
    p.add_argument("--yes", action="store_true", help="confirm the printed budget and run")
    p.add_argument("--run-id", default=None)
    p.add_argument("--shard", default=None, metavar="K/N",
                   help="run only part K of N (items K, K+N, K+2N, ... in data order), e.g. 1/4")
    return p


def parse_shard(spec: str) -> tuple[int, int]:
    try:
        k, n = (int(x) for x in spec.split("/"))
    except ValueError:
        raise SystemExit(f"--shard must look like K/N, got {spec!r}")
    if not 1 <= k <= n:
        raise SystemExit(f"--shard {spec}: K must be between 1 and N")
    return k, n


def select_shard(items: list[Quadruple], spec: Optional[str]) -> list[Quadruple]:
    """Round-robin split, so every part gets a similar mix of factual / open-ended items and wrong twins."""
    if not spec:
        return items
    k, n = parse_shard(spec)
    return [q for i, q in enumerate(items) if i % n == k - 1]


def resolve(args, experiment: str) -> tuple[list[Quadruple], list[str], dict]:
    exp_cfg = experiments_config()
    if args.include_unverified and args.yes:
        raise SystemExit("refusing to run judges on unverified items (only qc.passed items enter analysis)")
    items = load_quadruples(include_unverified=args.include_unverified, pilot_only=args.pilot)
    if args.pilot:
        items = items[: exp_cfg["pilot"]["n_items"]]
    items = select_shard(items, args.shard)
    judges =args.judges or (exp_cfg["pilot"]["judges"] if args.pilot else exp_cfg["experiments"][experiment]["judges"])
    return items, judges, exp_cfg


def default_run_id(args) -> str:
    shard = "shard{}of{}-".format(*parse_shard(args.shard)) if args.shard else ""
    return args.run_id or (("pilot-" if args.pilot else "") + args.variant + "-" + shard
                           + datetime.now().strftime("%Y%m%dT%H%M%S"))


def run(args, experiment: str, specs: list[CallSpec]) -> None:
    from ..budget import confirm
    if not specs:
        print(f"{experiment}: no eligible items (need qc.passed=true{', pilot' if args.pilot else ''}). Nothing to run.")
        return
    judges = build_judges(sorted({s.judge for s in specs}), offline=args.offline)
    if not confirm(specs, judges, args.yes or args.offline):
        return
    run_id = default_run_id(args)
    print(f"run_id={run_id}")
    print(execute(specs, judges, run_id))
