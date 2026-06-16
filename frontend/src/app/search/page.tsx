"use client";

import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

export default function SearchPage() {
  const [query, setQuery] = useState("net irr");
  const [results, setResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  async function search(q?: string) {
    setLoading(true);
    try {
      const res = await api.search(q ?? query);
      setResults(res.results || []);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <header className="page-header">
        <p className="eyebrow">Universal search</p>
        <h1>Search metrics, functions, and formulas</h1>
      </header>

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem" }}>
        <input
          className="search-input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void search()}
          placeholder="Search: net IRR, compute_xirr, fund_cashflows..."
        />
        <button className="btn" onClick={() => void search()} disabled={loading}>Search</button>
      </div>

      <div className="list">
        {results.map((r) => (
          <Link key={`${r.type}-${r.id}`} href={r.href.startsWith("/") ? r.href : `/metrics/${r.id}`} className="card">
            <span className="pill">{r.type}</span>
            <h3>{r.title}</h3>
            <p className="muted">{r.subtitle}</p>
            <p>{r.snippet}</p>
          </Link>
        ))}
        {!results.length && !loading && <p className="muted">Enter a query to search the metric index.</p>}
      </div>
    </div>
  );
}
