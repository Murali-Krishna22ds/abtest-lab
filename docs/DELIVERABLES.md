# Deliverables checklist

| Deliverable | Status | Where |
|---|---|---|
| Working demo (deployed or screen-recorded) | **Screen-recorded** (1:55, 1280x800). **Not deployed**: no cloud access from the build environment; deployment is a one-command `docker compose up --build` on any host. | `docs/demo/demo.webm`, `docs/DEMO.md` |
| GitHub repository with clean commits, README, setup instructions | Local git repository with conventional commit history and README; **needs `git remote add origin <url> && git push -u origin main`** by a team member | repo root, `README.md` |
| Architecture diagram | Done | `docs/architecture.svg` (also `.png`), `docs/ARCHITECTURE.md` |
| Data and API documentation | Done | `docs/API.md`, `docs/openapi.json`, Swagger UI at `/docs` |
| Test results and accuracy / performance numbers | Done, all measured | `docs/TEST_RESULTS.md`, `docs/benchmark_results.md` |
| 10-minute final presentation | Script, timings and slide content ready; deck provided | `docs/PRESENTATION.md`, `docs/Experiment_Lab_Final_Presentation.pptx` |
| Individual reflection from each intern | **Template and prompts provided; each intern must write their own** | `docs/reflections/TEMPLATE.md` |

Reflections are personal accounts of what each person learned and owned. They cannot be written on someone's behalf, so only the template is
supplied. A suggested way to record ownership for the "what I owned" section: assign each workstream below to a named person, and have that
person cite the commits (`git log --author`) and the tests they wrote.

| Workstream | Suggested ownership unit |
|---|---|
| Fundamentals and power service | `stats/power.py`, `routers/power.py`, `docs/01-fundamentals.md` |
| Simulation, tests, corrections | `stats/tests.py`, `corrections.py`, `simulate.py` |
| Sequential testing | `stats/sequential.py` |
| Bayesian A/B | `stats/bayes.py` |
| Observational methods | `stats/causal/` |
| API and orchestration | `routers/`, `services/` |
| Front end | `frontend/` |
| Quality, docs, deployment | tests, `docs/`, `Dockerfile`, CI |
