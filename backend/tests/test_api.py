"""End-to-end API tests: every endpoint, error handling and cross-checks against reference libraries."""
from __future__ import annotations

import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from scipy import stats
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.power import NormalIndPower, TTestIndPower
from statsmodels.stats.proportion import proportion_effectsize

from app.main import app

client = TestClient(app)


@pytest.fixture(scope="module")
def sessions():
    r = client.post("/api/samples/ab_test_sessions")
    assert r.status_code == 200
    return r.json()


def post(path, **body):
    return client.post(path, json=body)


# --------------------------------------------------------------------------- meta & data
def test_health():
    assert client.get("/api/health").json()["status"] == "ok"


def test_sample_profile_suggests_columns(sessions):
    assert sessions["kind"] == "rows" and sessions["n_rows"] == 15000
    assert "pricing_variant" in sessions["suggestions"]["variant_columns"]
    assert "converted" in sessions["suggestions"]["binary"]
    assert sessions["meta"]["labels_id"]


def test_upload_csv_roundtrip():
    csv = "variant,converted\n" + "\n".join(f"{'control' if i % 2 else 'b'},{int(i % 5 == 0)}" for i in range(400))
    r = client.post("/api/datasets", files={"file": ("t.csv", io.BytesIO(csv.encode()), "text/csv")})
    assert r.status_code == 200 and r.json()["n_rows"] == 400
    again = client.get(f"/api/datasets/{r.json()['id']}")
    assert again.status_code == 200


@pytest.mark.parametrize("payload", [b"", b"a\n", b"a,b\n1,2\n"])
def test_bad_uploads_are_rejected(payload):
    r = client.post("/api/datasets", files={"file": ("bad.csv", io.BytesIO(payload), "text/csv")})
    assert r.status_code == 400 and "detail" in r.json()


def test_duplicate_headers_are_made_unique():
    r = client.post("/api/datasets", files={"file": ("d.csv", io.BytesIO(b"a,a\n1,2\n3,4\n"), "text/csv")}).json()
    assert [c["name"] for c in r["columns"]] == ["a", "a.1"]


def test_unknown_dataset_is_404():
    assert post("/api/analyze/frequentist", dataset_id="nope", outcome="x").status_code == 404


@pytest.mark.parametrize("path", ["/api/samples/..%2Fsecret", "/api/samples/../secret", "/api/samples/%2e%2e%2fpytest.ini"])
def test_sample_path_traversal_is_rejected(path):
    r = client.post(path)
    assert r.status_code in (404, 405, 422)  # exact code depends on routing; what matters is that it is never served


@pytest.mark.parametrize("path", ["/..%2f..%2fetc/passwd", "/%2e%2e/%2e%2e/etc/passwd", "/assets/../../backend/app/main.py"])
def test_static_route_never_leaks_files(path):
    r = client.get(path)
    assert "root:" not in r.text and "FastAPI(" not in r.text and "settings" not in r.text


def test_load_sample_allowlist():
    from app.errors import AppError
    from app.services import datasets as dsv

    with pytest.raises(AppError):
        dsv.load_sample("../pytest")


# --------------------------------------------------------------------------- power
def test_sample_size_matches_reference_values():
    r = post("/api/power/proportions/sample-size", baseline=0.10, mde=0.02).json()
    assert r["n_control"] == 3841  # R: power.prop.test(p1=.10, p2=.12, power=.8)
    ref = NormalIndPower().solve_power(proportion_effectsize(0.12, 0.10), power=0.8, alpha=0.05)
    assert abs(r["n_control"] - ref) / ref < 0.01
    m = post("/api/power/means/sample-size", delta=0.5, sd=1.0).json()
    assert m["n_control"] == 64  # G*Power


@pytest.mark.parametrize("d,n", [(0.3, 100), (0.5, 64), (0.2, 500)])
def test_means_power_matches_statsmodels(d, n):
    r = post("/api/power/means/power", delta=d, sd=1, n_control=n).json()
    assert r["power"] == pytest.approx(TTestIndPower().power(d, n, 0.05), abs=0.01)


def test_mde_roundtrip():
    mde = post("/api/power/proportions/mde", baseline=0.1, n_control=3841).json()["absolute_mde"]
    p = post("/api/power/proportions/power", baseline=0.1, target=0.1 + mde, n_control=3841).json()["power"]
    assert p == pytest.approx(0.8, abs=0.005)


