import json

import pytest

from conftest import FakeProvider
from lb.cache import Cache, cache_key
from lb.judge import CallMeta, Judge

CFG = {"provider": "openai_compat", "model": "fake-model", "base_url": "http://x", "api_key_env": None}
GOOD = '{"correctness": 5, "completeness": 5, "clarity": 5, "language_quality": 4, "comment": "ok"}'
META = CallMeta("run1", "e1", "baseline", "item-1", ["hi"])


def make(tmp_path, responses, offline=False):
    fake = FakeProvider(responses)
    j = Judge("fake", CFG, cache=Cache(tmp_path / "cache"), provider=None if offline else fake,
              offline=offline, raw_dir=tmp_path / "raw")
    return j, fake


def read_log(tmp_path):
    return [json.loads(l) for f in (tmp_path / "raw").glob("*.jsonl") for l in f.read_text("utf-8").splitlines()]


def test_cache_key_depends_on_model_prompt_inputs():
    base = cache_key("m", "p", {"attempt": 0})
    assert base == cache_key("m", "p", {"attempt": 0})
    assert len({base, cache_key("m2", "p", {"attempt": 0}), cache_key("m", "p2", {"attempt": 0}),
                cache_key("m", "p", {"attempt": 1})}) == 4


def test_cache_hit_never_calls_provider(tmp_path):
    j, fake = make(tmp_path, [GOOD])
    first = j.score("Q?", "उत्तर", META)
    assert fake.calls == 1
    j2, fake2 = make(tmp_path, [])            # same cache dir, provider has nothing to return
    second = j2.score("Q?", "उत्तर", META)
    assert fake2.calls == 0
    assert first == second
    log = read_log(tmp_path)
    assert [r["cache_hit"] for r in log] == [False, True]


def test_offline_mode_uses_cache_and_fails_on_miss(tmp_path):
    j, _ = make(tmp_path, [GOOD])
    j.score("Q?", "A", META)
    off, _ = make(tmp_path, [], offline=True)
    assert off.score("Q?", "A", META) is not None
    with pytest.raises(RuntimeError, match="offline"):
        off.score("Q?", "a different answer", META)


def test_parse_retries_then_gives_up(tmp_path):
    j, fake = make(tmp_path, ["garbage", "still garbage", "nope"])
    assert j.score("Q?", "A", META) is None
    assert fake.calls == 3                    # first try + 2 retries
    log = read_log(tmp_path)
    assert [r["attempt"] for r in log] == [0, 1, 2]
    assert not any(r["parse_ok"] for r in log)
    assert all(r["error"] for r in log)


def test_parse_retry_succeeds(tmp_path):
    j, fake = make(tmp_path, ["garbage", GOOD])
    assert j.score("Q?", "A", META).language_quality == 4
    assert fake.calls == 2
    assert [r["parse_ok"] for r in read_log(tmp_path)] == [False, True]


def test_log_preserves_devanagari(tmp_path):
    j, _ = make(tmp_path, [GOOD])
    j.score("प्रश्न?", "उत्तर", META)
    raw = next((tmp_path / "raw").glob("*.jsonl")).read_text("utf-8")
    assert "\\u" not in raw
    assert json.loads(raw)["item_id"] == "item-1"
