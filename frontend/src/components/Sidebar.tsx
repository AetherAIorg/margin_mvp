"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navGroups = [
  {
    label: "Explore",
    links: [
      { href: "/search", label: "Search" },
      { href: "/metrics", label: "Repositories" },
      { href: "/functions", label: "Functions" },
      { href: "/discovery", label: "Candidates" },
    ],
  },
  {
    label: "Governance",
    links: [
      { href: "/issues", label: "Issues" },
      { href: "/upload", label: "Push sources" },
    ],
  },
  {
    label: "Run",
    links: [{ href: "/apply", label: "Pull & run" }],
  },
];

export function Sidebar() {
  const pathname = usePathname();

  function isActive(href: string) {
    if (href === "/metrics") return pathname === "/metrics" || pathname.startsWith("/metrics/");
    return pathname.startsWith(href);
  }

  return (
    <aside className="sidebar">
      <div className="brand">
        <strong>Margin Registry</strong>
        <span>Investment metrics</span>
      </div>
      {navGroups.map((group) => (
        <div key={group.label} className="nav-group">
          <div className="nav-group-label">{group.label}</div>
          <nav>
            {group.links.map((l) => (
              <Link key={l.href} href={l.href} className={isActive(l.href) ? "active" : ""}>
                {l.label}
              </Link>
            ))}
          </nav>
        </div>
      ))}
      {process.env.NEXT_PUBLIC_CATALOG_URL && (
        <div className="nav-group">
          <div className="nav-group-label">Catalog</div>
          <nav>
            <a href={process.env.NEXT_PUBLIC_CATALOG_URL} target="_blank" rel="noreferrer">
              Margin Catalog
            </a>
          </nav>
        </div>
      )}
    </aside>
  );
}
