"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

export default function DiscoveryPage() {
  const [summary, setSummary] = useState<any>(null);
  const [selected, setSelected] = useState<any>(null);
  const [issues, setIssues] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.discoverySummary(), api.issues()])
      .then(([s, i]) => { setSummary(s); setIssues(i); })
      .catch((e) => setError(e.message));
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
      <header className="page-header">
        <p className="eyebrow">Financial Formula Index</p>
        <h1>Discovery Dashboard</h1>
      </header>

      {error && <p className="error">{error}</p>}

      {summary && (
        <>
          <div className="panel" style={{ marginBottom: "1rem" }}>
            <strong>
              Discovered {summary.total_candidates} metric candidates across {summary.total_artifacts} artifacts
            </strong>
          </div>
          <div className="grid grid-3" style={{ marginBottom: "1.5rem" }}>
            <div className="panel stat-card"><strong>{summary.total_artifacts}</strong><span>Artifacts scanned</span></div>
            <div className="panel stat-card"><strong>{summary.total_implementations}</strong><span>Formula implementations</span></div>
            <div className="panel stat-card"><strong>{summary.total_candidates}</strong><span>Metric candidates</span></div>
            <div className="panel stat-card"><strong>{summary.high_confidence_metrics}</strong><span>High-confidence metrics</span></div>
            <div className="panel stat-card"><strong>{summary.formula_clusters}</strong><span>Formula clusters</span></div>
            <div className="panel stat-card"><strong>{issueTotal}</strong><span>Issues detected</span></div>
          </div>
        </>
      )}

      {irrFamily && (
        <div className="panel" style={{ marginBottom: "1rem" }}>
          <h2>IRR cluster</h2>
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
          <h2>All families</h2>
          <div className="grid grid-2">
            {summary.families.map((f: any) => (
              <div className="card" key={f.family}>
                <span className="pill">{f.family}</span>
                <h3>{f.candidate_count} candidates</h3>
                <p className="muted">{f.implementation_count} implementations</p>
              </div>
            ))}
          </div>
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
              <button className="btn btn-secondary" onClick={() => setSelected(null)}>Close</button>
            </header>
            {selected.has_conflict && (
              <div className="pill pill-warning" style={{ marginBottom: "1rem", padding: "0.5rem" }}>
                Conflicting definitions detected
              </div>
            )}
            <div className="list">
              {selected.implementations?.map((impl: any) => (
                <div className="card" key={impl.id}>
                  <span className="pill">{impl.artifact_filename}</span>
                  {impl.is_deprecated && <span className="pill pill-warning">deprecated</span>}
                  <h3>{impl.extracted_name}</h3>
                  <p className="muted">{impl.location} · {impl.owner || "no owner"}</p>
                  <pre>{impl.raw_formula}</pre>
                  {impl.dimensions && (
                    <p className="muted">
                      Time basis: {impl.dimensions.time_basis} · Fees: {impl.dimensions.fees} · NAV: {impl.dimensions.nav_treatment}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
