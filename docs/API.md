# API and data reference

Interactive docs are served by the running app at `/docs` (Swagger UI) and `/redoc`. The machine-readable spec is
[`openapi.json`](openapi.json) (regenerate with `make openapi`). All bodies are JSON unless noted. Errors always have the shape
`{"detail": "<plain-English message>"}` with status **404** (unknown dataset or sample), **422** (the request or the data cannot support
the analysis), **400** (unreadable file), **413** (file too large) or **503** (all heavy-compute slots busy; retry).

## Endpoints

| Area | Method and path | Purpose |
|---|---|---|
| Meta | `GET /api/health` | Liveness and version |
| Data | `POST /api/datasets` (multipart `file`) | Upload a CSV; returns a profile and a `dataset_id` |
| Data | `GET /api/datasets/{id}` · `GET /api/datasets/{id}/download` | Re-read a profile; download as CSV |
| Data | `GET /api/samples` · `POST /api/samples/{name}` | Bundled sample files |
| Data | `POST /api/datasets/simulate` | Generate `ab_test`, `observational` or `panel` data with a known true effect |
| Power | `POST /api/power/{proportions,means}/sample-size` | Users needed for a target power |
| Power | `POST /api/power/{proportions,means}/power` | Power for a given sample size |
| Power | `POST /api/power/{proportions,means}/mde` | Minimum detectable effect for a given sample size |
| Tests | `POST /api/tests/chi-square` · `/t-test` · `/chi-square-table` · `/srm` | Classical tests from summary numbers |
| Tests | `POST /api/tests/adjust-pvalues` | Bonferroni, Holm, Benjamini-Hochberg |
| Analyze | `POST /api/analyze/frequentist` | Chi-square / Welch t-test for every variant vs control, with correction |
| Analyze | `POST /api/analyze/sequential` | Group-sequential boundaries and always-valid p-values per look |
| Analyze | `POST /api/analyze/bayesian` | P(variant beats control), expected lift and loss (PyMC or closed form) |
| Analyze | `POST /api/analyze/psm` | Propensity-score matching with balance checks and cross-checks |
| Analyze | `POST /api/analyze/did` | Difference-in-differences with parallel-trends check |
| Analyze | `POST /api/analyze/synthetic-control` | Synthetic control with placebo inference |
| Studies | `POST /api/sequential/boundaries` · `/api/sequential/peeking-simulation` | Stopping boundaries; error rate of peeking strategies |
| Studies | `POST /api/multiple-testing/simulation` | FWER / FDR / power of each correction |

## Workflow

```
POST /api/datasets            ->  { id, kind, columns[], suggestions{}, preview[], meta{} }
POST /api/analyze/<method>    ->  { method, result{}, narrative{headline, verdict, summary[], caveats[]}, runtime_ms }
```

Every analysis response has a `narrative` written for non-statisticians and a `result` with every number behind it, including the series
the front end plots (`looks`, `posterior_density`, `balance`, `series`, `placebo_gaps`, ...).

## Examples (responses are real, abbreviated)

```bash
curl -s localhost:8000/api/power/proportions/sample-size -H 'content-type: application/json' \
  -d '{"baseline":0.10,"mde":0.02,"daily_traffic":2000}'
```
```json
{"baseline":0.1,"target":0.12,"power":0.8,"achieved_power":0.80002,"n_control":3841,"n_treatment":3841,"n_total":7682,"days_needed":4, "...":"curve, alpha, ratio"}
```

```bash
curl -s localhost:8000/api/tests/chi-square -H 'content-type: application/json' \
  -d '{"x_control":100,"n_control":1000,"x_treatment":130,"n_treatment":1000}'
```
```json
{"p_control":0.1,"p_treatment":0.13,"diff":0.03,"ci_low":0.0020,"ci_high":0.0581,"rel_lift":0.3,"statistic":4.4215,"p_value":0.0355,"cohens_h":0.0942,"test":"chi-square","df":1}
```

```bash
curl -s localhost:8000/api/tests/adjust-pvalues -H 'content-type: application/json' \
  -d '{"p_values":[0.001,0.01,0.03,0.2],"method":"bh"}'
# {"method":"bh","alpha":0.05,"adjusted":[0.004,0.02,0.04,0.2],"reject":[true,true,true,false],"n_rejected":3}
```

Analysing an uploaded or bundled dataset:

