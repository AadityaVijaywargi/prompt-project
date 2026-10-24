"""Checks that a judge's baseline E1-E3 run covers every planned call, optionally for one --shard.

    python scripts/check_shard.py --judge qwen2.5-7b-local --shard 2/4
    python scripts/check_shard.py --judge qwen2.5-7b-local --shard 2/4 --zip qwen_part2_results.zip

A planned call counts as done when a raw record parsed OK, or when it was still unparseable after the
last retry (that is a recorded failure, not a gap). Provider errors and calls never made are missing.
Exit code 0 only when nothing is missing. --zip packs this shard's raw files and the cache entries
they reference, for a teammate who cannot push.
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

from lb.config import CACHE, RAW, ROOT, experiments_config, read_jsonl
from lb.data import load_quadruples
from lb.judge import MAX_PARSE_RETRIES
from lb.runners import e1_pointwise, e2_pairwise, e3_wrong
from lb.runners.common import parse_shard, select_shard

PLANNERS = {"e1": e1_pointwise.plan, "e2": e2_pairwise.plan, "e3": e3_wrong.plan}


def call_key(experiment: str, item_id: str, forms, order) -> tuple:
    return experiment, item_id, tuple(forms), order


def check(judge: str, shard: str | None = None, variant: str = "baseline",
          raw_dir: Path = RAW) -> list[dict]:
    status = {}
    for f in sorted(raw_dir.glob("*.jsonl")):
        for r in read_jsonl(f):
            if r["judge"] != judge or r.get("prompt_variant") != variant:
                continue
            k = call_key(r["experiment"], r["item_id"], r["forms"], r.get("order"))
            if r["parse_ok"]:
                status[k] = "ok"
            elif r.get("attempt", 0) >= MAX_PARSE_RETRIES and status.get(k) != "ok":
                status[k] = "unparsed"
    cfg = experiments_config()
    items = select_shard(load_quadruples(), shard)
    rows = []
    for exp, plan in PLANNERS.items():
        found = [status.get(call_key(exp, s.item_id, s.forms, s.order))
                 for s in plan(items, [judge], cfg, variant)]
        rows.append({"experiment": exp, "planned": len(found), "parsed_ok": found.count("ok"),
                     "unparsed": found.count("unparsed"), "missing": found.count(None)})
    return rows


def zip_shard(out: Path, shard: str, raw_dir: Path = RAW, cache_dir: Path = CACHE) -> int:
    tag = "shard{}of{}".format(*parse_shard(shard))
    files = sorted(raw_dir.glob(f"*{tag}*.jsonl"))
    keys = {r["cache_key"] for f in files for r in read_jsonl(f) if r.get("cache_key")}
    cached = [p for k in sorted(keys) if (p := cache_dir / k[:2] / f"{k}.json").exists()]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files + cached:
            z.write(p, p.relative_to(ROOT).as_posix())
    return len(files) + len(cached)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--judge", required=True)
    p.add_argument("--shard", default=None, metavar="K/N")
    p.add_argument("--variant", default="baseline")
    p.add_argument("--zip", type=Path, default=None, help="also pack this shard's results into a zip file")
    args = p.parse_args()
    rows = check(args.judge, args.shard, args.variant)
    print(f"{args.judge}, {args.variant}, shard {args.shard or 'all'}")
    for r in rows:
        print(f"  {r['experiment']}: planned {r['planned']}, parsed OK {r['parsed_ok']}, "
              f"unparsed after retries {r['unparsed']}, missing {r['missing']}")
    missing = sum(r["missing"] for r in rows)
    print("COMPLETE" if missing == 0 else f"INCOMPLETE: {missing} calls missing; rerun the experiments listed above")
    if args.zip:
        if not args.shard:
            raise SystemExit("--zip needs --shard")
        print(f"wrote {args.zip} ({zip_shard(args.zip, args.shard)} files)")
    sys.exit(0 if missing == 0 else 1)


if __name__ == "__main__":
    main()
