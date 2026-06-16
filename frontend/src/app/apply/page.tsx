"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function ApplyPage() {
  const [metrics, setMetrics] = useState<any[]>([]);
  const [datasets, setDatasets] = useState<any[]>([]);
  const [selectedMetric, setSelectedMetric] = useState("");
  const [selectedDataset, setSelectedDataset] = useState("");
  const [selectedNav, setSelectedNav] = useState("");
  const [run, setRun] = useState<any>(null);
  const [results, setResults] = useState<any>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    Promise.all([api.metrics(), api.datasets()]).then(([m, d]) => {
      setMetrics(m);
      setDatasets(d);
      const approved = m.find((x: any) => x.status === "approved");
      if (approved) setSelectedMetric(approved.id);
    });
  }, []);

  async function uploadDataset(file: File) {
    const ds = await api.uploadDataset(file);
    setDatasets((prev) => [ds, ...prev]);
    if (file.name.includes("cashflow")) setSelectedDataset(ds.id);
    if (file.name.includes("nav")) setSelectedNav(ds.id);
  }

  async function runMetric() {
    if (!selectedMetric || !selectedDataset) return;
    setRunning(true);
    try {
      const r = await api.runMetric(selectedMetric, selectedDataset, selectedNav || undefined);
      setRun(r);
      const res = await api.runResults(r.id);
      setResults(res);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div>
      <header className="page-header">
        <p className="eyebrow">Metric application engine</p>
        <h1>Apply Metric to Raw Data</h1>
      </header>

      <div className="panel" style={{ marginBottom: "1rem" }}>
        <h2>Upload datasets</h2>
        <label className="btn btn-secondary">
          Upload CSV
          <input type="file" accept=".csv" hidden onChange={(e) => e.target.files?.[0] && void uploadDataset(e.target.files[0])} />
        </label>
      </div>

      <div className="grid grid-2">
        <div className="panel">
          <label>Metric</label>
          <select
            value={selectedMetric}
            onChange={(e) => setSelectedMetric(e.target.value)}
            style={{ width: "100%", padding: "0.5rem", marginTop: "0.5rem" }}
          >
            {metrics.map((m) => (
              <option key={m.id} value={m.id}>{m.canonical_name} ({m.status})</option>
            ))}
          </select>
        </div>
        <div className="panel">
          <label>Cashflow dataset</label>
          <select
            value={selectedDataset}
            onChange={(e) => setSelectedDataset(e.target.value)}
            style={{ width: "100%", padding: "0.5rem", marginTop: "0.5rem" }}
          >
            <option value="">Select…</option>
            {datasets.map((d) => (
              <option key={d.id} value={d.id}>{d.filename} ({d.row_count} rows)</option>
            ))}
          </select>
        </div>
        <div className="panel">
          <label>NAV dataset (optional)</label>
          <select
            value={selectedNav}
            onChange={(e) => setSelectedNav(e.target.value)}
            style={{ width: "100%", padding: "0.5rem", marginTop: "0.5rem" }}
          >
            <option value="">None</option>
            {datasets.map((d) => (
              <option key={d.id} value={d.id}>{d.filename}</option>
            ))}
          </select>
        </div>
      </div>

      <button className="btn" style={{ marginTop: "1rem" }} onClick={() => void runMetric()} disabled={running || !selectedMetric || !selectedDataset}>
        {running ? "Running…" : "Run metric"}
      </button>

      {run && (
        <div className="panel" style={{ marginTop: "1.5rem" }}>
          <h2>Run status: {run.status}</h2>
          {run.warnings?.length > 0 && (
            <div>
              <h3>Warnings</h3>
              <ul>{run.warnings.map((w: string, i: number) => <li key={i}>{w}</li>)}</ul>
            </div>
          )}
          {run.errors?.length > 0 && (
            <div className="error">
              <h3>Errors</h3>
              <ul>{run.errors.map((e: string, i: number) => <li key={i}>{e}</li>)}</ul>
            </div>
          )}
        </div>
      )}

      {results && (
        <div className="panel" style={{ marginTop: "1rem" }}>
          <h2>Results</h2>
          {results.results?.length > 0 ? (
            <table>
              <thead>
                <tr>{Object.keys(results.results[0]).map((k) => <th key={k}>{k}</th>)}</tr>
              </thead>
              <tbody>
                {results.results.map((row: any, i: number) => (
                  <tr key={i}>{Object.values(row).map((v, j) => <td key={j}>{String(v)}</td>)}</tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="muted">No results</p>
          )}
          <h3>Audit trail</h3>
          <pre>{JSON.stringify(results.audit_log, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}
