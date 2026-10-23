import pytest

from lb.parse import extract_json, parse_pairwise, parse_pointwise

GOOD = '{"correctness": 5, "completeness": 4, "clarity": 5, "language_quality": 3, "comment": "ok"}'


def test_plain_json():
    s = parse_pointwise(GOOD)
    assert (s.correctness, s.language_quality) == (5, 3)
    assert s.content == pytest.approx(14 / 3)
    assert s.overall == pytest.approx(17 / 4)


def test_code_fence_and_prose():
    s = parse_pointwise("Here you go:\n```json\n" + GOOD + "\n```\nThanks!")
    assert s.completeness == 4


def test_string_digits_coerced():
    s = parse_pointwise(GOOD.replace('"correctness": 5', '"correctness": "5"'))
    assert s.correctness == 5


def test_braces_inside_comment():
    s = parse_pointwise('{"correctness": 2, "completeness": 2, "clarity": 2, '
                        '"language_quality": 2, "comment": "uses {weird} braces"}')
    assert s.comment == "uses {weird} braces"


@pytest.mark.parametrize("bad", [
    "", None, "no json here", '{"correctness": 6, "completeness": 4, "clarity": 5, "language_quality": 3}',
    '{"correctness": 5, "completeness": 4}', '{"correctness": 5, "completeness": 4, "clarity": 5,',
    '[1, 2, 3]',
])
def test_malformed_pointwise(bad):
    with pytest.raises(ValueError):
        parse_pointwise(bad)


@pytest.mark.parametrize("text,winner", [
    ('{"winner": "A", "reason": "x"}', "A"),
    ('{"winner": "b", "reason": "x"}', "B"),
    ('{"winner": "Tie", "reason": "x"}', "tie"),
    ('{"winner": "Answer A", "reason": "x"}', "A"),
    ('```\n{"winner": "B"}\n```', "B"),
])
def test_pairwise(text, winner):
    assert parse_pairwise(text).winner == winner


@pytest.mark.parametrize("bad", ['{"winner": "C"}', '{"reason": "no winner"}', "A is better"])
def test_malformed_pairwise(bad):
    with pytest.raises(ValueError):
        parse_pairwise(bad)


def test_extract_skips_invalid_first_object():
    assert extract_json('{not json} then {"winner": "A"}') == {"winner": "A"}
