import type { Metadata } from "next";
import "./globals.css";
import { Header } from "@/components/header";

export const metadata: Metadata = {
  title: "ConnectaIACare — Cuidado Integrado",
  description: "Plataforma de cuidado com IA para idosos e pacientes crônicos.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body className="min-h-screen bg-slate-50">
        <Header />
        <main className="container py-6">{children}</main>
      </body>
    </html>
  );
}
