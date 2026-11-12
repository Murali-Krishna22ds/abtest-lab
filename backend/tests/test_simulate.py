import numpy as np
import pytest

from app.stats import simulate as sim


def test_simulate_ab_balanced_and_reproducible():
    a = sim.simulate_ab(n_total=3000, n_variants=3, seed=1)
    b = sim.simulate_ab(n_total=3000, n_variants=3, seed=1)
    assert a.equals(b)
    assert set(a.variant) == {"control", "variant_a", "variant_b"}
    assert a.variant.value_counts().max() - a.variant.value_counts().min() <= 1
    assert a.timestamp.is_monotonic_increasing


def test_simulate_ab_effect_recovered():
    d = sim.simulate_ab(n_total=200_000, baseline=0.1, rel_lift=0.2, seed=2)
    r = d.groupby("variant").converted.mean()
    assert r["variant_a"] / r["control"] - 1 == pytest.approx(0.2, abs=0.03)


def test_simulate_ab_continuous_and_validation():
    d = sim.simulate_ab(n_total=1000, metric="continuous", baseline=50, rel_lift=0.1, sd=5)
    assert "value" in d and "converted" not in d
    with pytest.raises(ValueError):
        sim.simulate_ab(n_total=1000, baseline=0.9, rel_lift=0.5)
    with pytest.raises(ValueError):
        sim.simulate_ab(n_total=3, n_variants=2)


def test_multiple_testing_properties():
    r = sim.simulate_multiple_testing(m=20, m_true=0, sims=4000, seed=1)["methods"]
    assert r["none"]["fwer"] > 0.5                      # 1-(0.95)^20 = 0.64
    assert r["bonferroni"]["fwer"] <= 0.06 and r["holm"]["fwer"] <= 0.06
    r2 = sim.simulate_multiple_testing(m=20, m_true=10, effect_z=3.5, sims=4000, seed=2)["methods"]
    assert r2["bh"]["fdr"] <= 0.05 + 0.01               # FDR controlled
    assert r2["bh"]["power"] >= r2["holm"]["power"] >= r2["bonferroni"]["power"] - 1e-9
    assert r2["none"]["fdr"] > r2["bh"]["fdr"]


def test_observational_is_confounded():
    d = sim.simulate_observational(n=20000, true_effect=2.0, seed=3)
    naive = d[d.treated == 1].outcome.mean() - d[d.treated == 0].outcome.mean()
    assert naive > 3.0
    d0 = sim.simulate_observational(n=20000, true_effect=2.0, confounding=0.0, seed=3)
    assert d0[d0.treated == 1].outcome.mean() - d0[d0.treated == 0].outcome.mean() == pytest.approx(2.0, abs=0.3)


def test_panel_shape_and_effect():
    p = sim.simulate_panel(n_units=20, n_periods=30, n_treated=3, intervention_period=20, true_effect=8, seed=4)
    assert p.shape == (600, 4) and p.group.eq("treated").sum() == 90
    with pytest.raises(ValueError):
        sim.simulate_panel(n_treated=0)
