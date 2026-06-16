"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Dataset, Metric, MetricTag } from "@/lib/types";
import { Breadcrumbs } from "@/components/Breadcrumbs";
import { DigestChip } from "@/components/DigestChip";

export default function ApplyPageClient() {
  const searchParams = useSearchParams();
  const [metrics, setMetrics] = useState<Metric[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [tags, setTags] = useState<MetricTag[]>([]);
  const [selectedMetric, setSelectedMetric] = useState("");
  const [selectedTag, setSelectedTag] = useState("");
  const [selectedDataset, setSelectedDataset] = useState("");
  const [selectedNav, setSelectedNav] = useState("");
  const [run, setRun] = useState<any>(null);
  const [results, setResults] = useState<any>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    Promise.all([api.metrics(), api.datasets()]).then(([m, d]) => {
      setMetrics(m);
      setDatasets(d);
      const paramMetric = searchParams.get("metric");
      const paramTag = searchParams.get("tag");
      const approved = m.find((x) => x.status === "approved");
      const initial = paramMetric ?? approved?.id ?? "";
      if (initial) setSelectedMetric(initial);
      if (paramTag) setSelectedTag(paramTag);
    });
  }, [searchParams]);

  useEffect(() => {
    if (!selectedMetric) {
      setTags([]);
      return;
    }
    api.metricTags(selectedMetric).then((t) => {
      setTags(t.filter((x) => x.status === "published"));
      if (!selectedTag) {
        const latest = t.find((x) => x.tag === "latest") ?? t[0];
        if (latest) setSelectedTag(latest.tag);
      }
    }).catch(console.error);
  }, [selectedMetric, selectedTag]);

  const selectedTagRow = useMemo(
    () => tags.find((t) => t.tag === selectedTag),
    [tags, selectedTag]
  );

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
      const r = await api.runMetric(
        selectedMetric,
        selectedDataset,
        selectedNav || undefined,
        selectedTag || undefined
      );
      setRun(r);
      const res = await api.runResults(r.id);
      setResults(res);
    } finally {
      setRunning(false);
    }
  }

  const repo = metrics.find((m) => m.id === selectedMetric);

  return (
    <div>
      <Breadcrumbs items={[{ label: "Pull & run" }]} />
      <header className="page-header">
        <p className="eyebrow">Execution</p>
        <h1>Pull & run</h1>
        <p className="muted">Select a repository and tag to execute an immutable manifest against raw data.</p>
      </header>

      <div className="panel" style={{ marginBottom: "1rem" }}>
        <h2 style={{ marginTop: 0, fontSize: "1rem" }}>Upload datasets</h2>
        <label className="btn btn-secondary">
          Upload CSV
          <input type="file" accept=".csv" hidden onChange={(e) => e.target.files?.[0] && void uploadDataset(e.target.files[0])} />
        </label>
      </div>

      <div className="grid grid-2">
        <div className="panel">
          <label>Repository</label>
          <select
            value={selectedMetric}
            onChange={(e) => { setSelectedMetric(e.target.value); setSelectedTag(""); }}
            style={{ width: "100%", padding: "0.5rem", marginTop: "0.5rem" }}
          >
            <option value="">Select…</option>
            {metrics.map((m) => (
              <option key={m.id} value={m.id}>{m.canonical_name} ({m.status})</option>
            ))}
          </select>
          {repo && (
            <p className="muted" style={{ marginTop: "0.5rem", fontSize: "0.8125rem" }}>
              <Link href={`/metrics/${repo.id}`}>View repository</Link>
            </p>
          )}
        </div>
        <div className="panel">
          <label>Tag</label>
          <select
            value={selectedTag}
            onChange={(e) => setSelectedTag(e.target.value)}
            style={{ width: "100%", padding: "0.5rem", marginTop: "0.5rem" }}
            disabled={!tags.length}
          >
            <option value="">Select…</option>
            {tags.map((t) => (
              <option key={t.id} value={t.tag}>{t.tag}</option>
            ))}
          </select>
          {selectedTagRow && (
            <p style={{ marginTop: "0.5rem" }}>
              <DigestChip digest={selectedTagRow.digest} />
            </p>
          )}
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

      <button
        className="btn"
        style={{ marginTop: "1rem" }}
        onClick={() => void runMetric()}
        disabled={running || !selectedMetric || !selectedDataset}
      >
        {running ? "Running…" : "Pull & run"}
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
            <table className="registry-table">
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
