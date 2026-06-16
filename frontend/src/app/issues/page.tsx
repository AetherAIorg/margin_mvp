"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Breadcrumbs } from "@/components/Breadcrumbs";

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
      <Breadcrumbs items={[{ label: "Governance", href: "/issues" }, { label: "Issues" }]} />
      <header className="page-header">
        <p className="eyebrow">Governance</p>
        <h1>Issues</h1>
        <p className="muted">{issues.length} issues detected across indexed sources.</p>
      </header>

      {Object.entries(grouped).map(([type, items]) => (
        <div className="panel" key={type} style={{ marginBottom: "1rem" }}>
          <h2 style={{ marginTop: 0 }}>{ISSUE_LABELS[type] || type} ({items.length})</h2>
          <table className="registry-table">
            <thead>
              <tr>
                <th>Severity</th>
                <th>Title</th>
                <th>Explanation</th>
                <th>Affected</th>
              </tr>
            </thead>
            <tbody>
              {items.map((issue) => (
                <tr key={issue.id}>
                  <td>
                    <span className={`pill ${issue.severity === "high" ? "pill-danger" : "pill-warning"}`}>
                      {issue.severity}
                    </span>
                  </td>
                  <td>{issue.title}</td>
                  <td className="muted">{issue.explanation}</td>
                  <td className="muted">{issue.affected_artifacts?.join(", ") ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      {!issues.length && <p className="muted">No issues yet. Push sources to begin discovery.</p>}
    </div>
  );
}
