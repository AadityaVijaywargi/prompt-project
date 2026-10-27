import pytest

from lb import budget, stats
from lb.config import experiments_config


def test_wilson_known_values():
    # Reference values: Wilson score interval, 95%.
    lo, hi = stats.wilson_ci(81, 263)
    assert lo == pytest.approx(0.2553, abs=1e-4) and hi == pytest.approx(0.3662, abs=1e-4)
    assert stats.wilson_ci(0, 10)[0] == 0.0
    lo, hi = stats.wilson_ci(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-4) and hi == pytest.approx(0.7634, abs=1e-4)


def test_bootstrap_constant_and_symmetric():
    assert stats.paired_bootstrap_ci([0.5] * 30) == (0.5, 0.5, 0.5)
    mean, lo, hi = stats.paired_bootstrap_ci([-1, 1] * 50, seed=1)
    assert mean == 0 and lo < 0 < hi
    assert lo == pytest.approx(-0.2, abs=0.05) and hi == pytest.approx(0.2, abs=0.05)


def test_bootstrap_reproducible():
    d = [0.1, -0.3, 0.7, 0.0, 0.2]
    assert stats.paired_bootstrap_ci(d, seed=7) == stats.paired_bootstrap_ci(d, seed=7)


def test_holm():
    assert stats.holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])


def test_kappa():
    assert stats.quadratic_weighted_kappa([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]) == pytest.approx(1.0)
    assert stats.quadratic_weighted_kappa([1, 5, 1, 5], [5, 1, 5, 1]) < 0


def test_wilcoxon_all_zero():
    assert stats.wilcoxon_p([0, 0, 0]) == 1.0


def test_planned_budget_matches_brief_with_four_judges():
    cfg = experiments_config()
    four = ["a", "b", "c", "d"]
    for e in ("e1", "e2", "e3"):
        cfg["experiments"][e]["judges"] = four
    rows = {name: calls for name, _, calls in budget.planned_counts(cfg, 150, 60)}
    assert rows["E1"] == 2400 and rows["E2"] == 3600 and rows["E3"] == 1440 and rows["E3 control"] == 480
    # E5: E1 480 + E2 720 + E3 on the subset's 40 wrong-twin items with the control, 4 x 2 x 40 x 2 = 640
    assert rows["E5 bias_aware"] == 1840 and rows["E5 translations"] == 180
