"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function FunctionsPage() {
  const [functions, setFunctions] = useState<any[]>([]);

  useEffect(() => {
    api.functions().then(setFunctions).catch(console.error);
  }, []);

  const calcs = functions.filter((f) => f.function_type === "financial_calculation");
  const transforms = functions.filter((f) => f.function_type === "transformation");

  return (
    <div>
      <header className="page-header">
        <p className="eyebrow">Function registry</p>
        <h1>Reusable Functions & Transformations</h1>
      </header>

      <div className="panel" style={{ marginBottom: "1rem" }}>
        <h2>Financial calculations</h2>
        <div className="list">
          {calcs.map((f) => (
            <div className="card" key={f.id}>
              <span className="pill pill-success">{f.status}</span>
              <h3>{f.name}</h3>
              <p>{f.description}</p>
              <pre>{JSON.stringify(f.input_schema, null, 2)}</pre>
            </div>
          ))}
        </div>
      </div>

      <div className="panel">
        <h2>Transformations</h2>
        <div className="list">
          {transforms.map((f) => (
            <div className="card" key={f.id}>
              <span className="pill">{f.function_type}</span>
              <h3>{f.name}</h3>
              <p>{f.description}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
