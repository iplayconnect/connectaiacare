import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/context/auth-context";
import { AuthShell } from "@/components/auth-shell";

export const metadata: Metadata = {
  title: "ConnectaIACare — Cuidado Integrado com IA",
  description:
    "Plataforma de cuidado integrado com IA para idosos e pacientes crônicos. Relato via WhatsApp, análise clínica contextual, alerta proativo à equipe médica.",
  themeColor: "#050b1f",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" className="dark">
      <body className="min-h-screen text-foreground antialiased bg-background">
        {/* Ambient background — sutil gradient pra profundidade */}
        <div
          aria-hidden
          className="fixed inset-0 pointer-events-none z-0"
          style={{
            background:
              "radial-gradient(1000px circle at 15% -10%, hsla(187,100%,40%,0.08), transparent 50%), radial-gradient(800px circle at 90% 20%, hsla(160,84%,39%,0.05), transparent 50%)",
          }}
        />

        <AuthProvider>
          <AuthShell>{children}</AuthShell>
        </AuthProvider>
      </body>
    </html>
  );
}
