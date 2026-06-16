import "./globals.css";
import { Sidebar } from "@/components/Sidebar";

export const metadata = {
  title: "MetricGraph",
  description: "Glean for financial metrics",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="app-shell">
          <Sidebar />
          <main className="main">{children}</main>
        </div>
      </body>
    </html>
  );
}