def test_bonferroni_planning_needs_more_users():
    one = post("/api/power/proportions/sample-size", baseline=0.1, mde=0.02).json()
    ten = post("/api/power/proportions/sample-size", baseline=0.1, mde=0.02, n_comparisons=10).json()
    assert ten["n_control"] > one["n_control"] and ten["alpha_adjusted"] == pytest.approx(0.005)


def test_power_validation_errors():
    assert post("/api/power/proportions/sample-size", baseline=0.1).status_code == 422
    assert post("/api/power/proportions/sample-size", baseline=1.2, mde=0.01).status_code == 422
    assert post("/api/power/proportions/sample-size", baseline=0.1, mde=0.01, target=0.2).status_code == 422


# --------------------------------------------------------------------------- classical tests
def test_chi_square_matches_scipy():
    r = post("/api/tests/chi-square", x_control=100, n_control=1000, x_treatment=130, n_treatment=1000).json()
    chi2, p, *_ = stats.chi2_contingency([[100, 900], [130, 870]], correction=False)
    assert r["statistic"] == pytest.approx(chi2) and r["p_value"] == pytest.approx(p)
    assert r["ci_low"] < r["diff"] < r["ci_high"]


def test_welch_matches_scipy():
    rng = np.random.default_rng(1)
    a, b = rng.normal(10, 3, 80), rng.normal(11, 4, 120)
    r = post("/api/tests/t-test", mean_control=a.mean(), sd_control=a.std(ddof=1), n_control=80,
             mean_treatment=b.mean(), sd_treatment=b.std(ddof=1), n_treatment=120).json()
    ref = stats.ttest_ind(b, a, equal_var=False)
    assert r["statistic"] == pytest.approx(ref.statistic) and r["p_value"] == pytest.approx(ref.pvalue)


@pytest.mark.parametrize("method,sm", [("bonferroni", "bonferroni"), ("holm", "holm"), ("bh", "fdr_bh")])
def test_corrections_match_statsmodels(method, sm):
    p = np.random.default_rng(3).uniform(0, 0.2, 40).tolist()
    got = np.array(post("/api/tests/adjust-pvalues", p_values=p, method=method).json()["adjusted"])
    assert np.allclose(got, multipletests(p, method=sm)[1])


def test_srm_flags_bad_split():
    assert post("/api/tests/srm", counts=[5000, 5100]).json()["p_value"] > 0.05
    assert post("/api/tests/srm", counts=[5000, 6000]).json()["p_value"] < 0.001


def test_invalid_counts_rejected():
    assert post("/api/tests/chi-square", x_control=11, n_control=10, x_treatment=1, n_treatment=10).status_code == 422


# --------------------------------------------------------------------------- analyses on the sample data
def test_frequentist_multiple_tests_with_correction(sessions):
    body = dict(dataset_id=sessions["id"], labels_id=sessions["meta"]["labels_id"], outcome="converted",
                variant_columns=sessions["suggestions"]["variant_columns"])
    holm = post("/api/analyze/frequentist", correction="holm", **body).json()
    none = post("/api/analyze/frequentist", correction="none", **body).json()
    assert len(holm["result"]["comparisons"]) == 6
    for h, n in zip(holm["result"]["comparisons"], none["result"]["comparisons"]):
        assert h["p_adjusted"] >= n["p_adjusted"] - 1e-12
    assert holm["narrative"]["headline"] and holm["narrative"]["caveats"]
    assert "Original Icon" in str(holm["result"]["comparisons"][0]["control_label"])


def test_frequentist_continuous_uses_welch(sessions):
    r = post("/api/analyze/frequentist", dataset_id=sessions["id"], outcome="time_spent_seconds",
             variant_columns=["pricing_variant"]).json()
    assert {c["test"] for c in r["result"]["comparisons"]} == {r["result"]["comparisons"][0]["test"]}
    assert "t" in r["result"]["comparisons"][0]["test"].lower()


def test_frequentist_aggregated_summary_file():
    s = client.post("/api/samples/ab_test_summary").json()
    r = post("/api/analyze/frequentist", dataset_id=s["id"], labels_id=s["meta"]["labels_id"])
    assert r.status_code == 200 and len(r.json()["result"]["comparisons"]) == 6


