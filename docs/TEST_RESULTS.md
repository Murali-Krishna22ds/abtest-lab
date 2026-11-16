# Test results

Run on a single CPU core, Python 3.12, Node 22, Chromium 153 (Playwright 1.63). Reproduce with `make test e2e bench`.

| Suite | Result | Notes |
|---|---|---|
| Backend (pytest) | **105 passed** in about 13 s | 91% line coverage (`make test-api`) |
| Front-end unit (vitest) | **5 passed** | method catalogue: defaults, validation, request building, covariate-leak guard |
| Browser end-to-end (Playwright) | **15 of 15 checks passed**, zero console or page errors | every analysis method through the real UI (`make e2e`) |
| Clean-install check | **105 passed** in a fresh virtualenv built only from `requirements.lock.txt` | validates the lock file and setup instructions |

## Backend tests by file

| File | Tests | What it covers |
|---|---|---|
| `test_power.py` | 11 | Sample size for 10% to 12% (3,841 per arm), agreement with `statsmodels` for proportions and means, monotone power, allocation ratios, one-sided designs, MDE round trips, simulated power against theory, Bonferroni planning |
| `test_hypothesis_tests.py` | 12 | Chi-square and Welch against SciPy, SRM, Bonferroni/Holm/BH against `statsmodels` |
| `test_sequential.py` | 11 | O'Brien-Fleming vs Pocock shape, alpha spent exactly (Monte Carlo), mSPRT type-I control under continuous monitoring, confidence-sequence coverage at every look, peeking simulation |
| `test_bayes.py` | 7 | PyMC posterior against the exact Beta-Binomial result, priors, ROPE, expected loss |
| `test_causal.py` | 11 | PSM removes confounding bias, DiD recovers the effect and matches DoWhy, synthetic control recovers the effect with placebo inference, parallel-trends violations are flagged, input validation (the EconML cross-check is exercised in `test_api.py`) |
| `test_simulate.py` | 6 | Simulators are reproducible and honour the requested truth |
| `test_api.py` | 47 | Every endpoint; validation errors; uploads; path-traversal safety; agreement with SciPy, statsmodels and published sample-size values (3,841 and 64 per arm); PSM bias removal with DoWhy and EconML cross-checks; narrative regressions |

The four slowest tests (PyMC sampling and PSM with bootstraps) take 1.5 to 2.4 s each and are marked `slow`.

## Independent verification of the hardest component

The group-sequential boundaries are computed by numerical integration, which is easy to get subtly wrong. They were checked against a method that
shares no code with the implementation: simulating 1,000,000 Brownian paths and counting how often any look crosses its boundary.

| Design | Boundaries | Simulated type-I error (target 0.050) |
|---|---|---|
| O'Brien-Fleming, 3 looks | 3.395, 2.407, 2.015 | 0.0502 |
| O'Brien-Fleming, 5 looks | 4.383, 3.100, 2.553, 2.254, 2.064 | 0.0501 |
| O'Brien-Fleming, 10 looks | 6.198 ... 2.122 | 0.0503 |
| Pocock, 3 / 5 / 10 looks | about 2.28 / 2.44 / 2.66 at look 1 | 0.0501 / 0.0501 / 0.0497 |

## Accuracy and performance

Summarised below; full tables in [`benchmark_results.md`](benchmark_results.md).

| Claim | Measured |
|---|---|
| Chi-square and Welch false-positive rate at alpha = 0.05 | 5.1% and 4.9% |
| 95% confidence-interval coverage | 95.2% (both) |
| Power at the planned sample size (target 80%) | 80.8% |
| Uncorrected testing of 20 metrics: chance of at least one false positive | 52.4% |
| Same, with Holm / Bonferroni | 4.2% / 3.6% |
| Peeking 10 times at p < 0.05 with no real effect | 20.9% false positives (4x the promise) |
| Group-sequential (O'Brien-Fleming) under the same peeking | 5.2% false positives, 66.6% power vs 69.3% for a single final test |
| PyMC vs exact probability that B beats A | max gap 0.0055 across 5 scenarios |
| 95% credible-interval coverage over 4,000 random worlds | 94.9% |
| Observational: raw gap vs truth of 2.0 | 7.19 (bias +5.19); matching gives 2.06 (bias +0.06) |
| Panel: true effect 5.0 | DiD 5.04, synthetic control 4.95 |
| Median latency: sample size / chi-square / 4-test analysis / sequential | 9 ms / 4 ms / 60 ms / 12 ms |
| Median latency: Bayesian closed form / PyMC / PSM (100 bootstraps) | 65 ms / about 2 s / 422 ms |

## Bugs found and fixed during verification

These were caught by the tests, the benchmarks or by inspecting the running UI, and each has a regression test or e2e assertion.

* The placebo-test narration printed "-0 of them" because it used `n*p - 1` instead of `p*(n+1) - 1`.
* `scipy.stats.nct` returns NaN for some large noncentralities, which broke minimum-detectable-effect searches; power now falls back to a normal tail around the exact t critical value.
* The matching form offered the treatment column as a covariate, which would silently invalidate the analysis; it is now excluded in the UI and filtered in the request.
* Chart defects: clipped axis labels, blank charts while animating, overlapping ticks and labels.
* Loose dependency ranges let pip choose a scikit-learn that EconML cannot use; ranges are bounded and a lock file added.
* A leftover duplicate power module (0% coverage) was removed.
