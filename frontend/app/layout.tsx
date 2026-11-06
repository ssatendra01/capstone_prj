import type { Metadata } from "next";
import "./globals.scss";

export const metadata: Metadata = {
  title: "Clearview Complaints - Monitoring Workbench",
  description: "Agentic complaints management with human-in-the-loop governance",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
