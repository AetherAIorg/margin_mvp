"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const ISSUE_LABELS: Record<string, string> = {
  CONFLICTING_DEFINITION: "Conflicting definitions",
  CONFLICTING_TIME_BASIS: "Conflicting time basis",
  CONFLICTING_FEE_TREATMENT: "Conflicting fee treatment",
  GROSS_NET_MISMATCH: "Gross vs net mismatch",
  REALIZED_UNREALIZED_MISMATCH: "Realized vs unrealized mismatch",
  MISSING_OWNER: "Missing owner",
  MISSING_SOURCE_DOCUMENTATION: "Missing source documentation",
  DEPRECATED_FORMULA_REFERENCED: "Deprecated formula referenced",
  INCONSISTENT_ENTITY_GRAIN: "Inconsistent entity grain",
};

export default function IssuesPage() {
  const [issues, setIssues] = useState<any[]>([]);

  useEffect(() => {
    api.issues().then(setIssues).catch(console.error);
  }, []);

  const grouped: Record<string, any[]> = {};
  for (const issue of issues) {
    grouped[issue.issue_type] = grouped[issue.issue_type] || [];
    grouped[issue.issue_type].push(issue);
  }

  return (
    <div>
      <header className="page-header">
        <p className="eyebrow">Governance</p>
        <h1>Issue Dashboard</h1>
        <p className="muted">{issues.length} issues detected across indexed artifacts.</p>
      </header>

      {Object.entries(grouped).map(([type, items]) => (
        <div className="panel" key={type} style={{ marginBottom: "1rem" }}>
          <h2>{ISSUE_LABELS[type] || type} ({items.length})</h2>
          <div className="list">
            {items.map((issue) => (
              <div className="card" key={issue.id}>
                <span className={`pill ${issue.severity === "high" ? "pill-danger" : "pill-warning"}`}>{issue.severity}</span>
                <h3>{issue.title}</h3>
                <p>{issue.explanation}</p>
                {issue.affected_artifacts?.length > 0 && (
                  <p className="muted">Affected: {issue.affected_artifacts.join(", ")}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}

      {!issues.length && <p className="muted">No issues yet. Upload artifacts to begin discovery.</p>}
    </div>
  );
}
