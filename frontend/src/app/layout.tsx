import type { Metadata } from "next";
import "./globals.css";
import { Header } from "@/components/header";

export const metadata: Metadata = {
  title: "ConnectaIACare — Cuidado Integrado com IA",
  description:
    "Plataforma de cuidado integrado com IA para idosos e pacientes crônicos. Relato via WhatsApp, análise clínica contextual, alerta proativo à equipe médica.",
  themeColor: "#050b1f",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" className="dark">
      <body className="min-h-screen text-foreground antialiased">
        <Header />
        <main className="container py-8">
          <div className="animate-fade-up">{children}</div>
        </main>
      </body>
    </html>
  );
}
