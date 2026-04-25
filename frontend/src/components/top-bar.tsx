"use client";

import { Bell, ChevronDown, LogOut, Search, User as UserIcon } from "lucide-react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { useAuth } from "@/context/auth-context";
import { ROLE_LABEL } from "@/lib/permissions";

// ═══════════════════════════════════════════════════════════════
// Top bar — breadcrumbs + search global + status + notifications
// Altura fixa 56px, complementa a sidebar de 240px
// ═══════════════════════════════════════════════════════════════

type Crumb = { label: string; href?: string };

function routeToCrumbs(pathname: string): Crumb[] {
  if (pathname === "/") {
    return [
      { label: "Monitoramento · ConnectaIA" },
      { label: "Dashboard clínico" },
    ];
  }

  const segments = pathname.split("/").filter(Boolean);
  const crumbs: Crumb[] = [{ label: "Monitoramento · ConnectaIA" }];

  // Mapeamento de segmentos → labels legíveis
  const routeLabels: Record<string, string> = {
    patients: "Pacientes",
    reports: "Relatos",
    eventos: "Eventos",
    equipe: "Equipe",
    configuracoes: "Configurações",
    consulta: "Teleconsulta",
  };

  let accumulated = "";
  segments.forEach((seg, idx) => {
    accumulated += `/${seg}`;
    const label = routeLabels[seg];
    const isId = seg.length > 20 && !label; // UUID-ish
    if (label) {
      crumbs.push({
        label,
        href: idx < segments.length - 1 ? accumulated : undefined,
      });
    } else if (isId) {
      // Detalhe — placeholder, a página de detalhe pode sobrescrever
      crumbs.push({ label: "Detalhe" });
    } else {
      crumbs.push({ label: seg });
    }
  });

  return crumbs;
}

export function TopBar() {
  const pathname = usePathname();
  const crumbs = routeToCrumbs(pathname);

  return (
    <header className="fixed top-0 left-60 right-0 h-14 border-b border-white/[0.05] bg-[hsl(225,80%,7%)]/85 backdrop-blur-xl z-30">
      <div className="h-full px-6 flex items-center gap-4">
        {/* Breadcrumb */}
        <div className="flex items-center gap-2 text-xs min-w-0 flex-1">
          {crumbs.slice(0, -1).map((c, i) => (
            <div key={i} className="flex items-center gap-2">
              {c.href ? (
                <Link
                  href={c.href}
                  className="text-muted-foreground uppercase tracking-[0.12em] hover:text-foreground transition-colors truncate"
                >
                  {c.label}
                </Link>
              ) : (
                <span className="text-muted-foreground uppercase tracking-[0.12em] truncate">
                  {c.label}
                </span>
              )}
              <span className="text-muted-foreground/30">·</span>
            </div>
          ))}
          <span className="font-semibold text-foreground truncate">
            {crumbs[crumbs.length - 1]?.label}
          </span>
        </div>

        {/* Search global (⌘K) */}
        <GlobalSearch />

        {/* Sistema ativo + notificações + perfil */}
        <div className="flex items-center gap-3">
          <SystemStatus />
          <NotificationBell />
          <UserMenu />
        </div>
      </div>
    </header>
  );
}

function UserMenu() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  if (!user) return null;

  const initials = (user.fullName || user.email)
    .split(" ")
    .map((p) => p[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 pl-1.5 pr-2 py-1 rounded-full hover:bg-white/[0.04] transition-colors"
        title={user.email}
      >
        {user.avatarUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={user.avatarUrl}
            alt={user.fullName}
            className="w-7 h-7 rounded-full object-cover border border-white/10"
          />
        ) : (
          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-accent-cyan/30 to-accent-teal/30 border border-white/10 flex items-center justify-center text-[10px] font-bold">
            {initials || "?"}
          </div>
        )}
        <ChevronDown className="h-3 w-3 text-muted-foreground" />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 w-60 rounded-lg border border-white/[0.08] bg-[hsl(225,80%,8%)]/95 backdrop-blur-xl shadow-[0_8px_32px_rgba(0,0,0,0.5)] z-50 overflow-hidden">
          <div className="px-3 py-3 border-b border-white/[0.06]">
            <div className="text-xs font-medium text-foreground truncate">
              {user.fullName}
            </div>
            <div className="text-[10px] text-muted-foreground truncate mt-0.5">
              {user.email}
            </div>
            <div className="text-[9px] uppercase tracking-[0.14em] text-accent-cyan mt-1.5">
              {ROLE_LABEL[user.role] || user.role}
            </div>
          </div>
          <div className="py-1">
            <Link
              href="/perfil"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 px-3 py-2 text-xs text-foreground hover:bg-white/[0.04]"
            >
              <UserIcon className="h-3.5 w-3.5" />
              Meu perfil
            </Link>
            <button
              onClick={() => {
                setOpen(false);
                logout();
              }}
              className="w-full flex items-center gap-2 px-3 py-2 text-xs text-classification-attention hover:bg-classification-attention/10 text-left"
            >
              <LogOut className="h-3.5 w-3.5" />
              Sair
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function GlobalSearch() {
  const [focused, setFocused] = useState(false);
  const [query, setQuery] = useState("");

  // ⌘K / Ctrl+K abre o search
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        const input = document.getElementById("global-search") as HTMLInputElement | null;
        input?.focus();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div
      className={`
        relative flex items-center gap-2 w-72 px-3 py-1.5 rounded-lg
        bg-white/[0.03] border transition-all
        ${focused ? "border-accent-cyan/40 bg-white/[0.05]" : "border-white/[0.06]"}
      `}
    >
      <Search
        className={`h-3.5 w-3.5 flex-shrink-0 ${
          focused ? "text-accent-cyan" : "text-muted-foreground"
        }`}
      />
      <input
        id="global-search"
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        placeholder="Buscar paciente, relato, evento..."
        className="flex-1 bg-transparent outline-none text-xs placeholder:text-muted-foreground/70"
      />
      <kbd className="hidden md:inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-white/[0.05] border border-white/[0.06] text-[9px] text-muted-foreground font-mono">
        ⌘K
      </kbd>
    </div>
  );
}

function SystemStatus() {
  return (
    <div
      className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white/[0.03] border border-white/[0.06]"
      title="Sistema operacional — Íris ativa"
    >
      <span className="relative flex h-1.5 w-1.5">
        <span className="absolute inline-flex h-full w-full rounded-full bg-classification-routine opacity-75 animate-ping" />
        <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-classification-routine" />
      </span>
      <span className="text-[11px] font-medium text-muted-foreground">
        Sistema ativo
      </span>
    </div>
  );
}

function NotificationBell() {
  // TODO: conectar com eventos live quando tiver endpoint de notifications
  const [unread] = useState<number>(0);

  return (
    <button
      className="relative p-2 rounded-lg hover:bg-white/[0.04] transition-colors group"
      title="Notificações"
    >
      <Bell
        className={`h-4 w-4 ${
          unread > 0
            ? "text-classification-urgent"
            : "text-muted-foreground group-hover:text-foreground"
        }`}
      />
      {unread > 0 && (
        <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-classification-urgent text-[9px] font-bold text-white flex items-center justify-center animate-pulse-soft">
          {unread > 9 ? "9+" : unread}
        </span>
      )}
    </button>
  );
}
