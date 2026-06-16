"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Breadcrumbs } from "@/components/Breadcrumbs";

export default function DiscoveryPage() {
  const [summary, setSummary] = useState<any>(null);
  const [selected, setSelected] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.discoverySummary().then(setSummary).catch((e) => setError(e.message));
  }, []);

  async function openCandidate(id: string) {
    const detail = await api.discoveryCandidate(id);
    setSelected(detail);
  }

  const irrFamily = summary?.families?.find((f: any) => f.family === "IRR");
  const issueTotal = Object.values(summary?.issue_counts ?? {}).reduce(
    (a: number, b) => a + Number(b),
    0
  );

  return (
    <div>
      <Breadcrumbs items={[{ label: "Candidates" }]} />
      <header className="page-header">
        <p className="eyebrow">Pre-registry discovery</p>
        <h1>Metric candidates</h1>
        <p className="muted">Discovered formulas before they become published repository tags.</p>
      </header>

      {error && <p className="error">{error}</p>}

      {summary && (
        <>
          <div className="panel" style={{ marginBottom: "1rem" }}>
            <strong>
              {summary.total_candidates} candidates across {summary.total_artifacts} source artifacts
            </strong>
          </div>
          <div className="grid grid-3" style={{ marginBottom: "1.5rem" }}>
            <div className="panel stat-card"><strong>{summary.total_artifacts}</strong><span>Sources scanned</span></div>
            <div className="panel stat-card"><strong>{summary.total_implementations}</strong><span>Implementations</span></div>
            <div className="panel stat-card"><strong>{summary.total_candidates}</strong><span>Candidates</span></div>
            <div className="panel stat-card"><strong>{summary.high_confidence_metrics}</strong><span>High confidence</span></div>
            <div className="panel stat-card"><strong>{summary.formula_clusters}</strong><span>Clusters</span></div>
            <div className="panel stat-card"><strong>{issueTotal}</strong><span>Issues</span></div>
          </div>
        </>
      )}

      {irrFamily && (
        <div className="panel" style={{ marginBottom: "1rem" }}>
          <h2 style={{ marginTop: 0 }}>IRR cluster</h2>
          <div className="grid grid-2">
            {irrFamily.candidates.map((c: any) => (
              <button key={c.id} className="card" onClick={() => void openCandidate(c.id)} style={{ textAlign: "left", cursor: "pointer" }}>
                <h3>{c.display_name}</h3>
                <p className="muted">{c.implementation_count} implementations</p>
                {c.has_conflict && <span className="pill pill-warning">conflict</span>}
              </button>
            ))}
          </div>
        </div>
      )}

      {summary?.families && (
        <div className="panel">
          <h2 style={{ marginTop: 0 }}>All families</h2>
          <table className="registry-table">
            <thead>
              <tr>
                <th>Family</th>
                <th>Candidates</th>
                <th>Implementations</th>
              </tr>
            </thead>
            <tbody>
              {summary.families.map((f: any) => (
                <tr key={f.family}>
                  <td><span className="pill">{f.family}</span></td>
                  <td>{f.candidate_count}</td>
                  <td>{f.implementation_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted" style={{ marginTop: "1rem" }}>
            Ready to publish? <Link href="/metrics">Browse repositories</Link> or approve a candidate as a canonical metric.
          </p>
        </div>
      )}

      {selected && (
        <div className="modal-backdrop" onClick={() => setSelected(null)}>
          <div className="modal panel" onClick={(e) => e.stopPropagation()}>
            <header style={{ display: "flex", justifyContent: "space-between", marginBottom: "1rem" }}>
              <div>
                <p className="eyebrow">{selected.family}</p>
                <h2>{selected.display_name}</h2>
                <p className="muted">{selected.implementation_count} implementations · {selected.signature_count} signatures</p>
              </div>
              <button type="button" className="btn btn-secondary" onClick={() => setSelected(null)}>Close</button>
            </header>
            <div className="list">
              {selected.implementations?.map((impl: any) => (
                <div className="card" key={impl.id}>
                  <span className="pill">{impl.artifact_filename}</span>
                  {impl.is_deprecated && <span className="pill pill-warning">deprecated</span>}
                  <h3>{impl.extracted_name}</h3>
                  <p className="muted">{impl.location} · {impl.owner || "no owner"}</p>
                  <pre>{impl.raw_formula}</pre>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
