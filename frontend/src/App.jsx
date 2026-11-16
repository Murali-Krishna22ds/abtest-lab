import React, { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
import { post } from "./api.js";
import DataStep from "./components/DataStep.jsx";
import { MethodForm, MethodPicker } from "./components/MethodStep.jsx";
import { Spinner } from "./components/ui.jsx";
import { buildRequest, defaultConfig, method as methodOf } from "./methods.js";

// Chart-heavy views are split out so the first paint downloads only the forms (charts load on first use).
const Planner = lazy(() => import("./components/Planner.jsx"));
const Explore = lazy(() => import("./components/Explore.jsx"));
const ResultView = lazy(() => import("./components/ResultView.jsx"));
const Loading = () => <div className="card"><Spinner>Loading charts…</Spinner></div>;

const TABS = [["analyze", "Analyze data"], ["plan", "Plan an experiment"], ["explore", "Explore the pitfalls"]];

export default function App() {
  const [tab, setTab] = useState("analyze");
  const [profile, setProfile] = useState(null);
  const [methodId, setMethodId] = useState(null);
  const [config, setConfig] = useState({});
  const [out, setOut] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const resultRef = useRef(null);

  const onProfile = useCallback((p) => {
    setProfile(p);
    setOut(null);
    setError("");
    setMethodId(null);
  }, []);

  const choose = (id) => {
    setMethodId(id);
    setConfig(defaultConfig(id, profile));
    setOut(null);
    setError("");
  };

  const run = async () => {
    setRunning(true);
    setError("");
    try {
      const m = methodOf(methodId);
      setOut(await post(m.endpoint, buildRequest(methodId, config, profile)));
    } catch (e) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  };

  useEffect(() => {
    if (out) resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [out]);

  const step = !profile ? 1 : !methodId ? 2 : !out ? 3 : 4;
  return (
    <div className="shell">
      <header className="top">
        <div className="brand">
          <h1>Experiment <span>Lab</span></h1>
          <p>Upload experiment data, choose a method, and get a plain-English answer with the evidence behind it.</p>
        </div>
        <nav className="tabs" role="tablist" style={{ marginBottom: 0, borderBottom: 0 }}>
          {TABS.map(([id, label]) => (
            <button key={id} role="tab" className="tab" aria-selected={tab === id} onClick={() => setTab(id)}>{label}</button>
          ))}
        </nav>
      </header>
      <hr style={{ border: 0, borderTop: "2px solid var(--ink)", margin: "0 0 24px" }} />

      {tab === "analyze" && (
        <>
          <div className="steps" aria-label="Progress">
            {["Data", "Method", "Settings", "Answer"].map((s, i) => (
              <div key={s} className={`step ${step === i + 1 ? "active" : step > i + 1 ? "done" : ""}`}><b>{i + 1}</b>{s}</div>
            ))}
          </div>
          <div className="layout">
            <div>
              <DataStep profile={profile} onProfile={onProfile} />
              {profile && <div style={{ marginTop: 18 }}><MethodPicker profile={profile} value={methodId} onChange={choose} /></div>}
            </div>
            <div>
              {!profile && (
                <div className="card">
                  <h2>How this works</h2>
                  <ul className="plain" style={{ marginTop: 8 }}>
                    <li><b>Randomised test?</b> Compare variants, peek safely, or ask for the probability that B beats A.</li>
                    <li><b>No randomisation?</b> Use matching, difference-in-differences or synthetic control, with assumptions spelled out.</li>
                    <li>Every result states the effect size, the uncertainty, and what the data can and cannot tell you.</li>
                  </ul>
                </div>
              )}
              {profile && methodId && (
                <MethodForm profile={profile} methodId={methodId} config={config} onConfig={setConfig} onRun={run} running={running} error={error} />
              )}
              {profile && !methodId && <div className="card"><h2>Next: choose a method</h2><p className="sub">Pick the question you want answered from the list on the left.</p></div>}
              <div ref={resultRef} style={{ marginTop: out ? 18 : 0 }}>{out && <Suspense fallback={<Loading />}><ResultView out={out} config={config} /></Suspense>}</div>
            </div>
          </div>
        </>
      )}
      {tab === "plan" && <Suspense fallback={<Loading />}><Planner /></Suspense>}
      {tab === "explore" && <Suspense fallback={<Loading />}><Explore /></Suspense>}
    </div>
  );
}
