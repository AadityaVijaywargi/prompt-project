import json
import zipfile

from lb.config import experiments_config
from lb.data import load_quadruples
from lb.runners import e1_pointwise
from lb.runners.common import select_shard
from scripts.check_shard import check, zip_shard

JUDGE = "judge-x"


def record(spec, parse_ok=True, attempt=0, key="ab" + "0" * 62):
    return {"experiment": spec.experiment, "judge": JUDGE, "prompt_variant": "baseline", "item_id": spec.item_id,
            "forms": list(spec.forms), "order": spec.order, "parse_ok": parse_ok, "attempt": attempt,
            "cache_key": key, "error": None if parse_ok else "bad json"}


def write(path, recs):
    path.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")


def test_check_counts_ok_unparsed_and_missing(tmp_path):
    specs = e1_pointwise.plan(select_shard(load_quadruples(), "4/4"), [JUDGE], experiments_config())
    recs = [record(s) for s in specs[:-2]]
    recs.append(record(specs[-2], parse_ok=False, attempt=2))     # gave up after retries: done, not missing
    recs.append(record(specs[-1], parse_ok=False, attempt=0))     # one failed attempt only: still missing
    write(tmp_path / "e1__baseline-shard4of4-x.jsonl", recs)
    e1 = check(JUDGE, "4/4", raw_dir=tmp_path)[0]
    assert e1 == {"experiment": "e1", "planned": len(specs), "parsed_ok": len(specs) - 2,
                  "unparsed": 1, "missing": 1}


def test_check_ignores_pilot_runs(tmp_path):
    specs = e1_pointwise.plan(select_shard(load_quadruples(), "1/4"), [JUDGE], experiments_config())
    write(tmp_path / "e1__pilot-baseline-x.jsonl", [{**record(s), "run_id": "pilot-baseline-x"} for s in specs])
    e1 = check(JUDGE, "1/4", raw_dir=tmp_path)[0]
    assert e1["parsed_ok"] == 0 and e1["missing"] == len(specs)


def test_zip_packs_shard_raw_files_and_their_cache(tmp_path, monkeypatch):
    import scripts.check_shard as cs
    raw, cache = tmp_path / "results" / "raw", tmp_path / "results" / "cache"
    raw.mkdir(parents=True)
    key = "cd" + "1" * 62
    (cache / "cd").mkdir(parents=True)
    (cache / "cd" / f"{key}.json").write_text("{}", encoding="utf-8")
    specs = e1_pointwise.plan(select_shard(load_quadruples(), "2/4"), [JUDGE], experiments_config())
    write(raw / "e1__baseline-shard2of4-x.jsonl", [record(specs[0], key=key)])
    write(raw / "e1__baseline-shard3of4-x.jsonl", [record(specs[0])])
    monkeypatch.setattr(cs, "ROOT", tmp_path)
    out = tmp_path / "part2.zip"
    assert zip_shard(out, "2/4", raw_dir=raw, cache_dir=cache) == 2
    assert sorted(zipfile.ZipFile(out).namelist()) == [
        f"results/cache/cd/{key}.json", "results/raw/e1__baseline-shard2of4-x.jsonl"]
