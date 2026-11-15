import React, { useCallback, useEffect, useRef, useState } from "react";
import { get, post, upload } from "../api.js";
import { ErrorBox, Field, Spinner } from "./ui.jsx";
import { num } from "../format.js";

const SCENARIOS = [
  { id: "ab_test", name: "Randomised A/B test", blurb: "10,000s of users, known lift", effectKey: "rel_lift", effectLabel: "True relative lift", effectDefault: 0.1, step: 0.05 },
  { id: "observational", name: "Observational study", blurb: "Confounded treatment, known effect", effectKey: "true_effect", effectLabel: "True effect", effectDefault: 2, step: 0.5 },
  { id: "panel", name: "Rollout over time", blurb: "Treated vs untreated units, weekly", effectKey: "true_effect", effectLabel: "True effect", effectDefault: 5, step: 0.5 },
];

export default function DataStep({ profile, onProfile }) {
  const [samples, setSamples] = useState([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [over, setOver] = useState(false);
  const [scenario, setScenario] = useState("ab_test");
  const [effect, setEffect] = useState(0.1);
  const input = useRef(null);

  useEffect(() => {
    get("/api/samples").then(setSamples).catch(() => setSamples([]));
  }, []);

  const run = useCallback(async (label, fn) => {
    setBusy(label);
    setError("");
    try {
      onProfile(await fn());
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }, [onProfile]);

  const onFile = (file) => {
    if (!file) return;
    if (!/\.(csv|tsv|txt)$/i.test(file.name)) return setError("Please choose a .csv file.");
    run("Reading file", () => upload(file));
  };

  const sc = SCENARIOS.find((s) => s.id === scenario);
  const generate = () =>
    run("Simulating", () => post("/api/datasets/simulate", { scenario, seed: 1, [sc.effectKey]: Number(effect), ...(scenario === "ab_test" ? { n_total: 20000 } : {}) }));

  return (
    <div className="card">
      <h2>1 · Bring your data</h2>
      <p className="sub">Upload a CSV, try a bundled sample, or generate a dataset where the right answer is known.</p>
      <div
        className={`drop ${over ? "over" : ""}`}
        role="button" tabIndex={0}
        onClick={() => input.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), input.current?.click())}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); onFile(e.dataTransfer.files?.[0]); }}
      >
        <strong>Drop a CSV here</strong>
        <span className="hint">or click to browse · up to 10 MB · one row per user or observation</span>
        <input ref={input} type="file" accept=".csv,.tsv,.txt,text/csv" className="sr" tabIndex={-1} onChange={(e) => { onFile(e.target.files?.[0]); e.target.value = ""; }} />
      </div>

      {samples.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <div className="lbl hint">Bundled samples</div>
          <div className="row">
            {samples.map((s) => (
              <button key={s.name} className="btn ghost small" disabled={!!busy} onClick={() => run("Loading sample", () => post(`/api/samples/${s.name}`))}>
                {s.name.replace(/_/g, " ")}
              </button>
            ))}
          </div>
        </div>
      )}

      <details style={{ marginTop: 10 }}>
        <summary>Generate simulated data</summary>
        <div className="grid" style={{ gridTemplateColumns: "1fr", alignItems: "end", marginTop: 8 }}>
          <Field label="Scenario">
            <select value={scenario} onChange={(e) => { const s = SCENARIOS.find((x) => x.id === e.target.value); setScenario(s.id); setEffect(s.effectDefault); }}>
              {SCENARIOS.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </Field>
          <Field label={sc.effectLabel} help={sc.blurb}>
            <input type="number" step={sc.step} value={effect} onChange={(e) => setEffect(e.target.value)} />
          </Field>
          <button className="btn small" style={{ justifySelf: "start" }} disabled={!!busy} onClick={generate}>Generate</button>
        </div>
      </details>

      <div style={{ marginTop: 12 }}>
        {busy && <Spinner>{busy}…</Spinner>}
        <ErrorBox error={error} />
      </div>
      {profile && <Profile profile={profile} />}
    </div>
  );
}

function Profile({ profile }) {
  const kindText = { rows: "row-level data", aggregated: "aggregated counts per variant", labels: "variant names only" }[profile.kind];
  return (
    <div style={{ marginTop: 18 }}>
      <h3 style={{ fontSize: 18 }}>{profile.name}</h3>
      <p className="sub" style={{ marginBottom: 8 }}>
        <span className="num">{num(profile.n_rows, 0)}</span> rows · <span className="num">{profile.n_cols}</span> columns · detected as {kindText}
        {profile.meta?.truth && " · simulated, true effect is known"}
      </p>
      {profile.kind === "labels" && <div className="callout">This file only lists variant names. It is used automatically as labels when you load the sample sessions file; upload the experiment data to analyse.</div>}
      <details>
        <summary>Columns and preview</summary>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Column</th><th>Detected as</th><th className="n">Unique</th><th className="n">Missing</th></tr></thead>
            <tbody>
              {profile.columns.map((c) => (
                <tr key={c.name}><td className="mono">{c.name}</td><td>{c.role}</td><td className="n">{c.n_unique}</td><td className="n">{c.n_missing}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="table-wrap" style={{ marginTop: 10 }}>
          <table>
            <thead><tr>{profile.columns.slice(0, 8).map((c) => <th key={c.name}>{c.name}</th>)}</tr></thead>
            <tbody>
              {profile.preview.map((r, i) => (
                <tr key={i}>{profile.columns.slice(0, 8).map((c) => <td key={c.name} className="mono">{String(r[c.name] ?? "").slice(0, 22)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
