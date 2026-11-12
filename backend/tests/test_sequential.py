import numpy as np
import pytest

from app.stats import sequential as sq
from app.stats import simulate as sim


def test_obf_boundaries_shape_and_final_near_fixed():
    b = sq.group_sequential_bounds(np.arange(1, 6) / 5, 0.05, "obf")
    assert np.all(np.diff(b) < 0)            # boundaries shrink over time
    assert b[0] > 4 and 1.96 < b[-1] < 2.1   # strict early, close to 1.96 at the end


def test_pocock_is_flatter_than_obf():
    info = np.arange(1, 6) / 5
    assert np.ptp(sq.group_sequential_bounds(info, 0.05, "pocock")) < np.ptp(sq.group_sequential_bounds(info, 0.05, "obf"))


@pytest.mark.parametrize("spending", ["obf", "pocock"])
def test_boundaries_spend_exactly_alpha_by_monte_carlo(spending):
    rng = np.random.default_rng(0)
    K = 5
    info = np.arange(1, K + 1) / K
    b = sq.group_sequential_bounds(info, 0.05, spending)
    z = np.cumsum(rng.normal(size=(300_000, K)) * np.sqrt(1 / K), axis=1) / np.sqrt(info)
    crossed = np.abs(z) >= b
    assert crossed.any(axis=1).mean() == pytest.approx(0.05, abs=0.002)
    # alpha spent up to each look matches the spending function
    cum = np.maximum.accumulate(crossed, axis=1).mean(axis=0)
    target = sq._SPENDING[spending](info, 0.05)
    assert np.allclose(cum, target, atol=0.002)


def test_unequal_looks_and_validation():
    b = sq.group_sequential_bounds([0.3, 0.55, 1.0], 0.05)
    assert len(b) == 3 and b[0] > b[1] > b[2]
    with pytest.raises(ValueError):
        sq.group_sequential_bounds([0.5, 0.4])
    with pytest.raises(ValueError):
        sq.group_sequential_bounds([0.5, 1.2])


def test_msprt_controls_type_one_error_under_continuous_monitoring():
    rng = np.random.default_rng(1)
    sims, n_looks, n_max, p = 3000, 100, 20_000, 0.1
    n_k = np.linspace(200, n_max, n_looks).astype(int)
    inc = np.diff(np.r_[0, n_k])
    xa = np.cumsum(rng.binomial(inc, p, (sims, n_looks)), axis=1)
    xb = np.cumsum(rng.binomial(inc, p, (sims, n_looks)), axis=1)
    theta, s2, _ = sq.binary_sequence(n_k, xa, n_k, xb)
    p_av = sq.msprt_pvalues(theta, s2, sq.default_tau(p) ** 2)
    assert (p_av <= 0.05).any(axis=1).mean() <= 0.06
    naive = (2 * (1 - __import__("scipy").stats.norm.cdf(np.abs(theta / np.sqrt(s2)))) <= 0.05).any(axis=1).mean()
    assert naive > 0.25  # naive peeking with 100 looks is badly inflated


def test_confidence_sequence_covers_truth_at_all_looks():
    rng = np.random.default_rng(2)
    sims, K, true = 2000, 40, 0.02
    n_k = np.linspace(500, 20_000, K).astype(int)
    inc = np.diff(np.r_[0, n_k])
    xa = np.cumsum(rng.binomial(inc, 0.10, (sims, K)), axis=1)
    xb = np.cumsum(rng.binomial(inc, 0.10 + true, (sims, K)), axis=1)
    theta, _, s2 = sq.binary_sequence(n_k, xa, n_k, xb)
    lo, hi = sq.msprt_conf_seq(theta, s2, sq.default_tau(0.1) ** 2, 0.05)
    covered_always = ((lo <= true) & (true <= hi)).all(axis=1).mean()
    assert covered_always >= 0.94


def test_peeking_simulation_shows_inflation_and_valid_alternatives():
    r = sim.simulate_peeking(rel_lift=0.0, n_max=6000, n_looks=10, sims=3000, seed=4)["methods"]
    assert r["naive_peeking"]["reject_rate"] > 0.15
    assert r["fixed_horizon"]["reject_rate"] == pytest.approx(0.05, abs=0.02)
    assert r["group_sequential"]["reject_rate"] <= 0.065
    assert r["msprt"]["reject_rate"] <= 0.065


def test_peeking_simulation_alt_has_power_and_saves_samples():
    r = sim.simulate_peeking(baseline=0.1, rel_lift=0.3, n_max=6000, n_looks=10, sims=2000, seed=5)["methods"]
    assert r["group_sequential"]["reject_rate"] > 0.8
    assert r["group_sequential"]["avg_sample_fraction"] < 1.0


def test_analyze_sequence_structure():
    n = np.array([500, 1000, 1500, 2000])
    theta, s2n, s2a = sq.binary_sequence(n, n * 0.10, n, n * 0.13)
    out = sq.analyze_sequence(theta, s2n, s2a, n / 2000, alpha=0.05)
    assert len(out["looks"]) == 4 and out["looks"][-1]["info_fraction"] == 1.0
    assert out["looks"][0]["cs_low"] < out["looks"][0]["theta"] < out["looks"][0]["cs_high"]
    assert all(l["always_valid_p"] >= l2["always_valid_p"] for l, l2 in zip(out["looks"], out["looks"][1:]))


def test_binary_sequence_validation():
    with pytest.raises(ValueError):
        sq.binary_sequence([10], [11], [10], [1])
