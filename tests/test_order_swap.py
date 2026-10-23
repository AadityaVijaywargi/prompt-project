from lb.config import experiments_config
from lb.prompts import render_pairwise, render_pointwise
from lb.runners import e1_pointwise, e2_pairwise, e3_wrong
from lb.schema import Quadruple

from conftest import forms


WRONG = forms(en="The capital of Australia is Sydney.", hi="ऑस्ट्रेलिया की राजधानी सिडनी है।",
              hi_rom="Australia ki rajdhani Sydney hai.", hinglish="Australia ki capital Sydney hai.")


def quad(rec, wrong=False, wrong_passed=True):
    if wrong:
        qc = {"verified_by": ["a1"], "verified_on": "2026-10-30", "edits": 0, "passed": True, "notes": ""}
        if not wrong_passed:
            qc = {"verified_by": [], "verified_on": None, "edits": 0, "passed": False, "notes": ""}
        rec = dict(rec, wrong=WRONG, wrong_qc=qc)
    return Quadruple.model_validate(rec)


def test_both_orders_swap_answers(quad_record):
    cfg = experiments_config()
    q = quad(quad_record)
    specs = e2_pairwise.plan([q], ["j1"], cfg)
    assert len(specs) == 3 * 2
    for pair in cfg["experiments"]["e2"]["pairs"]:
        ab = next(s for s in specs if s.forms == tuple(pair) and s.order == "AB")
        ba = next(s for s in specs if s.forms == tuple(pair) and s.order == "BA")
        x, y = (q.answers.get(f).text for f in pair)
        assert ab.prompt.index(x) < ab.prompt.index(y)
        assert ba.prompt.index(y) < ba.prompt.index(x)
        assert "Answer A:\n" + x in ab.prompt and "Answer A:\n" + y in ba.prompt


def test_e1_counts_and_reference(quad_record):
    cfg = experiments_config()
    q = quad(quad_record)
    specs = e1_pointwise.plan([q], ["j1", "j2"], cfg)
    assert len(specs) == 4 * 2
    assert all("Reference answer: Canberra." in s.prompt for s in specs)   # factual -> reference-guided


def test_open_ended_has_no_reference(quad_record):
    q = quad(dict(quad_record, type="open_ended"))
    specs = e1_pointwise.plan([q], ["j1"], experiments_config())
    assert not any("Reference answer" in s.prompt for s in specs)


def test_e3_pairs_wrong_english(quad_record):
    cfg = experiments_config()
    items = [quad(quad_record), quad(dict(quad_record, item_id="x2"), wrong=True),
             quad(dict(quad_record, item_id="x3"), wrong=True, wrong_passed=False)]
    specs = e3_wrong.plan(items, ["j1"], cfg)
    assert {s.item_id for s in specs} == {"x2"}          # no twin, or unverified twin -> skipped
    assert len(specs) == (3 + 1) * 2                               # 3 forms + en control, both orders
    assert all(s.forms[0] == "wrong:en" for s in specs)
    assert all("Sydney" in s.prompt for s in specs)


def test_prompt_placeholders_all_filled():
    p = render_pointwise("pointwise_en", "Q", "A", "R", "bias_aware_suffix")
    assert "{question}" not in p and "{answer}" not in p and "{reference_block}" not in p
    assert p.rstrip().endswith("when the meaning is clear and correct.")
    h = render_pairwise("pairwise_hi", "Q", "A1", "B1", "R")
    assert "संदर्भ उत्तर: R" in h and '{"winner"' in h
