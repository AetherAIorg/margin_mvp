"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/search", label: "Search" },
  { href: "/upload", label: "Upload" },
  { href: "/discovery", label: "Discovery" },
  { href: "/metrics", label: "Metric Registry" },
  { href: "/functions", label: "Function Registry" },
  { href: "/apply", label: "Apply Metric" },
  { href: "/issues", label: "Issues" },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="sidebar">
      <div className="brand">
        <strong>MetricGraph</strong>
        <span>Glean for financial metrics</span>
      </div>
      <nav>
        {links.map((l) => (
          <Link key={l.href} href={l.href} className={pathname.startsWith(l.href) ? "active" : ""}>
            {l.label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
