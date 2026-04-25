import { NextResponse, type NextRequest } from "next/server";

/**
 * Auth middleware — bloqueia páginas privadas se não houver cookie `care_token`.
 *
 * Não validamos a assinatura do JWT aqui (edge runtime, sem o segredo) —
 * apenas a presença. O backend valida em cada chamada de API e o
 * AuthContext faz `GET /api/auth/me` no boot pra confirmar a sessão.
 *
 * Rotas públicas (acessíveis sem token):
 *   /login                       — formulário de login
 *   /cadastro/*                  — onboarding B2C
 *   /pitch                       — material de marketing
 *   /planos                      — tabela de planos
 *   /demo/onboarding             — Sofia ao vivo (público intencionalmente)
 *   /meu/[id]                    — portal do paciente (PIN-gated, próprio guard)
 *   /consulta/[room]             — sala de teleconsulta (token JWT no link)
 *   /consulta/finalizada         — tela pós-call
 *   _next/* / static / favicon   — assets
 */

const PUBLIC_PATHS = new Set([
  "/login",
  "/pitch",
  "/planos",
]);

const PUBLIC_PREFIXES = [
  "/cadastro",
  "/demo",
  "/meu",
  "/consulta",
  "/_next",
  "/static",
  "/api",          // o backend tem seu próprio gate; Next.js só roteia
  "/images",
  "/favicon",
];

function isPublic(pathname: string): boolean {
  if (PUBLIC_PATHS.has(pathname)) return true;
  return PUBLIC_PREFIXES.some((p) => pathname.startsWith(p));
}

export function middleware(req: NextRequest) {
  const { pathname, search } = req.nextUrl;

  if (isPublic(pathname)) {
    return NextResponse.next();
  }

  const token = req.cookies.get("care_token")?.value;
  if (token) {
    return NextResponse.next();
  }

  // Sem token → redireciona pra login preservando destino.
  const loginUrl = req.nextUrl.clone();
  loginUrl.pathname = "/login";
  loginUrl.searchParams.set("next", pathname + search);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  // Casa todas as rotas exceto arquivos estáticos óbvios. PUBLIC_PREFIXES
  // ainda escapa o que precisa ficar público dentro do app.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
