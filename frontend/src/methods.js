/** Catalogue of analyses: what each needs, the form fields, defaults and request building. */

const ids = (profile) => profile.columns.map((c) => c.name);
const withRole = (profile, ...roles) => profile.columns.filter((c) => roles.includes(c.role)).map((c) => c.name);

export const METHODS = [
  {
    id: "frequentist", name: "Compare variants", tag: "t-test · chi-square · corrections", endpoint: "/api/analyze/frequentist",
    blurb: "Is each variant different from control? Uses a chi-square test for conversions and Welch's t-test for averages, and corrects for testing many variants.",
    needs: "any",
    fields: [
      { key: "outcome", label: "Outcome to compare", type: "column", roles: ["binary", "numeric"], aggregated: false, help: "A 0/1 column (converted) or a number (revenue, time spent)." },
      { key: "variant_columns", label: "Variant column(s)", type: "columns", roles: ["categorical", "binary"], aggregated: false, help: "Each column is analysed as its own experiment." },
      { key: "control_level", label: "Control group", type: "level", levelsOf: "variant_columns", optional: true, help: "Leave blank to auto-detect (a level named “control”)." },
      { key: "correction", label: "Multiple-testing correction", type: "select", options: [["holm", "Holm (strict, recommended)"], ["bonferroni", "Bonferroni (strictest)"], ["bh", "Benjamini-Hochberg (controls false discovery rate)"], ["none", "None"]] },
      { key: "alpha", label: "Significance level (α)", type: "number", step: 0.01, min: 0.001, max: 0.2 },
    ],
  },
  {
    id: "sequential", name: "Peek safely", tag: "sequential testing", endpoint: "/api/analyze/sequential",
    blurb: "Check results as data arrives without inflating false positives. Shows group-sequential boundaries and always-valid p-values side by side with the naive approach.",
    needs: "rows",
    fields: [
      { key: "variant_column", label: "Variant column", type: "column", roles: ["categorical", "binary"] },
      { key: "outcome", label: "Outcome", type: "column", roles: ["binary", "numeric"] },
      { key: "time_column", label: "Time column (order of arrival)", type: "column", roles: ["datetime", "numeric"], optional: true, help: "Strongly recommended; otherwise file order is used." },
      { key: "n_looks", label: "Number of looks", type: "number", step: 1, min: 2, max: 50 },
      { key: "spending", label: "Alpha spending", type: "select", options: [["obf", "O'Brien-Fleming (strict early, powerful late)"], ["pocock", "Pocock (even across looks)"]] },
      { key: "alpha", label: "Significance level (α)", type: "number", step: 0.01, min: 0.001, max: 0.2 },
    ],
  },
  {
    id: "bayesian", name: "Probability B beats A", tag: "Bayesian · PyMC", endpoint: "/api/analyze/bayesian",
    blurb: "Direct answers to “how likely is it that the variant is better?”, plus expected lift and the expected loss if you ship it and are wrong. Conversion outcomes only.",
    needs: "any",
    fields: [
      { key: "outcome", label: "Conversion outcome (0/1)", type: "column", roles: ["binary"], aggregated: false },
      { key: "variant_columns", label: "Variant column(s)", type: "columns", roles: ["categorical", "binary"], aggregated: false },
      { key: "control_level", label: "Control group", type: "level", levelsOf: "variant_columns", optional: true },
      { key: "engine", label: "Engine", type: "select", options: [["pymc", "PyMC sampler (MCMC)"], ["conjugate", "Closed-form Beta-Binomial (instant)"]] },
      { key: "rope", label: "“Negligible” difference (rate points, 0.005 = 0.5 pts)", type: "number", step: 0.001, min: 0, max: 0.5, optional: true },
    ],
  },
  {
    id: "psm", name: "Observational: matching", tag: "propensity score matching", endpoint: "/api/analyze/psm",
    blurb: "No randomisation? Match each treated unit to similar untreated units and compare outcomes. Cross-checked with DoWhy and an EconML doubly-robust estimator.",
    needs: "rows",
    fields: [
      { key: "treatment", label: "Treatment column", type: "column", roles: ["binary", "categorical"] },
      { key: "treated_value", label: "Value meaning “treated”", type: "level", levelsOf: "treatment", optional: true, help: "Only needed if the column is not already 0/1." },
      { key: "outcome", label: "Outcome", type: "column", roles: ["numeric", "binary"] },
      { key: "covariates", label: "Covariates to match on", type: "columns", roles: ["numeric", "binary", "categorical"], exclude: ["treatment", "outcome"], help: "Everything that influences both who gets the treatment and the outcome." },
      { key: "caliper", label: "Match tolerance (caliper, in SDs of the score)", type: "number", step: 0.05, min: 0.05, max: 5 },
      { key: "n_boot", label: "Bootstrap repetitions", type: "number", step: 10, min: 0, max: 1000 },
      { key: "cross_check", label: "Cross-check with DoWhy and EconML", type: "checkbox" },
    ],
  },
  {
    id: "did", name: "Before/after vs control", tag: "difference-in-differences", endpoint: "/api/analyze/did",
    blurb: "Compare how a treated group changed against how an untreated group changed over the same period, with a parallel-trends check.",
    needs: "rows",
    fields: [
      { key: "outcome", label: "Outcome", type: "column", roles: ["numeric"] },
      { key: "group_col", label: "Group column", type: "column", roles: ["categorical", "binary"] },
      { key: "treated_value", label: "Value meaning “treated”", type: "level", levelsOf: "group_col" },
      { key: "time_col", label: "Time column", type: "column", roles: ["datetime", "numeric"] },
      { key: "cutoff", label: "First period after the change", type: "text", placeholder: "2026-07-13 or 28" },
      { key: "unit_col", label: "Unit column (for clustered errors)", type: "column", roles: ["categorical", "id"], optional: true },
      { key: "cross_check", label: "Cross-check with DoWhy", type: "checkbox" },
    ],
  },
  {
    id: "synthetic", name: "One treated unit", tag: "synthetic control", endpoint: "/api/analyze/synthetic-control",
    blurb: "Build a weighted blend of untreated units that tracks the treated unit before the change, then read the gap afterwards. Significance by placebo tests.",
    needs: "rows",
    fields: [
      { key: "outcome", label: "Outcome", type: "column", roles: ["numeric"] },
      { key: "unit_col", label: "Unit column", type: "column", roles: ["categorical", "id"] },
      { key: "time_col", label: "Time column", type: "column", roles: ["datetime", "numeric"] },
      { key: "group_col", label: "Group column", type: "column", roles: ["categorical", "binary"] },
      { key: "treated_value", label: "Value meaning “treated”", type: "level", levelsOf: "group_col" },
      { key: "intervention", label: "First period after the change", type: "text", placeholder: "2026-07-13 or 28" },
    ],
  },
];

