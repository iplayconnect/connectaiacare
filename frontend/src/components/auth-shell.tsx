"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { Sidebar } from "@/components/sidebar";
import { TopBar } from "@/components/top-bar";
import { useAuth } from "@/context/auth-context";

/**
 * Shell que decide se renderiza Sidebar+TopBar ou só o conteúdo.
 *
 * Páginas "chrome-less" (sem layout do CRM): /login, /cadastro/*, /pitch,
 * /planos, /demo/*, /meu/* (portal paciente), /consulta/* (sala teleconsulta).
 * Em todas as outras o user tem que estar autenticado (middleware bloqueia).
 *
 * Faz também a hidratação inicial: chama /api/auth/me se houver token,
 * pra detectar sessão expirada e devolver o user mais atualizado.
 */

const CHROMELESS_PREFIXES = [
  "/login",
  "/forgot-password",
  "/reset-password",
  "/cadastro",
  "/pitch",
  "/planos",
  "/demo",
  "/meu",
  "/consulta",
];

function isChromeless(pathname: string): boolean {
  return CHROMELESS_PREFIXES.some((p) => pathname.startsWith(p));
}

export function AuthShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { hydrated, user, refresh } = useAuth();
  const chromeless = isChromeless(pathname);

  // Refresh dos dados do user no boot (caso o JWT esteja stale).
  useEffect(() => {
    if (hydrated && user) {
      refresh();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hydrated]);

  if (chromeless) {
    return <>{children}</>;
  }

  return (
    <>
      <Sidebar />
      <TopBar />
      <main className="pl-60 pt-14 relative z-10">
        <div className="px-8 py-6 min-h-[calc(100vh-3.5rem)] animate-fade-up">
          {children}
        </div>
      </main>
    </>
  );
}