def test_frequentist_rejects_bad_input(sessions):
    assert post("/api/analyze/frequentist", dataset_id=sessions["id"], outcome="nope", variant_columns=["pricing_variant"]).status_code == 422
    assert post("/api/analyze/frequentist", dataset_id=sessions["id"], outcome="converted").status_code == 422


def test_sequential_on_sample(sessions):
    r = post("/api/analyze/sequential", dataset_id=sessions["id"], variant_column="icon_design_variant",
             outcome="converted", time_column="session_date", n_looks=8).json()
    looks = r["result"]["looks"]
    assert len(looks) == 8 and looks[-1]["info_fraction"] == pytest.approx(1.0)
    assert looks[0]["gs_bound"] > looks[-1]["gs_bound"]  # O'Brien-Fleming boundaries shrink
    assert all(l["cs_low"] <= l["theta"] <= l["cs_high"] for l in looks)
    assert r["result"]["naive_peeking_false_positive_rate"] > 0.05


def test_sequential_requires_row_level_data():
    s = client.post("/api/samples/ab_test_summary").json()
    assert post("/api/analyze/sequential", dataset_id=s["id"], variant_column="variant_key", outcome="conversions").status_code == 422


def test_bayesian_conjugate_matches_exact(sessions):
    r = post("/api/analyze/bayesian", dataset_id=sessions["id"], outcome="converted",
             variant_columns=["icon_design_variant"], engine="conjugate", rope=0.005).json()
    for c in r["result"]["experiments"][0]["comparisons"]:
        assert c["prob_beats_control"] == pytest.approx(c["prob_beats_control_exact"], abs=0.01)
        assert 0 <= c["prob_in_rope"] <= 1


@pytest.mark.slow
def test_bayesian_pymc_agrees_with_exact(sessions):
    r = post("/api/analyze/bayesian", dataset_id=sessions["id"], outcome="converted",
             variant_columns=["pricing_variant"], engine="pymc", draws=1000, chains=2).json()
    for c in r["result"]["experiments"][0]["comparisons"]:
        assert c["prob_beats_control"] == pytest.approx(c["prob_beats_control_exact"], abs=0.02)
    assert (r["result"]["diagnostics"]["r_hat_max"] or 1.0) < 1.02


def test_bayesian_rejects_continuous_outcome(sessions):
    assert post("/api/analyze/bayesian", dataset_id=sessions["id"], outcome="time_spent_seconds",
                variant_columns=["pricing_variant"], engine="conjugate").status_code == 422


# --------------------------------------------------------------------------- causal
def test_simulated_ab_known_effect_is_recovered():
    d = post("/api/datasets/simulate", scenario="ab_test", n_total=60000, baseline=0.1, rel_lift=0.2, seed=5).json()
    s = d["meta"]["suggested"]
    r = post("/api/analyze/frequentist", dataset_id=d["id"], outcome=s["outcome"], variant_columns=["variant"]).json()
    c = r["result"]["comparisons"][0]
    assert c["ci_low"] <= 0.02 <= c["ci_high"] and c["significant"]


@pytest.mark.slow
def test_psm_removes_confounding():
    d = post("/api/datasets/simulate", scenario="observational", n=4000, true_effect=2.0, confounding=1.5, seed=2).json()
    s = d["meta"]["suggested"]
    r = post("/api/analyze/psm", dataset_id=d["id"], treatment="treated", outcome="outcome",
             covariates=s["covariates"], n_boot=60, cross_check=True).json()["result"]
    assert abs(r["naive_difference"] - 2.0) > abs(r["estimate"] - 2.0)  # matching beats the raw gap
    assert r["ci_low"] <= 2.0 <= r["ci_high"] and r["balance_ok"]
    assert {"dowhy_psm", "econml_dr"} <= set(r["cross_checks"])


@pytest.fixture(scope="module")
def panel():
    return post("/api/datasets/simulate", scenario="panel", true_effect=5.0, seed=1).json()


def test_did_runs_and_checks_trends(panel):
    r = post("/api/analyze/did", dataset_id=panel["id"], outcome="outcome", group_col="group", treated_value="treated",
             time_col="date", cutoff=panel["meta"]["suggested"]["cutoff"], unit_col="unit").json()
    assert r["result"]["ci_low"] < r["result"]["estimate"] < r["result"]["ci_high"]
    assert "pre_trend" in r["result"] and r["result"]["cross_check"]["library"] == "DoWhy"
    assert r["result"]["cross_check"]["estimate"] == pytest.approx(r["result"]["estimate"], abs=1e-6)


