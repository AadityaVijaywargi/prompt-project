"""Statistical helpers (brief section 7). Table builders that read results/raw come in Phase 2-3,
implementing exactly the comparisons fixed in analysis/plan.md."""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np
from scipy import stats as st

N_BOOT = 10_000


def wilson_ci(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def binom_test_half(successes: int, n: int) -> float:
    return float(st.binomtest(successes, n, 0.5).pvalue) if n else float("nan")


def paired_bootstrap_ci(diffs: Sequence[float], n_boot: int = N_BOOT, seed: int = 0,
                        alpha: float = 0.05) -> tuple[float, float, float]:
    """Mean of per-item paired differences with a percentile bootstrap CI (resampling items)."""
    d = np.asarray(diffs, dtype=float)
    if d.size == 0:
        return (float("nan"),) * 3
    rng = np.random.default_rng(seed)
    means = d[rng.integers(0, d.size, size=(n_boot, d.size))].mean(axis=1)
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return float(d.mean()), float(lo), float(hi)


def wilcoxon_p(diffs: Sequence[float]) -> float:
    d = np.asarray(diffs, dtype=float)
    if d.size == 0 or np.all(d == 0):
        return 1.0
    return float(st.wilcoxon(d, zero_method="wilcox").pvalue)


def holm(pvalues: Sequence[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values, returned in the input order."""
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    adjusted, running = [0.0] * m, 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[i]))
        adjusted[i] = running
    return adjusted


def quadratic_weighted_kappa(a: Sequence[int], b: Sequence[int], labels: Sequence[int] = (1, 2, 3, 4, 5)) -> float:
    idx = {l: i for i, l in enumerate(labels)}
    k = len(labels)
    obs = np.zeros((k, k))
    for x, y in zip(a, b):
        obs[idx[x], idx[y]] += 1
    n = obs.sum()
    if n == 0:
        return float("nan")
    w = np.array([[(i - j) ** 2 / (k - 1) ** 2 for j in range(k)] for i in range(k)])
    expected = np.outer(obs.sum(axis=1), obs.sum(axis=0)) / n
    denom = (w * expected).sum()
    return float(1 - (w * obs).sum() / denom) if denom else float("nan")


def spearman(a: Sequence[float], b: Sequence[float]) -> float:
    return float(st.spearmanr(a, b).statistic)


def bootstrap_rate_diff_ci(base: Sequence[tuple[int, int]], new: Sequence[tuple[int, int]], n_boot: int = N_BOOT,
                           seed: int = 0, alpha: float = 0.05) -> tuple[float, float, float, float, float]:
    """Paired change in a pooled rate (sum of hits / sum of trials) between two runs on the same items.
    Each item gives (hits, trials) in both runs; items are resampled together. Returns (base rate, new rate,
    new minus base, CI low, CI high); NaN where a rate has no trials."""
    b, v = np.asarray(base, dtype=float).reshape(-1, 2), np.asarray(new, dtype=float).reshape(-1, 2)
    rate = lambda x: float(x[:, 0].sum() / x[:, 1].sum()) if x[:, 1].sum() else float("nan")
    rb, rv = rate(b), rate(v)
    if math.isnan(rb) or math.isnan(rv):
        return rb, rv, float("nan"), float("nan"), float("nan")
    idx = np.random.default_rng(seed).integers(0, b.shape[0], size=(n_boot, b.shape[0]))
    with np.errstate(divide="ignore", invalid="ignore"):
        diffs = v[idx, 0].sum(1) / v[idx, 1].sum(1) - b[idx, 0].sum(1) / b[idx, 1].sum(1)
    diffs = diffs[~np.isnan(diffs)]
    lo, hi = np.quantile(diffs, [alpha / 2, 1 - alpha / 2]) if diffs.size else (float("nan"),) * 2
    return float(rb), float(rv), float(rv - rb), float(lo), float(hi)


def kendall_tau_b(x: Sequence[float], y: Sequence[float]) -> tuple[float, float]:
    """Kendall's tau-b (tie-corrected) and its p-value; NaN when either side has no variance."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if x.size < 3 or np.var(x) == 0 or np.var(y) == 0:
        return float("nan"), float("nan")
    res = st.kendalltau(x, y)
    return float(res.statistic), float(res.pvalue)


def cohen_kappa_binary_ci(a: Sequence[bool], b: Sequence[bool], n_boot: int = N_BOOT, seed: int = 0,
                          alpha: float = 0.05) -> tuple[float, float, float]:
    """Cohen's kappa for two raters' yes/no labels with a percentile bootstrap CI (resampling rows).
    NaN when expected agreement is 1 (both raters give one label throughout)."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a.size == 0:
        return (float("nan"),) * 3

    def kappa(x: np.ndarray, y: np.ndarray) -> np.ndarray:
        po = (x == y).mean(axis=-1)
        px, py = x.mean(axis=-1), y.mean(axis=-1)
        pe = px * py + (1 - px) * (1 - py)
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(pe < 1, (po - pe) / (1 - pe), np.nan)

    idx = np.random.default_rng(seed).integers(0, a.size, size=(n_boot, a.size))
    boots = kappa(a[idx], b[idx])
    boots = boots[~np.isnan(boots)]
    lo, hi = np.quantile(boots, [alpha / 2, 1 - alpha / 2]) if boots.size else (float("nan"),) * 2
    return float(kappa(a, b)), float(lo), float(hi)


def bootstrap_slope_ci(x: Sequence[float], y: Sequence[float], n_boot: int = N_BOOT, seed: int = 0,
                       alpha: float = 0.05) -> tuple[float, float, float]:
    """OLS slope of y on x with a percentile bootstrap CI (resampling items). NaN when x has no variance;
    resamples whose x has no variance are skipped."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if x.size < 3 or np.var(x) == 0:
        return (float("nan"),) * 3
    idx = np.random.default_rng(seed).integers(0, x.size, size=(n_boot, x.size))
    bx, by = x[idx], y[idx]
    bx_c = bx - bx.mean(axis=1, keepdims=True)
    var = (bx_c ** 2).sum(axis=1)
    ok = var > 0
    slopes = (bx_c[ok] * (by[ok] - by[ok].mean(axis=1, keepdims=True))).sum(axis=1) / var[ok]
    lo, hi = np.quantile(slopes, [alpha / 2, 1 - alpha / 2])
    xc = x - x.mean()
    return float((xc * (y - y.mean())).sum() / (xc ** 2).sum()), float(lo), float(hi)


def log_length_ratio_slope(diffs: Sequence[float], log_ratios: Sequence[float]) -> dict:
    """OLS of score difference on log(words_form / words_en): the verbosity control for E1."""
    res = st.linregress(np.asarray(log_ratios, float), np.asarray(diffs, float))
    return {"intercept": float(res.intercept), "slope": float(res.slope),
            "slope_p": float(res.pvalue), "r2": float(res.rvalue ** 2)}
