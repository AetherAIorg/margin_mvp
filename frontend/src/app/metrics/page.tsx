"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { Metric } from "@/lib/types";
import { RepoCard } from "@/components/RepoCard";
import { Breadcrumbs } from "@/components/Breadcrumbs";

export default function MetricsPage() {
  const [metrics, setMetrics] = useState<Metric[]>([]);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [sort, setSort] = useState<"name" | "tags" | "updated">("name");

  useEffect(() => {
    api.metrics().then(setMetrics).catch(console.error);
  }, []);

  const filtered = useMemo(() => {
    let list = [...metrics];
    if (query) {
      const q = query.toLowerCase();
      list = list.filter(
        (m) =>
          m.canonical_name.toLowerCase().includes(q) ||
          m.domain.toLowerCase().includes(q) ||
          (m.owner ?? "").toLowerCase().includes(q)
      );
    }
    if (statusFilter) list = list.filter((m) => m.status === statusFilter);
    list.sort((a, b) => {
      if (sort === "tags") return b.tag_count - a.tag_count;
      if (sort === "updated") {
        const ta = a.updated_at ? new Date(a.updated_at).getTime() : 0;
        const tb = b.updated_at ? new Date(b.updated_at).getTime() : 0;
        return tb - ta;
      }
      return a.canonical_name.localeCompare(b.canonical_name);
    });
    return list;
  }, [metrics, query, statusFilter, sort]);

  return (
    <div>
      <Breadcrumbs items={[{ label: "Repositories" }]} />
      <header className="page-header">
        <p className="eyebrow">Metric registry</p>
        <h1>Repositories</h1>
        <p className="muted">Browse canonical metric repositories, tags, and immutable manifests.</p>
      </header>

      <div className="filter-bar">
        <input
          placeholder="Filter by name, domain, owner…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">All statuses</option>
          <option value="approved">Approved</option>
          <option value="candidate">Candidate</option>
        </select>
        <select value={sort} onChange={(e) => setSort(e.target.value as typeof sort)}>
          <option value="name">Sort: name</option>
          <option value="tags">Sort: tag count</option>
          <option value="updated">Sort: last updated</option>
        </select>
      </div>

      <div className="repo-grid">
        {filtered.map((m) => (
          <RepoCard key={m.id} metric={m} />
        ))}
      </div>
      {!filtered.length && <p className="muted">No repositories match your filters.</p>}
    </div>
  );
}
