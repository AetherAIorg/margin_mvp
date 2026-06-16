"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { FunctionDef } from "@/lib/types";
import { Breadcrumbs } from "@/components/Breadcrumbs";

export default function FunctionsPage() {
  const [functions, setFunctions] = useState<FunctionDef[]>([]);

  useEffect(() => {
    api.functions().then(setFunctions).catch(console.error);
  }, []);

  const calcs = functions.filter((f) => f.function_type === "financial_calculation");
  const transforms = functions.filter((f) => f.function_type === "transformation");

  return (
    <div>
      <Breadcrumbs items={[{ label: "Functions" }]} />
      <header className="page-header">
        <p className="eyebrow">Function registry</p>
        <h1>Functions</h1>
        <p className="muted">Reusable calculation and transformation functions referenced by metric manifests.</p>
      </header>

      <div className="panel" style={{ marginBottom: "1rem" }}>
        <h2 style={{ marginTop: 0 }}>Financial calculations</h2>
        <table className="registry-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Version</th>
              <th>Status</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            {calcs.map((f) => (
              <tr key={f.id}>
                <td className="tag-name">{f.name}</td>
                <td>{f.version}</td>
                <td><span className="pill pill-success">{f.status}</span></td>
                <td className="muted">{f.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <h2 style={{ marginTop: 0 }}>Transformations</h2>
        <table className="registry-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Version</th>
              <th>Type</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            {transforms.map((f) => (
              <tr key={f.id}>
                <td className="tag-name">{f.name}</td>
                <td>{f.version}</td>
                <td><span className="pill">{f.function_type}</span></td>
                <td className="muted">{f.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
