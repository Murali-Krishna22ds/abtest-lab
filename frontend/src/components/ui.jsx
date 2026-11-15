import React from "react";

export function Spinner({ children }) {
  return (
    <span role="status" aria-live="polite">
      <i className="spinner" aria-hidden="true" />
      {children}
    </span>
  );
}

export function ErrorBox({ error }) {
  if (!error) return null;
  return (
    <div className="callout err" role="alert">
      <strong>Something needs attention.</strong> {error}
    </div>
  );
}

export function Field({ label, help, children }) {
  return (
    <label className="field">
      <span className="lbl">{label}</span>
      {children}
      {help && <small>{help}</small>}
    </label>
  );
}

export function Chips({ options, value, onChange, label }) {
  const set = new Set(value || []);
  const toggle = (o) => {
    const next = new Set(set);
    next.has(o) ? next.delete(o) : next.add(o);
    onChange([...next]);
  };
  return (
    <div className="chips" role="group" aria-label={label}>
      {options.map((o) => (
        <button type="button" key={o} className="chip" aria-pressed={set.has(o)} onClick={() => toggle(o)}>
          {o}
        </button>
      ))}
    </div>
  );
}

export function Fact({ k, v, s }) {
  return (
    <div className="fact">
      <div className="k">{k}</div>
      <div className="v">{v}</div>
      {s && <div className="s">{s}</div>}
    </div>
  );
}

export function Legend({ items }) {
  return (
    <div className="legend">
      {items.map(([c, t]) => (
        <span key={t}>
          <i style={{ background: c }} />
          {t}
        </span>
      ))}
    </div>
  );
}

export function Chart({ title, caption, children, legend }) {
  return (
    <section className="chart">
      <h3>{title}</h3>
      {caption && <p className="cap">{caption}</p>}
      {legend && <Legend items={legend} />}
      {children}
    </section>
  );
}

export function Tip({ active, payload, label, fmt }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="tip">
      {label !== undefined && <div className="mono">{String(label)}</div>}
      {payload
        .filter((p) => p.value !== undefined && p.value !== null)
        .map((p) => (
          <div key={p.dataKey + p.name} style={{ color: p.color }}>
            {p.name}: <span className="mono">{fmt ? fmt(p.value) : Array.isArray(p.value) ? p.value.map((v) => v?.toFixed?.(3)).join(" – ") : p.value?.toFixed?.(4) ?? p.value}</span>
          </div>
        ))}
    </div>
  );
}
