import "./globals.css";
import { RegistryShell } from "@/components/RegistryShell";
import { Sidebar } from "@/components/Sidebar";

export const metadata = {
  title: "Margin Registry",
  description: "Docker Hub-style registry for investment metrics",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="app-shell">
          <Sidebar />
          <RegistryShell>{children}</RegistryShell>
        </div>
      </body>
    </html>
  );
}
