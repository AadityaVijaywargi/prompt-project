"""Fetch candidate MMMLU questions (English from cais/mmlu, Hindi from openai/MMMLU HI_IN) and
MT-Bench prompts via the Hugging Face datasets-server API. Read-only; writes data/sources/*.jsonl.

English and Hindi rows are matched by (subject, index within subject) and the answer letters are checked.
Candidates are sampled with the seed in experiments.yaml; scripts/build_pilot.py documents which were kept.

    python scripts/fetch_sources.py --round pilot     # Phase 0 candidates + MT-Bench
    python scripts/fetch_sources.py --round phase1    # more candidates (never re-drawing pilot ones) + MT-Bench-Hi
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from lb.config import DATA, experiments_config, read_jsonl, write_jsonl  # noqa: E402

API = "https://datasets-server.huggingface.co"
LETTERS = "ABCD"
client = httpx.Client(timeout=60)


def get(path: str, **params) -> dict:
    status = None
    for attempt in range(10):
        try:
            r = client.get(f"{API}/{path}", params=params)
            status = r.status_code
            if status == 200:
                return r.json()
        except httpx.TransportError as e:
            status = type(e).__name__
        time.sleep(min(2 ** attempt, 30))
    raise RuntimeError(f"failed ({status}): {path} {params}")


def subject_offsets() -> tuple[dict[str, int], dict[str, int]]:
    """MMMLU HI_IN shares the global row order of cais/mmlu 'all': subjects concatenated alphabetically."""
    splits = get("size", dataset="cais/mmlu")["size"]["splits"]
    sizes = {s["config"]: s["num_rows"] for s in splits
             if s["split"] == "test" and s["config"] not in ("all", "auxiliary_train")}
    starts, total = {}, 0
    for subject in sorted(sizes):
        starts[subject] = total
        total += sizes[subject]
    return sizes, starts


def fetch_mmmlu(seed: int, subjects: dict, k: int, exclude: frozenset = frozenset()) -> list[dict]:
    rng = random.Random(seed)
    sizes, starts = subject_offsets()
    out = []
    for domain in ("stem", "humanities"):
        for subject in subjects[domain]:
            population = [i for i in range(sizes[subject]) if f"{subject}/{i}" not in exclude]
            for idx in sorted(rng.sample(population, k)):
                en = get("rows", dataset="cais/mmlu", config=subject, split="test", offset=idx, length=1)["rows"][0]["row"]
                hi = get("rows", dataset="openai/MMMLU", config="HI_IN", split="test",
                         offset=starts[subject] + idx, length=1)["rows"][0]["row"]
                ok = (hi["Subject"] == subject and hi["Unnamed: 0"] == idx
                      and LETTERS[en["answer"]] == hi["Answer"])
                out.append({"source_id": f"{subject}/{idx}", "subject": subject, "domain": domain,
                            "question_en": en["question"], "choices_en": en["choices"],
                            "answer_letter": LETTERS[en["answer"]],
                            "question_hi_source": hi["Question"],
                            "choices_hi_source": [hi[c] for c in LETTERS],
                            "aligned": ok})
                print(f"{subject}/{idx} aligned={ok}", flush=True)
    return out


def fetch_mt_bench() -> list[dict]:
    rows = get("rows", dataset="HuggingFaceH4/mt_bench_prompts", config="default", split="train",
               offset=0, length=100)["rows"]
    return [{"source_id": str(r["row"]["prompt_id"]), "category": r["row"]["category"],
             "prompt": r["row"]["prompt"][0]} for r in rows]


def fetch_mt_bench_hi() -> list[dict]:
    """nvidia/MT-Bench-Hi (Kamath et al., arXiv:2508.19831): 200 prompts, about 80% written natively in Hindi."""
    rows = []
    for offset in (0, 100):
        rows += get("rows", dataset="nvidia/MT-Bench-Hi", config="default", split="test",
                    offset=offset, length=100)["rows"]
    return [{"source_id": str(r["row"]["question_id"]), "category": r["row"]["category"],
             "translated": r["row"]["translated"], "prompt_hi": r["row"]["turns"][0]} for r in rows]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--round", choices=["pilot", "phase1"], required=True)
    args = p.parse_args()
    cfg = experiments_config()
    src = cfg["sources"]
    if args.round == "pilot":
        write_jsonl(DATA / "sources" / "mmmlu_candidates.jsonl",
                    fetch_mmmlu(cfg["seed"], src["mmmlu_subjects"], src["candidates_per_subject"]))
        write_jsonl(DATA / "sources" / "mt_bench_prompts.jsonl", fetch_mt_bench())
    else:
        ph = src["phase1"]
        seen = frozenset(r["source_id"] for r in read_jsonl(DATA / "sources" / "mmmlu_candidates.jsonl"))
        write_jsonl(DATA / "sources" / "mmmlu_candidates_phase1.jsonl",
                    fetch_mmmlu(cfg["seed"] + ph["seed_offset"], ph["mmmlu_subjects"],
                                ph["candidates_per_subject"], seen))
        write_jsonl(DATA / "sources" / "mt_bench_hi_prompts.jsonl", fetch_mt_bench_hi())


if __name__ == "__main__":
    main()
