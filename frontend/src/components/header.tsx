import Link from "next/link";
import { Heart, Activity, Users, FileText } from "lucide-react";

export function Header() {
  return (
    <header className="border-b bg-white sticky top-0 z-50 shadow-sm">
      <div className="container flex h-16 items-center justify-between">
        <Link href="/" className="flex items-center gap-2">
          <div className="bg-gradient-to-br from-blue-600 to-teal-500 p-2 rounded-lg">
            <Heart className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-bold text-lg leading-tight">ConnectaIACare</h1>
            <p className="text-[10px] text-muted-foreground leading-tight uppercase tracking-wider">
              Cuidado Integrado com IA
            </p>
          </div>
        </Link>
        <nav className="flex items-center gap-6">
          <Link
            href="/"
            className="flex items-center gap-2 text-sm font-medium text-slate-700 hover:text-blue-600 transition"
          >
            <Activity className="h-4 w-4" />
            Dashboard
          </Link>
          <Link
            href="/reports"
            className="flex items-center gap-2 text-sm font-medium text-slate-700 hover:text-blue-600 transition"
          >
            <FileText className="h-4 w-4" />
            Relatos
          </Link>
          <Link
            href="/patients"
            className="flex items-center gap-2 text-sm font-medium text-slate-700 hover:text-blue-600 transition"
          >
            <Users className="h-4 w-4" />
            Pacientes
          </Link>
        </nav>
      </div>
    </header>
  );
}
