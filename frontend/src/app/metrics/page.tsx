"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

export default function MetricsPage() {
  const [metrics, setMetrics] = useState<any[]>([]);

  useEffect(() => {
    api.metrics().then(setMetrics).catch(console.error);
  }, []);

  return (
    <div>
      <header className="page-header">
        <p className="eyebrow">Metric registry</p>
        <h1>Canonical Metrics</h1>
        <p className="muted">Approved metric definitions with execution plans.</p>
      </header>

      <div className="list">
        {metrics.map((m) => (
          <Link key={m.id} href={`/metrics/${m.id}`} className="card">
            <span className={`pill ${m.status === "approved" ? "pill-success" : ""}`}>{m.status}</span>
            <h3>{m.canonical_name}</h3>
            <p className="muted">{m.domain} · {m.entity} · owner {m.owner || "none"}</p>
            <p>{m.description}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
