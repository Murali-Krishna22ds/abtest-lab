import React from "react";
import { METHODS, levelsFor, method as methodOf, optionsFor, validate } from "../methods.js";
import { Chips, ErrorBox, Field, Spinner } from "./ui.jsx";

export function MethodPicker({ profile, value, onChange }) {
  return (
    <div className="card">
      <h2>2 · Pick a method</h2>
      <p className="sub">Choose the question you are asking.</p>
      <div className="methods">
        {METHODS.map((m) => {
          const blocked = profile.kind === "labels" || (m.needs === "rows" && profile.kind !== "rows");
          return (
            <button key={m.id} className="method" aria-pressed={value === m.id} disabled={blocked} onClick={() => onChange(m.id)}
              title={blocked ? "Needs row-level data" : undefined}>
              <b>{m.name}</b>
              <span className="tag">{m.tag}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function MethodForm({ profile, methodId, config, onConfig, onRun, running, error }) {
  const m = methodOf(methodId);
  const set = (k, v) => onConfig({ ...config, [k]: v });
  const problem = validate(methodId, config, profile);
  const agg = profile.kind === "aggregated";
  return (
    <div className="card">
      <h2>3 · Set up “{m.name}”</h2>
      <p className="sub">{m.blurb}</p>
      {agg && (methodId === "frequentist" || methodId === "bayesian") && (
        <div className="callout info">This file has one row per variant with user and conversion counts, so only conversion rate can be analysed. No column choices are needed.</div>
      )}
      <div className="grid cols-2">
        {m.fields.map((f) => {
          if (agg && f.aggregated === false) return null;
          const v = config[f.key];
          const wide = f.type === "columns";
          return (
            <div key={f.key} style={wide ? { gridColumn: "1 / -1" } : undefined}>
              {f.type === "checkbox" ? (
                <label className="check">
                  <input type="checkbox" checked={!!v} onChange={(e) => set(f.key, e.target.checked)} />
                  <span>{f.label}</span>
                </label>
              ) : f.type === "columns" ? (
                <Field label={f.label} help={f.help}>
                  <Chips label={f.label} options={optionsFor(profile, f, config)} value={(v || []).filter((c) => optionsFor(profile, f, config).includes(c))} onChange={(x) => set(f.key, x)} />
                </Field>
              ) : f.type === "number" ? (
                <Field label={f.label} help={f.help}>
                  <input type="number" value={v ?? ""} step={f.step} min={f.min} max={f.max} onChange={(e) => set(f.key, e.target.value)} />
                </Field>
              ) : f.type === "text" ? (
                <Field label={f.label} help={f.help}>
                  <input type="text" value={v ?? ""} placeholder={f.placeholder} onChange={(e) => set(f.key, e.target.value)} />
                </Field>
              ) : f.type === "select" ? (
                <Field label={f.label} help={f.help}>
                  <select value={v ?? ""} onChange={(e) => set(f.key, e.target.value)}>
                    {f.options.map(([val, text]) => <option key={val} value={val}>{text}</option>)}
                  </select>
                </Field>
              ) : f.type === "level" ? (
                <LevelField f={f} v={v} cfg={config} profile={profile} set={set} />
              ) : (
                <Field label={f.label} help={f.help}>
                  <select value={v ?? ""} onChange={(e) => set(f.key, e.target.value)}>
                    {f.optional && <option value="">(none)</option>}
                    {!f.optional && !v && <option value="">Choose…</option>}
                    {optionsFor(profile, f).map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </Field>
              )}
            </div>
          );
        })}
      </div>
      {methodId === "bayesian" && config.engine === "pymc" && (
        <p className="hint" style={{ marginTop: 10 }}>The first PyMC run compiles the model and can take 10–20 seconds; later runs are much faster.</p>
      )}
      <div className="row" style={{ marginTop: 18 }}>
        <button className="btn" onClick={onRun} disabled={running || !!problem}>{running ? "Analysing…" : "Run analysis"}</button>
        {running && <Spinner>Working on it</Spinner>}
        {problem && !running && <span className="hint">{problem}</span>}
      </div>
      <div style={{ marginTop: 12 }}><ErrorBox error={error} /></div>
    </div>
  );
}

function LevelField({ f, v, cfg, profile, set }) {
  const levels = levelsFor(profile, cfg, f);
  return (
    <Field label={f.label} help={f.help}>
      {levels.length ? (
        <select value={v ?? ""} onChange={(e) => set(f.key, e.target.value)}>
          <option value="">{f.optional ? "(auto-detect)" : "Choose…"}</option>
          {levels.map((l) => <option key={l} value={l}>{l}</option>)}
        </select>
      ) : (
        <input type="text" value={v ?? ""} onChange={(e) => set(f.key, e.target.value)} placeholder={f.optional ? "(auto-detect)" : ""} />
      )}
    </Field>
  );
}