```bash
ID=$(curl -s -X POST localhost:8000/api/samples/ab_test_sessions | python -c 'import sys,json;print(json.load(sys.stdin)["id"])')
curl -s localhost:8000/api/analyze/sequential -H 'content-type: application/json' -d \
 "{\"dataset_id\":\"$ID\",\"variant_column\":\"icon_design_variant\",\"outcome\":\"converted\",\"time_column\":\"session_date\",\"n_looks\":10}"
```

An invalid request:

```json
{"detail":"Outcome column 'nope' not found."}
```

## Request fields by analysis

| Analysis | Required | Optional (default) |
|---|---|---|
| `frequentist` | `dataset_id`; for row-level data `outcome`, `variant_columns[]` | `control_level` (auto), `correction` (`holm`; also `bonferroni`, `bh`, `none`), `alpha` (0.05), `outcome_kind`, `labels_id` |
| `sequential` | `dataset_id`, `variant_column`, `outcome` | `time_column`, `control_level`, `variant_level`, `n_looks` (10), `spending` (`obf`/`pocock`), `tau`, `alpha` |
| `bayesian` | `dataset_id`; row-level: `outcome` (0/1), `variant_columns[]` | `engine` (`pymc`/`conjugate`), `prior_alpha`/`prior_beta` (1/1), `rope` (0), `draws` (1000), `chains` (4), `hdi_prob` (0.95) |
| `psm` | `dataset_id`, `treatment`, `outcome`, `covariates[]` | `treated_value`, `caliper` (0.2 SD of logit score), `n_neighbors` (1), `n_boot` (100), `cross_check` (true), `refute` (false) |
| `did` | `dataset_id`, `outcome`, `group_col`, `treated_value`, `time_col`, `cutoff` | `unit_col` (cluster-robust errors), `covariates[]`, `cross_check` (true) |
| `synthetic-control` | `dataset_id`, `outcome`, `unit_col`, `time_col`, `intervention`, and either `treated_units[]` or `group_col`+`treated_value` | `freq` (`W`) |

## Data formats

Uploads are CSV (comma, tab or semicolon separated; UTF-8). Limits: 10 MB and 500,000 rows (configurable, see `.env.example`).
Column roles (binary, numeric, categorical, datetime, id) are detected automatically and shown after upload.

| Analysis | Expected shape (one row per ...) | Example columns |
|---|---|---|
| Frequentist, sequential, Bayesian | user or session; a variant column and an outcome column | `variant`, `converted` (0/1 or True/False), `revenue`, `session_date` |
| Frequentist, Bayesian (aggregated) | variant; counts | `test_name`, `variant_key`, `total_users`, `conversions` |
| PSM | unit; treatment flag, outcome, covariates | `treated`, `outcome`, `age`, `income`, `plan` |
| DiD, synthetic control | unit x time period | `unit`, `date`, `outcome`, `group` (`treated`/`control`) |
| Variant names (optional) | variant | `test_name`, `variant_key`, `variant_name` |

The bundled `ab_test_sessions.csv` holds 15,000 sessions across four concurrent tests (icon, description, pricing and screenshots), each
with its own variant column. Analysing several variant columns at once is treated as one family of comparisons for multiple-testing
correction, and the independence of the assignments is checked.

## Result shapes (key fields)

* **frequentist**: `comparisons[]` {`variant_label`, `diff`, `ci_low`, `ci_high`, `rel_lift`, `p_value`, `p_adjusted`, `significant`, `test`}, `srm[]` (sample-ratio checks), `correction`.
* **sequential**: `looks[]` {`n_control`, `n_variant`, `theta`, `z`, `gs_bound`, `naive_p`, `always_valid_p`, `cs_low`, `cs_high`}, `first_look` {`group_sequential`, `msprt`, `naive`}, `final`, `naive_peeking_false_positive_rate`.
* **bayesian**: `experiments[]` {`comparisons[]` {`prob_beats_control`, `expected_diff`, `expected_rel_lift`, `diff_hdi_low/high`, `expected_loss_if_choose_variant`, `prob_in_rope`}, `posterior_density[]`}, `diagnostics` {`r_hat_max`}.
* **psm**: `estimate`, `ci_low`, `ci_high`, `naive_difference`, `balance[]` {`covariate`, `smd_before`, `smd_after`}, `overlap[]`, `cross_checks` {`dowhy_psm`, `econml_dr`}.
* **did**: `estimate`, `ci_*`, `p_value`, `pre_trend` {`p_value`, `slope_difference_per_week`}, `series[]`, `cross_check`.
* **synthetic_control**: `estimate`, `relative_effect`, `p_value`, `pre_rmspe`, `weights[]`, `series[]`, `placebo_gaps[]`.
