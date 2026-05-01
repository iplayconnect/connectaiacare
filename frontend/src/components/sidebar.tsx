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
  ClipboardCheck,
  Users,
  KeyRound,
  Stethoscope,
  Phone,
  PhoneOutgoing,
  GitBranch,
  GitFork,
  Volume2,
  CalendarClock,
  Building2,
  HeartHandshake,
  ServerCog,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { hasPermission, hasRole, ROLE_LABEL } from "@/lib/permissions";
import type { AuthUser } from "@/lib/auth";

// ═══════════════════════════════════════════════════════════════
// Sidebar com 4 grupos:
//   main        — Operação (todos com permission)
//   tenant      — Administração do tenant (admin_tenant + super_admin)
//   governance  — Governança Clínica cross-tenant (multi-role
//                 conforme item — clinical_reviewer, medico, etc.)
//   system      — Sistema · Cross-tenant (SUPER_ADMIN ONLY)
//
// Decisão de roteamento:
//   /admin/*               → governance e tenant misturados (legado)
//   /admin/governance/*    → governança clínica cross-tenant (multi-role)
//   /admin/system/*        → operações de plataforma (super_admin only)
// ═══════════════════════════════════════════════════════════════

type NavGroupId = "main" | "tenant" | "governance" | "system";

type NavItem = {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  permissions?: string[];
  roles?: AuthUser["role"][];
  badge?: number | string;
  group?: NavGroupId;
};

const GROUP_LABELS: Record<NavGroupId, string> = {
  main: "",
  tenant: "Administração do tenant",
  governance: "Governança Clínica",
  system: "Sistema · Cross-tenant",
};

const NAV_ITEMS: NavItem[] = [
  // ─── Operação (todos com permission) ───
  { href: "/", label: "Dashboard", icon: Activity },
  { href: "/alertas", label: "Alertas", icon: ShieldAlert, permissions: ["alerts:read"] },
  { href: "/alertas/clinicos", label: "Alertas Clínicos", icon: ShieldAlert, permissions: ["alerts:read"] },
  { href: "/reports", label: "Relatos", icon: FileText, permissions: ["reports:read"] },
  { href: "/patients", label: "Pacientes", icon: UsersRound, permissions: ["patients:read"] },
  { href: "/teleconsulta", label: "Teleconsulta", icon: Video, permissions: ["teleconsulta:read"] },
  { href: "/sofia", label: "Sofia Chat", icon: Sparkles },
  { href: "/comunicacao", label: "Comunicação", icon: Phone },
  { href: "/equipe", label: "Equipe", icon: UserCog, permissions: ["caregivers:read"] },

  // ─── Administração do tenant ───
  {
    href: "/admin/usuarios",
    label: "Usuários",
    icon: Users,
    permissions: ["users:read"],
    group: "tenant",
  },
  {
    href: "/admin/perfis",
    label: "Papéis & Permissões",
    icon: KeyRound,
    permissions: ["profiles:read"],
    group: "tenant",
  },
  {
    href: "/admin/biometria-voz",
    label: "Biometria de Voz",
    icon: Volume2,
    roles: ["super_admin", "admin_tenant", "medico", "enfermeiro"],
    group: "tenant",
  },
  {
    href: "/admin/plantoes",
    label: "Plantões",
    icon: CalendarClock,
    roles: ["super_admin", "admin_tenant", "medico", "enfermeiro"],
    group: "tenant",
  },
  {
    href: "/admin/seguranca/fila-revisao",
    label: "Fila de Revisão",
    icon: ShieldAlert,
    roles: ["super_admin", "admin_tenant", "medico", "enfermeiro", "cuidador_pro", "familia"],
    group: "tenant",
  },
  { href: "/configuracoes", label: "Configurações", icon: Settings, group: "tenant" },

  // ─── Governança Clínica (cross-tenant, multi-role) ───
  {
    href: "/admin/governance/clinical-rules",
    label: "Regras Clínicas (master)",
    icon: Stethoscope,
    roles: ["super_admin", "admin_tenant"],
    group: "governance",
  },
  {
    href: "/admin/governance/cascades",
    label: "Cascatas",
    icon: GitFork,
    roles: ["super_admin", "admin_tenant", "medico", "enfermeiro"],
    group: "governance",
  },
  {
    href: "/admin/governance/review",
    label: "Revisão Clínica",
    icon: ClipboardCheck,
    roles: ["super_admin", "admin_tenant", "medico", "enfermeiro"],
    group: "governance",
  },
  {
    href: "/admin/governance/corpus-review",
    label: "Revisão · Corpus",
    icon: HeartHandshake,
    roles: ["super_admin", "admin_tenant", "clinical_reviewer", "medico"],
    group: "governance",
  },
  {
    href: "/admin/governance/synthetic-tests",
    label: "Testes Sintéticos",
    icon: Activity,
    roles: ["super_admin", "admin_tenant"],
    group: "governance",
  },
  {
    href: "/admin/governance/scenarios",
    label: "Cenários Sofia",
    icon: Phone,
    roles: ["super_admin", "admin_tenant"],
    group: "governance",
  },
  {
    href: "/admin/governance/scenarios/versions",
    label: "Versões de Prompts",
    icon: GitBranch,
    roles: ["super_admin", "admin_tenant"],
    group: "governance",
  },

  // ─── Sistema · Cross-tenant (SUPER_ADMIN ONLY) ───
  {
    href: "/admin/system",
    label: "Dashboard cross-tenant",
    icon: Activity,
    roles: ["super_admin"],
    group: "system",
  },
  {
    href: "/admin/system/tenants",
    label: "Tenants",
    icon: Building2,
    roles: ["super_admin"],
    group: "system",
  },
  {
    href: "/admin/system/health",
    label: "Saúde da Plataforma",
    icon: ServerCog,
    roles: ["super_admin"],
    group: "system",
  },
  {
    href: "/admin/system/health/risk-score",
    label: "Risk Score",
    icon: Activity,
    roles: ["super_admin"],
    group: "system",
  },
  {
    href: "/admin/system/operations/proactive-caller",
    label: "Proactive Caller",
    icon: PhoneOutgoing,
    roles: ["super_admin"],
    group: "system",
  },
  {
    href: "/admin/system/operations/leads",
    label: "Leads · Funil",
    icon: Sparkles,
    roles: ["super_admin", "admin_tenant"],
    group: "system",
  },
  {
    href: "/admin/system/operations/handoff",
    label: "Handoff · Atendimento Humano",
    icon: HeartHandshake,
    roles: ["super_admin", "admin_tenant", "medico", "enfermeiro"],
    group: "system",
  },
  {
    href: "/admin/system/conversations",
    label: "Conversas · Replay",
    icon: Phone,
    roles: ["super_admin", "admin_tenant"],
    group: "system",
  },
];