export const method = (id) => METHODS.find((m) => m.id === id);

export function optionsFor(profile, field, cfg = {}) {
  const names = field.roles ? withRole(profile, ...field.roles) : ids(profile);
  const banned = new Set((field.exclude || []).map((k) => cfg[k]).filter(Boolean));
  const pool = (names.length ? names : ids(profile)).filter((n) => !banned.has(n));
  return pool;
}

/** Covariates actually used: never the treatment or outcome themselves. */
export const psmCovariates = (cfg) => (cfg.covariates || []).filter((c) => c !== cfg.treatment && c !== cfg.outcome);

export function levelsFor(profile, cfg, field) {
  const src = cfg[field.levelsOf];
  const col = Array.isArray(src) ? src[0] : src;
  const c = profile.columns.find((x) => x.name === col);
  return c?.levels || [];
}

const first = (...xs) => xs.find((x) => x !== undefined && x !== null && x !== "") ?? "";

export function defaultConfig(id, profile) {
  const s = profile.suggestions || {};
  const g = profile.meta?.suggested || {};
  const binary = s.binary?.[0];
  const numeric = s.numeric?.[0];
  const time = first(g.time_col, s.datetime_columns?.[0], s.time_columns?.[0]);
  const base = {
    frequentist: { outcome: first(g.outcome, binary, s.outcomes?.[0]), variant_columns: g.variant_columns || s.variant_columns?.slice(0, 4) || [], control_level: "", correction: "holm", alpha: 0.05 },
    sequential: { variant_column: first(g.variant_column, s.variant_columns?.[0], s.categorical?.[0]), outcome: first(g.outcome, binary, s.outcomes?.[0]), time_column: first(g.time_column, s.datetime_columns?.[0]), n_looks: 10, spending: "obf", alpha: 0.05 },
    bayesian: { outcome: first(g.outcome, binary), variant_columns: g.variant_columns || s.variant_columns?.slice(0, 4) || [], control_level: "", engine: "pymc", rope: 0 },
    psm: { treatment: first(g.treatment, binary, s.categorical?.[0]), treated_value: "", outcome: first(g.outcome, numeric), covariates: g.covariates || [], caliper: 0.2, n_boot: 100, cross_check: true },
    did: { outcome: first(g.outcome, numeric), group_col: first(g.group_col, s.categorical?.[0]), treated_value: first(g.treated_value), time_col: time, cutoff: first(g.cutoff), unit_col: first(g.unit_col, s.unit_columns?.[0]), cross_check: true },
    synthetic: { outcome: first(g.outcome, numeric), unit_col: first(g.unit_col, s.unit_columns?.[0]), time_col: time, group_col: first(g.group_col, s.categorical?.[0]), treated_value: first(g.treated_value), intervention: first(g.cutoff) },
  }[id];
  if (id === "psm" && !base.covariates.length) {
    base.covariates = (s.numeric || []).filter((c) => c !== base.outcome && c !== base.treatment).slice(0, 5);
  }
  return base;
}

/** Returns an error string if the form is incomplete, else null. */
export function validate(id, cfg, profile) {
  const m = method(id);
  if (profile.kind === "labels") return "This file only lists variant names. Upload the experiment data.";
  if (m.needs === "rows" && profile.kind !== "rows") return "This analysis needs one row per user or observation, not aggregated counts.";
  if (profile.kind === "aggregated" && (id === "frequentist" || id === "bayesian")) return null;
  if (id === "psm" && !psmCovariates(cfg).length) return "Choose at least one covariate (other than the treatment and outcome).";
  for (const f of m.fields) {
    if (f.optional || f.type === "checkbox" || f.type === "select" || f.type === "number") continue;
    const v = cfg[f.key];
    if (v === undefined || v === null || v === "" || (Array.isArray(v) && !v.length)) return `Choose a value for “${f.label}”.`;
  }
  return null;
}

export function buildRequest(id, cfg, profile) {
  const body = { dataset_id: profile.id };
  if (profile.meta?.labels_id) body.labels_id = profile.meta.labels_id;
  const agg = profile.kind === "aggregated";
  for (const f of method(id).fields) {
    let v = cfg[f.key];
    if (agg && f.aggregated === false) continue;
    if (f.type === "number") v = v === "" || v === undefined ? undefined : Number(v);
    if (v === "" || v === undefined) continue;
    body[f.key] = v;
  }
  if (id === "psm") {
    body.covariates = psmCovariates(cfg);
    const col = profile.columns.find((c) => c.name === cfg.treatment);
    if (col?.role === "binary") delete body.treated_value;
  }
  if (id === "bayesian") body.draws = 1000;
  if (id === "synthetic") body.treated_units = [];
  return body;
}
