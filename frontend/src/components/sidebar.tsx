"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  FileText,
  HeartPulse,
  Settings,
  Sparkles,
  UsersRound,
  UserCog,
  Video,
} from "lucide-react";

// ═══════════════════════════════════════════════════════════════
// Sidebar fixa — navegação clínica + profile médico no rodapé
// Inspiração: Linear + Cerner (estrutura hospitalar séria)
// ═══════════════════════════════════════════════════════════════

type NavItem = {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: number | string;
};

const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Dashboard", icon: Activity },
  { href: "/reports", label: "Relatos", icon: FileText },
  { href: "/patients", label: "Pacientes", icon: UsersRound },
  { href: "/teleconsulta", label: "Teleconsulta", icon: Video },
  { href: "/demo/onboarding", label: "Sofia ao vivo", icon: Sparkles },
  { href: "/equipe", label: "Equipe", icon: UserCog },
  { href: "/configuracoes", label: "Configurações", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed left-0 top-0 bottom-0 w-60 border-r border-white/[0.06] bg-[hsl(222,47%,7%)]/80 backdrop-blur-xl flex flex-col z-40">
      {/* Logo */}
      <Link
        href="/"
        className="flex items-center gap-3 px-5 py-5 border-b border-white/[0.04] group"
      >
        <div className="relative">
          <div className="accent-gradient p-2 rounded-lg shadow-glow-cyan transition-transform group-hover:scale-105">
            <HeartPulse
              className="h-4 w-4 text-slate-900"
              strokeWidth={2.5}
            />
          </div>
          <div className="absolute -inset-0.5 accent-gradient rounded-lg opacity-0 group-hover:opacity-30 blur transition-opacity" />
        </div>
        <div className="min-w-0">
          <div className="font-bold text-sm tracking-tight leading-tight truncate">
            <span className="accent-gradient-text">ConnectaIA</span>
            <span className="text-foreground">Care</span>
          </div>
          <div className="text-[10px] text-muted-foreground leading-tight uppercase tracking-[0.18em] mt-0.5">
            Cuidado Integrado · Íris
          </div>
        </div>
      </Link>

      {/* Navigation */}
      <nav className="flex-1 py-3 px-2 overflow-y-auto">
        <ul className="space-y-0.5">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);

            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={`
                    flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all
                    ${
                      active
                        ? "bg-accent-cyan/10 text-accent-cyan font-medium border border-accent-cyan/20"
                        : "text-muted-foreground hover:text-foreground hover:bg-white/[0.03] border border-transparent"
                    }
                  `}
                >
                  <Icon className="h-4 w-4 flex-shrink-0" />
                  <span className="flex-1">{item.label}</span>
                  {item.badge != null && (
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded-md font-medium tabular ${
                        active
                          ? "bg-accent-cyan/20 text-accent-cyan"
                          : "bg-white/[0.06] text-muted-foreground"
                      }`}
                    >
                      {item.badge}
                    </span>
                  )}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Profile médico fixo no rodapé */}
      <DoctorProfileFooter />
    </aside>
  );
}

function DoctorProfileFooter() {
  // Mock — em produção vem de auth/session
  const doctor = {
    name: "Dra. Ana Silva",
    crm: "CRM/RS 12345",
    specialty: "Geriatria",
    isDemo: true,
  };

  return (
    <div className="border-t border-white/[0.04] p-3">
      <Link
        href="/equipe"
        className="flex items-center gap-3 px-2 py-2 rounded-lg hover:bg-white/[0.03] transition-colors group"
      >
        <div className="relative flex-shrink-0">
          <div className="w-9 h-9 rounded-full bg-gradient-to-br from-accent-cyan/30 to-accent-teal/30 border border-white/10 flex items-center justify-center text-xs font-bold">
            AS
          </div>
          {doctor.isDemo && (
            <div
              className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-classification-attention border-2 border-background"
              title="Persona de demonstração"
            />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-xs font-medium text-foreground truncate flex items-center gap-1.5">
            {doctor.name}
            {doctor.isDemo && (
              <span className="text-[9px] uppercase tracking-wider bg-classification-attention/15 text-classification-attention px-1 py-0.5 rounded">
                demo
              </span>
            )}
          </div>
          <div className="text-[10px] text-muted-foreground truncate mt-0.5">
            {doctor.crm} · {doctor.specialty}
          </div>
        </div>
      </Link>
    </div>
  );
}