function visibleItems(user: AuthUser | null, group: NavGroupId): NavItem[] {
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
  const tenantItems = visibleItems(user, "tenant");
  const governanceItems = visibleItems(user, "governance");
  const systemItems = visibleItems(user, "system");

  return (
    <aside className="fixed left-0 top-0 bottom-0 w-60 border-r border-white/[0.06] bg-[hsl(222,47%,7%)]/80 backdrop-blur-xl flex flex-col z-40">
      {/* Logo */}
      <Link
        href="/"
        className="flex items-center gap-3 px-5 py-5 border-b border-white/[0.04] group"
      >
        <div className="relative">
          <div className="accent-gradient p-2 rounded-lg shadow-glow-cyan transition-transform group-hover:scale-105">
            <HeartPulse className="h-4 w-4 text-slate-900" strokeWidth={2.5} />
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
        <Group label={GROUP_LABELS.tenant} items={tenantItems} pathname={pathname} />
        <Group label={GROUP_LABELS.governance} items={governanceItems} pathname={pathname} />
        <Group label={GROUP_LABELS.system} items={systemItems} pathname={pathname} accent />
      </nav>

      <UserFooter />
    </aside>
  );
}

function Group({
  label,
  items,
  pathname,
  accent = false,
}: {
  label: string;
  items: NavItem[];
  pathname: string;
  accent?: boolean;
}) {
  if (items.length === 0) return null;
  return (
    <>
      <div
        className={`mt-5 mb-2 px-3 text-[9px] uppercase tracking-[0.18em] ${
          accent ? "text-accent-cyan/70" : "text-muted-foreground/60"
        }`}
      >
        {label}
      </div>
      <NavGroup items={items} pathname={pathname} />
    </>
  );
}

function NavGroup({ items, pathname }: { items: NavItem[]; pathname: string }) {
  return (
    <ul className="space-y-0.5">
      {items.map((item) => {
        const Icon = item.icon;
        // Longest-prefix-wins: /alertas não fica ativo em /alertas/clinicos
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
