import numpy as np
import pytest
from scipy import stats
from statsmodels.stats.power import NormalIndPower, TTestIndPower
from statsmodels.stats.proportion import proportion_effectsize

from app.stats import power as pw


def test_known_sample_size_10_to_12_percent():
    n1, n2 = pw.sample_size_proportions(0.10, 0.12, alpha=0.05, power=0.8)
    assert n1 == n2
    assert 3800 <= n1 <= 3900  # textbook value is ~3,840 per arm


def test_sample_size_close_to_statsmodels_arcsine():
    n1, _ = pw.sample_size_proportions(0.2, 0.25)
    ref = NormalIndPower().solve_power(proportion_effectsize(0.25, 0.2), alpha=0.05, power=0.8)
    assert abs(n1 - ref) / ref < 0.02


def test_power_is_monotone_and_hits_target():
    n1, n2 = pw.sample_size_proportions(0.1, 0.13, power=0.9)
    assert pw.power_proportions(0.1, 0.13, n1, n2) >= 0.9
    assert pw.power_proportions(0.1, 0.13, n1 - 5, n2 - 5) < pw.power_proportions(0.1, 0.13, n1, n2)


def test_unequal_allocation():
    n1, n2 = pw.sample_size_proportions(0.1, 0.13, ratio=2.0)
    assert n2 == 2 * n1
    assert pw.power_proportions(0.1, 0.13, n1, n2) >= 0.8


def test_one_sided_needs_fewer_samples():
    assert pw.sample_size_proportions(0.1, 0.13, two_sided=False)[0] < pw.sample_size_proportions(0.1, 0.13)[0]


def test_mde_round_trip():
    n = 5000
    d = pw.mde_proportions(0.2, n, n)
    assert pw.power_proportions(0.2, 0.2 + d, n, n) == pytest.approx(0.8, abs=1e-6)


def test_mde_unachievable_raises():
    with pytest.raises(ValueError):
        pw.mde_proportions(0.5, 5, 5, power=0.99)


def test_empirical_power_matches_theory():
    rng = np.random.default_rng(0)
    p1, p2 = 0.12, 0.15
    n1, n2 = pw.sample_size_proportions(p1, p2)
    sims = 4000
    xa, xb = rng.binomial(n1, p1, sims), rng.binomial(n2, p2, sims)
    pbar = (xa + xb) / (n1 + n2)
    z = (xb / n2 - xa / n1) / np.sqrt(pbar * (1 - pbar) * (1 / n1 + 1 / n2))
    assert abs((np.abs(z) > 1.959964).mean() - 0.8) < 0.03


def test_means_match_statsmodels():
    n1, n2 = pw.sample_size_means(delta=2, sd=10)
    assert n1 == pytest.approx(393, abs=2)  # d = 0.2 -> ~393 per arm
    assert pw.power_means(2, 10, n1, n2) >= 0.8
    assert pw.mde_means(10, n1, n2) == pytest.approx(2, abs=0.05)


def test_plan_bonferroni_increases_n_and_reports_days():
    a = pw.plan_proportions(0.2, mde=0.05, relative=False)
    b = pw.plan_proportions(0.2, mde=0.05, n_comparisons=4, daily_traffic=1000)
    assert b["n_control"] > a["n_control"]
    assert b["alpha_adjusted"] == pytest.approx(0.0125)
    assert b["days_needed"] == -(-b["n_total"] // 1000)
    assert b["curve"][-1]["power"] > b["curve"][0]["power"]


def test_relative_mde_and_validation():
    plan = pw.plan_proportions(0.2, mde=0.1, relative=True)
    assert plan["target"] == pytest.approx(0.22)
    with pytest.raises(ValueError):
        pw.plan_proportions(0.2)  # neither mde nor target
    with pytest.raises(ValueError):
        pw.plan_proportions(0.2, mde=0.1, target=0.3)  # both
    with pytest.raises(ValueError):
        pw.plan_proportions(1.2, mde=0.1)
