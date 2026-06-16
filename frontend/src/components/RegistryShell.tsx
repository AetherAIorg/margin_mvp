"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ReactNode, useState } from "react";

interface RegistryShellProps {
  children: ReactNode;
  breadcrumbs?: { label: string; href?: string }[];
}

export function RegistryShell({ children, breadcrumbs }: RegistryShellProps) {
  const router = useRouter();
  const [q, setQ] = useState("");

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (q.trim()) router.push(`/search?q=${encodeURIComponent(q.trim())}`);
  }

  return (
    <div className="registry-shell">
      <header className="registry-topbar">
        <form className="registry-topbar-search" onSubmit={handleSearch}>
          <input
            type="search"
            placeholder="Search repositories, tags, functions…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </form>
        {breadcrumbs && breadcrumbs.length > 0 && (
          <nav className="breadcrumbs" aria-label="Breadcrumb">
            {breadcrumbs.map((crumb, i) => (
              <span key={i} style={{ display: "contents" }}>
                {i > 0 && <span className="breadcrumbs-sep">/</span>}
                {crumb.href ? (
                  <Link href={crumb.href}>{crumb.label}</Link>
                ) : (
                  <span>{crumb.label}</span>
                )}
              </span>
            ))}
          </nav>
        )}
      </header>
      <div className="registry-content">{children}</div>
    </div>
  );
}
