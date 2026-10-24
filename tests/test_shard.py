import pytest

from lb.data import load_quadruples
from lb.runners.common import parse_shard, select_shard


def test_shards_partition_items():
    items = list(range(150))
    parts = [select_shard(items, f"{k}/4") for k in range(1, 5)]
    assert sorted(x for p in parts for x in p) == items
    assert [len(p) for p in parts] == [38, 38, 37, 37]
    assert parts[0][:3] == [0, 4, 8]


def test_no_shard_returns_everything():
    assert select_shard([1, 2, 3], None) == [1, 2, 3]


@pytest.mark.parametrize("spec", ["0/4", "5/4", "1-4", "a/b"])
def test_bad_shard_spec_refused(spec):
    with pytest.raises(SystemExit):
        parse_shard(spec)


def test_real_data_shards_are_disjoint_and_complete():
    items = load_quadruples()
    ids = [set(q.item_id for q in select_shard(items, f"{k}/4")) for k in range(1, 5)]
    assert set().union(*ids) == {q.item_id for q in items}
    assert sum(len(s) for s in ids) == len(items)
