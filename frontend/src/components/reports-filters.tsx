"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useLayoutEffect, useRef, useState, useTransition } from "react";
import { createPortal } from "react-dom";
import { Search, X, SlidersHorizontal, ChevronDown, Check } from "lucide-react";

// ═══════════════════════════════════════════════════════════════
// Barra de filtros compacta (inspiração Linear/Vercel)
// Sincroniza com URL query pra deep-link + back button funcionam
// ═══════════════════════════════════════════════════════════════

const CLASSIFICATIONS = [
  { value: "critical", label: "Crítico", color: "classification-critical" },
  { value: "urgent", label: "Urgente", color: "classification-urgent" },
  { value: "attention", label: "Atenção", color: "classification-attention" },
  { value: "routine", label: "Rotina", color: "classification-routine" },
] as const;

const DAYS_OPTIONS = [
  { value: 1, label: "Hoje" },
  { value: 7, label: "Últimos 7 dias" },
  { value: 30, label: "Últimos 30 dias" },
  { value: 90, label: "Últimos 90 dias" },
  { value: 365, label: "Último ano" },
];

export function ReportsFilters({
  totalFiltered,
  totalAll,
}: {
  totalFiltered: number;
  totalAll?: number;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();

  // Estados iniciais vindos da URL
  const initialSearch = searchParams.get("search") || "";
  const initialClassif = (searchParams.get("classification") || "").split(",").filter(Boolean);
  const initialDays = Number(searchParams.get("days") || "30");

  const [search, setSearch] = useState(initialSearch);
  const [classifications, setClassifications] = useState<string[]>(initialClassif);
  const [days, setDays] = useState<number>(initialDays);
  const [classifOpen, setClassifOpen] = useState(false);
  const [daysOpen, setDaysOpen] = useState(false);

  const classifRef = useRef<HTMLDivElement>(null);
  const daysRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  // Fecha dropdowns ao clicar fora — ignora cliques dentro de FloatingMenus
  // (portal no body, fora dos refs dos âncoras)
  useEffect(() => {
    function onClick(e: MouseEvent) {
      const target = e.target as HTMLElement | null;
      // Se o click foi num portal de menu nosso, deixa o handler do item lidar
      if (target?.closest('[data-filter-menu="true"]')) return;

      if (classifRef.current && !classifRef.current.contains(target)) {
        setClassifOpen(false);
      }
      if (daysRef.current && !daysRef.current.contains(target)) {
        setDaysOpen(false);
      }
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  // Debounce search — atualiza URL 400ms depois de parar de digitar
  useEffect(() => {
    const id = setTimeout(() => {
      updateUrl({ search, classifications, days });
    }, 400);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  // Classifications + days atualizam URL imediatamente
  useEffect(() => {
    updateUrl({ search, classifications, days });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classifications, days]);

  // Shortcut: / foca no search
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement;
      if (target && ["INPUT", "TEXTAREA"].includes(target.tagName)) return;
      if (e.key === "/") {
        e.preventDefault();
        searchRef.current?.focus();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function updateUrl(state: {
    search: string;
    classifications: string[];
    days: number;
  }) {
    const params = new URLSearchParams();
    if (state.search) params.set("search", state.search);
    if (state.classifications.length > 0)
      params.set("classification", state.classifications.join(","));
    if (state.days !== 30) params.set("days", String(state.days));

    const url = params.toString() ? `/reports?${params.toString()}` : "/reports";
    startTransition(() => {
      router.replace(url);
    });
  }

  function toggleClassif(v: string) {
    setClassifications((prev) =>
      prev.includes(v) ? prev.filter((x) => x !== v) : [...prev, v],
    );
  }

  function clearAll() {
    setSearch("");
    setClassifications([]);
    setDays(30);
  }

  const hasActiveFilters =
    search.length > 0 || classifications.length > 0 || days !== 30;

  const selectedDaysLabel =
    DAYS_OPTIONS.find((o) => o.value === days)?.label || "Período";

  return (
    <div className="glass-card rounded-xl p-3 flex items-center gap-2 flex-wrap">
      {/* Search input */}
      <div className="flex items-center gap-2 flex-1 min-w-[280px] px-3 py-1.5 rounded-lg bg-white/[0.03] border border-white/[0.06] focus-within:border-accent-cyan/40 focus-within:bg-white/[0.05] transition-all">
        <Search className="h-4 w-4 text-muted-foreground flex-shrink-0" />
        <input
          ref={searchRef}
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Buscar em transcrição ou resumo..."
          className="flex-1 bg-transparent outline-none text-sm placeholder:text-muted-foreground/70"
        />
        {search && (
          <button
            onClick={() => setSearch("")}
            className="text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
        <kbd className="hidden md:inline-flex items-center px-1.5 py-0.5 rounded bg-white/[0.05] border border-white/[0.06] text-[9px] text-muted-foreground font-mono">
          /
        </kbd>
      </div>

      {/* Filtro: Classificação (multi) */}
      <div ref={classifRef}>
        <button
          onClick={() => setClassifOpen((v) => !v)}
          className={`
            inline-flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium
            transition-all border
            ${
              classifications.length > 0
                ? "bg-accent-cyan/10 border-accent-cyan/25 text-accent-cyan"
                : "bg-white/[0.03] border-white/[0.06] text-muted-foreground hover:text-foreground hover:border-white/[0.12]"
            }
          `}
        >
          <SlidersHorizontal className="h-3.5 w-3.5" />
          {classifications.length === 0 ? (
            "Classificação"
          ) : (
            <>
              Classificação
              <span className="text-[10px] px-1 py-0 rounded bg-accent-cyan/20 tabular">
                {classifications.length}
              </span>
            </>
          )}
          <ChevronDown
            className={`h-3 w-3 transition-transform ${classifOpen ? "rotate-180" : ""}`}
          />
        </button>

        <FloatingMenu
          open={classifOpen}
          anchorRef={classifRef}
          minWidth={200}
          align="right"
        >
          {CLASSIFICATIONS.map((c) => {
            const active = classifications.includes(c.value);
            return (
              <button
                key={c.value}
                onClick={() => toggleClassif(c.value)}
                className={`
                  w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-md text-sm text-left
                  transition-colors
                  ${
                    active
                      ? "bg-white/[0.05] text-foreground"
                      : "text-muted-foreground hover:bg-white/[0.03] hover:text-foreground"
                  }
                `}
              >
                <span
                  className={`w-2.5 h-2.5 rounded-sm`}
                  style={{ backgroundColor: `hsl(var(--${c.color}))` }}
                />
                <span className="flex-1">{c.label}</span>
                {active && <Check className="h-3.5 w-3.5 text-accent-cyan" />}
              </button>
            );
          })}
        </FloatingMenu>
      </div>

      {/* Filtro: Período */}
      <div ref={daysRef}>
        <button
          onClick={() => setDaysOpen((v) => !v)}
          className={`
            inline-flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium
            transition-all border
            ${
              days !== 30
                ? "bg-accent-cyan/10 border-accent-cyan/25 text-accent-cyan"
                : "bg-white/[0.03] border-white/[0.06] text-muted-foreground hover:text-foreground hover:border-white/[0.12]"
            }
          `}
        >
          {selectedDaysLabel}
          <ChevronDown
            className={`h-3 w-3 transition-transform ${daysOpen ? "rotate-180" : ""}`}
          />
        </button>

        <FloatingMenu
          open={daysOpen}
          anchorRef={daysRef}
          minWidth={180}
          align="right"
        >
          {DAYS_OPTIONS.map((o) => (
            <button
              key={o.value}
              onClick={() => {
                setDays(o.value);
                setDaysOpen(false);
              }}
              className={`
                w-full flex items-center justify-between px-2.5 py-1.5 rounded-md text-sm
                transition-colors
                ${
                  days === o.value
                    ? "bg-white/[0.05] text-accent-cyan"
                    : "text-muted-foreground hover:bg-white/[0.03] hover:text-foreground"
                }
              `}
            >
              {o.label}
              {days === o.value && <Check className="h-3.5 w-3.5" />}
            </button>
          ))}
        </FloatingMenu>
      </div>

      {/* Divisor */}
      <div className="hidden md:block w-px h-6 bg-white/[0.06] mx-1" />

      {/* Contador + clear */}
      <div className="flex items-center gap-2 text-xs">
        <span className="text-muted-foreground tabular">
          {isPending ? (
            <span className="animate-pulse-soft">atualizando…</span>
          ) : (
            <>
              <span className="font-semibold text-foreground">{totalFiltered}</span>{" "}
              {totalFiltered === 1 ? "relato" : "relatos"}
              {totalAll !== undefined && totalAll !== totalFiltered && (
                <span className="opacity-60"> de {totalAll}</span>
              )}
            </>
          )}
        </span>
        {hasActiveFilters && (
          <button
            onClick={clearAll}
            className="text-xs text-accent-cyan hover:text-accent-teal transition-colors flex items-center gap-1"
          >
            <X className="h-3 w-3" />
            Limpar
          </button>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// FloatingMenu — dropdown via React Portal
// Escapa do stacking context criado por backdrop-filter dos glass-cards
// Posicionado via getBoundingClientRect do anchor; reposiciona no scroll/resize
// ═══════════════════════════════════════════════════════════════
function FloatingMenu({
  open,
  anchorRef,
  minWidth = 180,
  align = "right",
  children,
}: {
  open: boolean;
  anchorRef: React.RefObject<HTMLDivElement | null>;
  minWidth?: number;
  align?: "left" | "right";
  children: React.ReactNode;
}) {
  const [mounted, setMounted] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  useEffect(() => setMounted(true), []);

  useLayoutEffect(() => {
    if (!open || !anchorRef.current) {
      setPos(null);
      return;
    }

    function compute() {
      const anchor = anchorRef.current;
      if (!anchor) return;
      const rect = anchor.getBoundingClientRect();
      const top = rect.bottom + 6;
      const menuWidth = Math.max(minWidth, rect.width);
      const left =
        align === "right"
          ? Math.max(8, rect.right - menuWidth)
          : rect.left;
      setPos({ top, left });
    }

    compute();
    window.addEventListener("scroll", compute, true);
    window.addEventListener("resize", compute);
    return () => {
      window.removeEventListener("scroll", compute, true);
      window.removeEventListener("resize", compute);
    };
  }, [open, anchorRef, minWidth, align]);

  if (!open || !mounted || !pos) return null;

  return createPortal(
    <div
      data-filter-menu="true"
      style={{
        position: "fixed",
        top: pos.top,
        left: pos.left,
        minWidth,
        zIndex: 9999,
      }}
      className="glass-card rounded-lg p-1 shadow-2xl border border-white/[0.1] animate-fade-up"
    >
      {children}
    </div>,
    document.body,
  );
}
