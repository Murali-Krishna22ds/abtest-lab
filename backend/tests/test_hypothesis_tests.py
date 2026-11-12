import numpy as np
import pytest
from scipy import stats
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.proportion import proportions_ztest

from app.stats import corrections as cx
from app.stats import tests as ht


def test_chi_square_equals_pooled_z_test():
    r = ht.two_proportion_test(1023, 5026, 1215, 5017)
    z, p = proportions_ztest([1215, 1023], [5017, 5026])
    assert r.p_value == pytest.approx(p, rel=1e-9)
    assert r.statistic == pytest.approx(z**2, rel=1e-9)
    assert r.diff == pytest.approx(1215 / 5017 - 1023 / 5026)
    assert r.ci_low < r.diff < r.ci_high


def test_newcombe_ci_matches_reference():
    # Newcombe (1998) example: 56/70 vs 48/80 -> 95% CI for difference (0.0524, 0.3339)
    r = ht.two_proportion_test(48, 80, 56, 70)
    assert r.ci_low == pytest.approx(0.0524, abs=1e-3)
    assert r.ci_high == pytest.approx(0.3339, abs=1e-3)


def test_degenerate_counts_do_not_crash():
    r = ht.two_proportion_test(0, 100, 0, 100)
    assert r.p_value == 1.0 and r.rel_lift is None
    with pytest.raises(ValueError):
        ht.two_proportion_test(5, 3, 1, 10)


def test_welch_matches_scipy():
    rng = np.random.default_rng(1)
    a, b = rng.normal(10, 2, 300), rng.normal(10.5, 3, 250)
    r = ht.welch_t_test(a, b)
    ref = stats.ttest_ind(b, a, equal_var=False)
    assert r.statistic == pytest.approx(ref.statistic)
    assert r.p_value == pytest.approx(ref.pvalue)
    ci = ref.confidence_interval(0.95)
    assert r.ci_low == pytest.approx(ci.low) and r.ci_high == pytest.approx(ci.high)


def test_welch_zero_variance():
    r = ht.welch_t_test([1, 1, 1], [1, 1, 1])
    assert r.p_value == 1.0


def test_srm_detects_imbalance():
    assert ht.srm_check([5000, 5000])["p_value"] > 0.99
    assert ht.srm_check([5300, 4700])["p_value"] < 0.001


def test_ci_coverage_of_newcombe():
    rng = np.random.default_rng(3)
    p1, p2, n, hits, sims = 0.2, 0.25, 800, 0, 2000
    xa, xb = rng.binomial(n, p1, sims), rng.binomial(n, p2, sims)
    for a, b in zip(xa, xb):
        r = ht.two_proportion_test(int(a), n, int(b), n)
        hits += r.ci_low <= p2 - p1 <= r.ci_high
    assert 0.93 <= hits / sims <= 0.975


@pytest.mark.parametrize("method,sm", [("bonferroni", "bonferroni"), ("holm", "holm"), ("bh", "fdr_bh")])
def test_corrections_match_statsmodels(method, sm):
    rng = np.random.default_rng(5)
    p = np.concatenate([rng.uniform(0, 0.01, 5), rng.uniform(0, 1, 25)])
    ours = cx.adjust_pvalues(p, method)
    ref = multipletests(p, method=sm)[1]
    assert np.allclose(ours, ref)


def test_corrections_vectorised_and_ordered():
    p = np.array([[0.01, 0.04, 0.03, 0.2], [0.5, 0.01, 0.02, 0.9]])
    for m in ("bonferroni", "holm", "bh"):
        adj = cx.adjust_pvalues(p, m)
        assert adj.shape == p.shape
        assert (adj >= p - 1e-12).all() and (adj <= 1).all()
        assert np.allclose(adj[1], cx.adjust_pvalues(p[1], m))
    # power ordering: bonferroni >= holm >= bh pointwise
    assert (cx.adjust_pvalues(p, "bonferroni") >= cx.adjust_pvalues(p, "holm") - 1e-12).all()
    assert (cx.adjust_pvalues(p, "holm") >= cx.adjust_pvalues(p, "bh") - 1e-12).all()


def test_corrections_reject_bad_input():
    with pytest.raises(ValueError):
        cx.adjust_pvalues([0.1, 1.2])
    with pytest.raises(ValueError):
        cx.adjust_pvalues([0.1], "nope")
