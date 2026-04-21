import Link from "next/link";
import { Activity, FileText, HeartPulse, Users } from "lucide-react";

export function Header() {
  return (
    <header className="glass-header sticky top-0 z-50">
      <div className="container flex h-16 items-center justify-between">
        <Link href="/" className="flex items-center gap-3 group">
          <div className="relative">
            <div className="accent-gradient p-2.5 rounded-lg shadow-glow-cyan transition-transform group-hover:scale-105">
              <HeartPulse className="h-5 w-5 text-slate-900" strokeWidth={2.5} />
            </div>
            <div className="absolute -inset-0.5 accent-gradient rounded-lg opacity-0 group-hover:opacity-30 blur transition-opacity" />
          </div>
          <div>
            <h1 className="font-bold text-lg leading-tight tracking-tight">
              <span className="accent-gradient-text">ConnectaIA</span>
              <span className="text-foreground">Care</span>
            </h1>
            <p className="text-xs text-muted-foreground leading-tight uppercase tracking-[0.2em]">
              Cuidado Integrado · IA
            </p>
          </div>
        </Link>

        <nav className="flex items-center gap-1">
          <NavLink href="/" icon={<Activity className="h-4 w-4" />} label="Dashboard" />
          <NavLink href="/reports" icon={<FileText className="h-4 w-4" />} label="Relatos" />
          <NavLink href="/patients" icon={<Users className="h-4 w-4" />} label="Pacientes" />
        </nav>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/[0.03] border border-white/[0.06]">
            <span className="status-dot status-dot-active" />
            <span className="text-xs font-medium text-muted-foreground">Sistema ativo</span>
          </div>
        </div>
      </div>
    </header>
  );
}

function NavLink({
  href,
  icon,
  label,
}: {
  href: string;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <Link
      href={href}
      className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-white/[0.04] transition-colors"
    >
      {icon}
      {label}
    </Link>
  );
}
