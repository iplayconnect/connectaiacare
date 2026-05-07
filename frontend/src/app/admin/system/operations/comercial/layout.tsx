"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { KanbanSquare, Calendar, Package, Sparkles, List } from "lucide-react";

const TABS = [
  {
    href: "/admin/system/operations/comercial/funil",
    label: "Funil",
    icon: KanbanSquare,
  },
  {
    href: "/admin/system/operations/comercial/lista",
    label: "Lista",
    icon: List,
  },
  {
    href: "/admin/system/operations/comercial/agenda",
    label: "Agenda",
    icon: Calendar,
  },
  {
    href: "/admin/system/operations/comercial/planos",
    label: "Planos",
    icon: Package,
  },
];

export default function ComercialLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  // Tab "Detalhe" é dinâmica — qualquer rota /comercial/leads/[id]
  const isLeadDetail =
    pathname?.includes("/comercial/leads/") && !pathname.endsWith("/leads");

  return (
    <div className="min-h-screen">
      <div className="px-6 lg:px-8 pt-6">
        <div className="flex items-center gap-2 mb-1 text-xs text-muted-foreground">
          <Sparkles className="w-3 h-3" />
          <span>Comercial</span>
        </div>

        <nav className="flex items-center gap-1 border-b border-white/10 -mb-px">
          {TABS.map((t) => {
            const active = pathname === t.href;
            const Icon = t.icon;
            return (
              <Link
                key={t.href}
                href={t.href}
                className={`px-4 py-2.5 text-sm font-medium border-b-2 transition flex items-center gap-1.5 ${
                  active
                    ? "border-cyan-400 text-cyan-300"
                    : "border-transparent text-slate-400 hover:text-slate-200 hover:border-white/20"
                }`}
              >
                <Icon className="w-4 h-4" />
                {t.label}
              </Link>
            );
          })}
          {isLeadDetail && (
            <span className="px-4 py-2.5 text-sm font-medium border-b-2 border-cyan-400 text-cyan-300 flex items-center gap-1.5">
              <Sparkles className="w-4 h-4" />
              Detalhe do Lead
            </span>
          )}
        </nav>
      </div>

      <div>{children}</div>
    </div>
  );
}
