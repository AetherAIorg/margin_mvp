"use client";

import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { SearchResult } from "@/lib/types";
import { Breadcrumbs } from "@/components/Breadcrumbs";

export default function SearchPage() {
  const [query, setQuery] = useState("net irr");
  const [results, setResults] = useState<SearchResult[]>([]);
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

  const grouped = results.reduce<Record<string, SearchResult[]>>((acc, r) => {
    acc[r.type] = acc[r.type] || [];
    acc[r.type].push(r);
    return acc;
  }, {});

  return (
    <div>
      <Breadcrumbs items={[{ label: "Search" }]} />
      <header className="page-header">
        <p className="eyebrow">Universal search</p>
        <h1>Search</h1>
        <p className="muted">Repositories, tags, functions, and indexed formulas.</p>
      </header>

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem" }}>
        <input
          className="search-input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void search()}
          placeholder="Search: net IRR, compute_xirr, fund_cashflows…"
        />
        <button type="button" className="btn" onClick={() => void search()} disabled={loading}>Search</button>
      </div>

      {Object.entries(grouped).map(([type, items]) => (
        <div key={type} className="panel" style={{ marginBottom: "1rem" }}>
          <h2 style={{ marginTop: 0, fontSize: "1rem", textTransform: "capitalize" }}>{type}</h2>
          <table className="registry-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Details</th>
                <th>Snippet</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr key={`${r.type}-${r.id}`}>
                  <td>
                    <Link href={r.href.startsWith("/") ? r.href : `/metrics/${r.id}`} className="tag-name">
                      {r.title}
                    </Link>
                  </td>
                  <td className="muted">{r.subtitle}</td>
                  <td>{r.snippet}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      {!results.length && !loading && <p className="muted">Enter a query to search the registry index.</p>}
    </div>
  );
}
