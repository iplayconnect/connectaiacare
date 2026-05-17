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
  BookMarked,
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
  KanbanSquare,
  Calendar,
  Package,
  Headphones,
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
  /**
   * Tooltip exibido ao passar o mouse sobre o item. Curto (até 110
   * chars), descreve a FUNÇÃO REAL da página — não apenas duplica o
   * label. Usado pelo title attr do <Link> (tooltip nativo do browser).
   */
  description?: string;
};

const GROUP_LABELS: Record<NavGroupId, string> = {
  main: "",
  tenant: "Administração do tenant",
  governance: "Governança Clínica",
  system: "Sistema · Cross-tenant",
};

const NAV_ITEMS: NavItem[] = [
  // ─── Operação (todos com permission) ───
  {
    href: "/",
    label: "Dashboard",
    icon: Activity,
    description: "Visão operacional ao vivo: eventos clínicos ativos, KPIs, feed de relatos recentes.",
  },
  {
    href: "/alertas",
    label: "Alertas Operacionais",
    icon: ShieldAlert,
    permissions: ["alerts:read"],
    description: "Triagem de care events: relatos, check-ins e eventos clínicos abertos esperando ação.",
  },
  {
    href: "/alertas/clinicos",
    label: "Alertas Clínicos",
    icon: ShieldAlert,
    permissions: ["alerts:read"],
    description: "Motor de validação farmacológica: doses, interações, contraindicações com reconhecimento/resolução.",
  },
  {
    href: "/reports",
    label: "Relatos",
    icon: FileText,
    permissions: ["reports:read"],
    description: "Histórico de relatos de cuidadores (áudio + transcrição + classificação Íris).",
  },
  {
    href: "/patients",
    label: "Pacientes",
    icon: UsersRound,
    permissions: ["patients:read"],
    description: "Lista e cadastro de pacientes monitorados; click abre prontuário 360°.",
  },
  {
    href: "/teleconsulta",
    label: "Teleconsulta",
    icon: Video,
    permissions: ["teleconsulta:read"],
    description: "Salas Jitsi: agendadas, ativas, pós-consulta com SOAP eletrônico.",
  },
  {
    href: "/sofia",
    label: "Sofia Chat",
    icon: Sparkles,
    description: "Chat persona-aware: tire dúvidas clínicas, peça contexto de paciente, simule conversas.",
  },
  {
    href: "/comunicacao",
    label: "Chamadas · VoIP",
    icon: Phone,
    description: "Hub de ligações: nova chamada, em andamento, histórico com transcrição.",
  },
  {
    href: "/equipe",
    label: "Equipe Clínica",
    icon: UserCog,
    permissions: ["caregivers:read"],
    description: "Médicos, enfermeiros, cuidadores e técnicos que ATENDEM pacientes (tabs por papel).",
  },

  // ─── Administração do tenant ───
  {
    href: "/admin/usuarios",
    label: "Usuários do CRM",
    icon: Users,
    permissions: ["users:read"],
    group: "tenant",
    description: "Quem tem CONTA no painel: email, papel, CRM/COREN, ativo/inativo. ≠ Equipe Clínica.",
  },
  {
    href: "/admin/perfis",
    label: "Papéis & Permissões",
    icon: KeyRound,
    permissions: ["profiles:read"],
    group: "tenant",
    description: "Crie papéis customizados além dos defaults (super_admin, médico, etc.) com checkboxes de permissões.",
  },
  {
    href: "/admin/biometria-voz",
    label: "Biometria de Voz",
    icon: Volume2,
    roles: ["super_admin", "admin_tenant", "medico", "enfermeiro"],
    group: "tenant",
    description: "Enrollment de voiceprints (pacientes e cuidadores) + cobertura por unidade.",
  },
  {
    href: "/admin/plantoes",
    label: "Escala de Cuidadores",
    icon: CalendarClock,
    roles: ["super_admin", "admin_tenant", "medico", "enfermeiro"],
    group: "tenant",
    description: "Turnos dos cuidadores que atendem pacientes (quem está em plantão agora, escala futura).",
  },
  {
    href: "/admin/seguranca/fila-revisao",
    label: "Fila de Revisão · Safety",
    icon: ShieldAlert,
    roles: ["super_admin", "admin_tenant", "medico", "enfermeiro", "cuidador_pro", "familia"],
    group: "tenant",
    description: "Safety Guardrail: ações clínicas críticas esperando aprovação humana (countdown auto-exec).",
  },
  {
    href: "/configuracoes",
    label: "Padrões & Compliance",
    icon: Settings,
    group: "tenant",
    description: "Catálogo READ-ONLY de padrões adotados (FHIR, CID-10, escalas, evidência) — vitrine compliance.",
  },

  // ─── Governança Clínica (cross-tenant, multi-role) ───
  {
    href: "/admin/governance/clinical-rules",
    label: "Regras Clínicas (master)",
    icon: Stethoscope,
    roles: ["super_admin", "admin_tenant"],
    group: "governance",
    description: "CRUD de doses máximas, aliases de medicamentos, interações. Alimenta o motor de Alertas Clínicos.",
  },
  {
    href: "/admin/governance/cascades",
    label: "Cascatas Farmacológicas",
    icon: GitFork,
    roles: ["super_admin", "admin_tenant", "medico", "enfermeiro"],
    group: "governance",
    description: "Read-only: visualização das cascatas de prescrição (A+C, A+B+C) com severidade.",
  },
  {
    href: "/admin/governance/review",
    label: "Revisão · Clínica",
    icon: ClipboardCheck,
    roles: ["super_admin", "admin_tenant", "medico", "enfermeiro"],
    group: "governance",
    description: "Revisão clínica geral pelo time interno (sample-based).",
  },
  {
    href: "/admin/governance/corpus-review",
    label: "Revisão · Corpus",
    icon: HeartHandshake,
    roles: ["super_admin", "admin_tenant", "clinical_reviewer", "medico"],
    group: "governance",
    description: "Revisão case-a-case do corpus de classificação (concordância/discordância com LLM).",
  },
  {
    href: "/admin/governance/curated-review",
    label: "Revisão · Bases Curadas",
    icon: BookMarked,
    roles: ["super_admin", "admin_tenant", "clinical_reviewer", "medico", "farmaceutico"],
    group: "governance",
    description: "Revisão das bases curadas: CID-10, medicamentos, regras de cross-validation (Henrique + PUC).",
  },
  {
    href: "/admin/governance/synthetic-tests",
    label: "Testes Sintéticos",
    icon: Activity,
    roles: ["super_admin", "admin_tenant"],
    group: "governance",
    description: "Bateria de cenários sintéticos pra validar regressões antes de subir pra produção.",
  },
  {
    href: "/admin/governance/scenarios",
    label: "Cenários da Sofia",
    icon: Phone,
    roles: ["super_admin", "admin_tenant"],
    group: "governance",
    description: "Playbooks VoIP da Sofia: prompts, persona, voz, tools, ações pós-call (com versionamento).",
  },
  {
    href: "/admin/governance/scenarios/versions",
    label: "Versões de Prompts",
    icon: GitBranch,
    roles: ["super_admin", "admin_tenant"],
    group: "governance",
    description: "Histórico de versões dos prompts da Sofia (diff, rollback).",
  },

  // ─── Sistema · Cross-tenant (SUPER_ADMIN ONLY) ───
  {
    href: "/admin/system",
    label: "Dashboard cross-tenant",
    icon: Activity,
    roles: ["super_admin"],
    group: "system",
    description: "Visão agregada de TODOS os tenants: totais, série 7d, top tenants, distribuição 30d.",
  },
  {
    href: "/admin/system/tenants",
    label: "Tenants",
    icon: Building2,
    roles: ["super_admin"],
    group: "system",
    description: "Provisioning SaaS: criar/editar/suspender tenants (ILPI, clínicas, parceiros como Tecnosenior).",
  },
  {
    href: "/admin/system/health",
    label: "Saúde da Plataforma",
    icon: ServerCog,
    roles: ["super_admin"],
    group: "system",
    description: "Uptime, latência, uso de recursos, status de integrações cross-tenant.",
  },
  {
    href: "/admin/system/health/risk-score",
    label: "Risk Score Agregado",
    icon: Activity,
    roles: ["super_admin"],
    group: "system",
    description: "Score consolidado de risco da plataforma (clínico + operacional + integração).",
  },
  {
    href: "/admin/system/operations/proactive-caller",
    label: "Sofia Proativa",
    icon: PhoneOutgoing,
    roles: ["super_admin"],
    group: "system",
    description: "Sofia outbound: chamadas proativas pra check-in de paciente (vê fila + executa).",
  },
  {
    href: "/admin/system/operations/leads",
    label: "Leads · Lista (legado)",
    icon: Sparkles,
    roles: ["super_admin", "admin_tenant"],
    group: "system",
    description: "DEPRECATED: lista antiga de leads comerciais. Substituída por Comercial · Funil.",
  },
  // ─── Phase D Comercial — único item, abre /comercial/funil
  // (com tabs Funil / Agenda / Planos no layout interno)
  {
    href: "/admin/system/operations/comercial/funil",
    label: "Comercial · Funil",
    icon: KanbanSquare,
    roles: ["super_admin", "admin_tenant", "comercial"],
    group: "system",
    description: "Funil de vendas ConnectaIACare: prospects → demos → propostas → fechamento.",
  },
  {
    href: "/admin/system/operations/handoff",
    label: "Handoff · Fila",
    icon: HeartHandshake,
    roles: ["super_admin", "admin_tenant", "medico", "enfermeiro"],
    group: "system",
    description: "Fila de pedidos que a Sofia escalou pra humano — reivindique e atenda no chat.",
  },
  {
    href: "/admin/system/operations/central",
    label: "Central · ATENT 24/7",
    icon: Headphones,
    roles: ["super_admin", "operador_central"],
    group: "system",
    description: "Operação 24/7: fila cross-tenant priorizada (P1/P2/P3) com SLA e heartbeat de operadores.",
  },
  {
    href: "/admin/system/operations/escalation-contacts",
    label: "Plantão Técnico · Contatos P1",
    icon: UserCog,
    roles: ["super_admin", "admin_tenant"],
    group: "system",
    description: "CRUD de quem recebe push WhatsApp em P1 clínico (≠ Escala de Cuidadores).",
  },
  {
    href: "/admin/system/conversations",
    label: "Conversas · Replay",
    icon: Phone,
    roles: ["super_admin", "admin_tenant"],
    group: "system",
    description: "Replay de conversas Sofia para auditoria LGPD e análise de qualidade (filtro tenant/paciente/período).",
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
              // Tooltip nativo do browser via title attr. Mostra a descrição
              // curta da função se houver; cai pro label se não tiver
              // description preenchida. Considerar trocar por componente
              // custom (Radix Tooltip) se quiser estilização dark theme.
              title={item.description || item.label}
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
