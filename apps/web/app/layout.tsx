import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FCCS | Validation & Audit",
  description: "Traceable financial validation, evidence and close review",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