def test_synthetic_control_recovers_effect(panel):
    r = post("/api/analyze/synthetic-control", dataset_id=panel["id"], outcome="outcome", unit_col="unit",
             time_col="date", intervention=panel["meta"]["suggested"]["cutoff"], group_col="group",
             treated_value="treated").json()["result"]
    assert r["estimate"] == pytest.approx(5.0, abs=1.5)
    assert sum(w["weight"] for w in r["weights"]) == pytest.approx(1.0, abs=1e-3)


def test_synthetic_narrative_counts_placebos_correctly(panel):
    """Regression: the placebo count was computed as n*p-1 instead of p*(n+1)-1, printing '-0 of them'."""
    out = post("/api/analyze/synthetic-control", dataset_id=panel["id"], outcome="outcome", unit_col="unit", time_col="date",
               intervention=panel["meta"]["suggested"]["cutoff"], group_col="group", treated_value="treated").json()
    text = " ".join(out["narrative"]["summary"])
    assert "-0 of them" not in text and "Placebo test" in text
    n, p = out["result"]["n_placebos"], out["result"]["p_value"]
    assert round(p * (n + 1) - 1) >= 0


def test_did_bad_cutoff(panel):
    assert post("/api/analyze/did", dataset_id=panel["id"], outcome="outcome", group_col="group", treated_value="treated",
                time_col="date", cutoff="not-a-date", unit_col="unit").status_code == 422


# --------------------------------------------------------------------------- studies
def test_peeking_simulation_shows_inflation_and_control():
    r = post("/api/sequential/peeking-simulation", n_looks=10, sims=1500, n_max=4000).json()["methods"]
    assert r["naive_peeking"]["reject_rate"] > 0.12
    assert r["group_sequential"]["reject_rate"] < 0.075 and r["msprt"]["reject_rate"] < 0.075
    assert r["fixed_horizon"]["reject_rate"] == pytest.approx(0.05, abs=0.02)


def test_boundaries_match_monte_carlo_validated_values():
    """Values were validated independently: 1e6 simulated Brownian paths give type-I error 0.050 for each design."""
    obf = post("/api/sequential/boundaries", n_looks=5, alpha=0.05, spending="obf").json()["z_bounds"]
    assert obf == pytest.approx([4.383, 3.100, 2.553, 2.254, 2.064], abs=0.01)
    pocock = post("/api/sequential/boundaries", n_looks=5, alpha=0.05, spending="pocock").json()["z_bounds"]
    assert pocock[0] == pytest.approx(2.438, abs=0.01) and max(pocock) - min(pocock) < 0.1


def test_multiple_testing_simulation_controls_errors():
    m = post("/api/multiple-testing/simulation", m=20, m_true=5, sims=3000).json()["methods"]
    assert m["none"]["fwer"] > 0.4  # uncorrected testing almost always produces a false positive
    assert m["bonferroni"]["fwer"] < 0.07 and m["holm"]["fwer"] < 0.07
    assert m["bh"]["fdr"] < 0.07 and m["bh"]["power"] > m["bonferroni"]["power"]


@pytest.mark.slow
def test_bayesian_results_are_memoised_and_unchanged(sessions):
    """Identical requests skip MCMC; the cached copy must be identical and isolated from later edits."""
    import time

    body = dict(dataset_id=sessions["id"], labels_id=sessions["meta"]["labels_id"], outcome="converted",
                variant_columns=["screenshots_variant"], engine="pymc", draws=777, chains=2)
    t0 = time.perf_counter(); first = post("/api/analyze/bayesian", **body).json(); cold = time.perf_counter() - t0
    t0 = time.perf_counter(); second = post("/api/analyze/bayesian", **body).json(); warm = time.perf_counter() - t0
    for r in (first, second):
        r.pop("runtime_ms")
        r["result"]["diagnostics"].pop("seconds", None)
    assert first == second
    assert warm < cold / 3
    # a different label set must not be served stale labels from the cache
    plain = post("/api/analyze/bayesian", **{**body, "labels_id": None}).json()
    assert plain["result"]["experiments"][0]["comparisons"][0]["variant_label"] != first["result"]["experiments"][0]["comparisons"][0]["variant_label"]
