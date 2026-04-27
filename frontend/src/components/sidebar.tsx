"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  FileText,
  HeartPulse,
  Settings,
  ShieldAlert,
  Sparkles,
  UsersRound,
  UserCog,
  Video,
  ClipboardList,
  Users,
  KeyRound,
  Stethoscope,
  Phone,
  PhoneOutgoing,
  GitBranch,
  GitFork,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { hasPermission, hasRole, ROLE_LABEL } from "@/lib/permissions";
import type { AuthUser } from "@/lib/auth";

// ═══════════════════════════════════════════════════════════════
// Sidebar fixa — navegação clínica + perfil do usuário no rodapé.
// Items filtrados por role/permission. Estrutura preparada para
// substituir por GET /api/ui/config dinâmico (Bloco C v2).
// ═══════════════════════════════════════════════════════════════

type NavItem = {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  /** Mostra apenas se o user tem QUALQUER UMA dessas permissions. */
  permissions?: string[];
  /** Mostra apenas se o user tem QUALQUER UM desses roles. */
  roles?: AuthUser["role"][];
  badge?: number | string;
  group?: "main" | "admin";
};

const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Dashboard", icon: Activity },
  { href: "/alertas", label: "Alertas", icon: ShieldAlert, permissions: ["alerts:read"] },
  { href: "/alertas/clinicos", label: "Alertas Clínicos", icon: ShieldAlert, permissions: ["alerts:read"] },
  { href: "/reports", label: "Relatos", icon: FileText, permissions: ["reports:read"] },
  { href: "/patients", label: "Pacientes", icon: UsersRound, permissions: ["patients:read"] },
  { href: "/teleconsulta", label: "Teleconsulta", icon: Video, permissions: ["teleconsulta:read"] },
  { href: "/sofia", label: "Sofia Chat", icon: Sparkles },
  { href: "/comunicacao", label: "Comunicação", icon: Phone },
  { href: "/equipe", label: "Equipe", icon: UserCog, permissions: ["caregivers:read"] },
  // Admin section
  {
    href: "/admin/usuarios",
    label: "Usuários",
    icon: Users,
    permissions: ["users:read"],
    group: "admin",
  },
  {
    href: "/admin/perfis",
    label: "Papéis & Permissões",
    icon: KeyRound,
    permissions: ["profiles:read"],
    group: "admin",
  },
  {
    href: "/admin/regras-clinicas",
    label: "Regras Clínicas",
    icon: Stethoscope,
    roles: ["super_admin", "admin_tenant"],
    group: "admin",
  },
  {
    href: "/admin/regras-clinicas/cascadas",
    label: "Cascatas",
    icon: GitFork,
    roles: ["super_admin", "admin_tenant", "medico", "enfermeiro"],
    group: "admin",
  },
  {
    href: "/admin/cenarios-sofia",
    label: "Cenários Sofia",
    icon: Phone,
    roles: ["super_admin", "admin_tenant"],
    group: "admin",
  },
  {
    href: "/admin/cenarios-sofia/versoes",
    label: "Versões de Prompts",
    icon: GitBranch,
    roles: ["super_admin", "admin_tenant"],
    group: "admin",
  },
  {
    href: "/admin/seguranca/fila-revisao",
    label: "Fila de Revisão",
    icon: ShieldAlert,
    roles: ["super_admin", "admin_tenant", "medico", "enfermeiro", "cuidador_pro", "familia"],
    group: "admin",
  },
  {
    href: "/admin/seguranca/risk-score",
    label: "Risk Score",
    icon: Activity,
    roles: ["super_admin", "admin_tenant", "medico", "enfermeiro"],
    group: "admin",
  },
  {
    href: "/admin/proactive-caller",
    label: "Proactive Caller",
    icon: PhoneOutgoing,
    roles: ["super_admin", "admin_tenant", "medico", "enfermeiro"],
    group: "admin",
  },
  // /admin/auditoria — desabilitado até página ser criada
  // (prefetch do Next.js gerava 404 no console)
  // {
  //   href: "/admin/auditoria",
  //   label: "Auditoria",
  //   icon: ClipboardList,
  //   permissions: ["audit:read"],
  //   group: "admin",
  // },
  // Settings (todos têm acesso ao próprio settings)
  { href: "/configuracoes", label: "Configurações", icon: Settings, group: "admin" },
];

function visibleItems(user: AuthUser | null, group: "main" | "admin"): NavItem[] {
  return NAV_ITEMS.filter((item) => {
    const itemGroup = item.group || "main";
    if (itemGroup !== group) return false;
    if (item.roles && !hasRole(user, ...item.roles)) return false;
    if (item.permissions && item.permissions.length > 0) {
      return item.permissions.some((p) => hasPermission(user, p));
    }
    return true;
  });
}

export function Sidebar() {
  const pathname = usePathname();
  const { user } = useAuth();

  const mainItems = visibleItems(user, "main");
  const adminItems = visibleItems(user, "admin");

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
        <NavGroup items={mainItems} pathname={pathname} />
        {adminItems.length > 0 && (
          <>
            <div className="mt-5 mb-2 px-3 text-[9px] uppercase tracking-[0.18em] text-muted-foreground/60">
              Administração
            </div>
            <NavGroup items={adminItems} pathname={pathname} />
          </>
        )}
      </nav>

      <UserFooter />
    </aside>
  );
}

function NavGroup({ items, pathname }: { items: NavItem[]; pathname: string }) {
  return (
    <ul className="space-y-0.5">
      {items.map((item) => {
        const Icon = item.icon;
        // Longest-prefix-wins: /alertas não fica ativo quando estamos em
        // /alertas/clinicos (que é um item próprio).
        const isPrefix =
          pathname === item.href || pathname.startsWith(item.href + "/");
        const hasMoreSpecific = items.some(
          (other) =>
            other.href !== item.href &&
            other.href.startsWith(item.href + "/") &&
            (pathname === other.href ||
              pathname.startsWith(other.href + "/")),
        );
        const active =
          item.href === "/" ? pathname === "/" : isPrefix && !hasMoreSpecific;
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
  );
}

function UserFooter() {
  const { user } = useAuth();

  if (!user) {
    return (
      <div className="border-t border-white/[0.04] p-3">
        <Link
          href="/login"
          className="block text-center text-xs text-muted-foreground hover:text-foreground py-2"
        >
          Entrar
        </Link>
      </div>
    );
  }

  const initials = (user.fullName || user.email)
    .split(" ")
    .map((p) => p[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
  const subtitle = ROLE_LABEL[user.role] || user.role;
  const credential = user.crmRegister || user.corenRegister || user.partnerOrg || null;

  return (
    <div className="border-t border-white/[0.04] p-3">
      <Link
        href="/perfil"
        className="flex items-center gap-3 px-2 py-2 rounded-lg hover:bg-white/[0.03] transition-colors group"
      >
        <div className="relative flex-shrink-0">
          {user.avatarUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={user.avatarUrl}
              alt={user.fullName}
              className="w-9 h-9 rounded-full object-cover border border-white/10"
            />
          ) : (
            <div className="w-9 h-9 rounded-full bg-gradient-to-br from-accent-cyan/30 to-accent-teal/30 border border-white/10 flex items-center justify-center text-xs font-bold">
              {initials || "?"}
            </div>
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-xs font-medium text-foreground truncate">
            {user.fullName}
          </div>
          <div className="text-[10px] text-muted-foreground truncate mt-0.5">
            {credential ? `${subtitle} · ${credential}` : subtitle}
          </div>
        </div>
      </Link>
    </div>
  );
}
