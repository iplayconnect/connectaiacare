/**
 * Helpers de autenticação no client.
 *
 * O token JWT é persistido em DOIS lugares pra cobrir os dois consumidores:
 *
 *   1. localStorage  — lido pelo `lib/api.ts` (fetch client) p/ injetar Bearer
 *   2. Cookie        — lido pelo `middleware.ts` (Next.js edge runtime, sem
 *                      acesso a localStorage) p/ redirecionar não-autenticado
 *
 * Cookie config:
 *   - SameSite=Lax (envia em GET top-level mas não cross-site POST)
 *   - Secure em prod (HTTPS-only)
 *   - HttpOnly NÃO setado: precisamos ler/escrever via JS pra logout client-side
 *     e injeção do Bearer. Trade-off de segurança documentado em SECURITY.md
 *     (XSS é prevenido por React + DOMPurify nos inputs livres, não pelo cookie).
 *   - Validade alinhada com TTL do refresh token (7d default).
 */

export const TOKEN_COOKIE = "care_token";
export const USER_COOKIE = "care_user";
const TOKEN_LS_KEY = "care_token";
const USER_LS_KEY = "care_user";
const REFRESH_LS_KEY = "care_refresh_token";

const COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 7; // 7 dias

export type Role =
  | "super_admin"
  | "admin_tenant"
  | "medico"
  | "enfermeiro"
  | "cuidador_pro"
  | "familia"
  | "parceiro";

export type AuthUser = {
  id: string;
  tenantId: string;
  email: string;
  fullName: string;
  role: Role;
  permissions: string[];
  profileId: string | null;
  avatarUrl: string | null;
  phone: string | null;
  crmRegister: string | null;
  corenRegister: string | null;
  caregiverId: string | null;
  patientId: string | null;
  partnerOrg: string | null;
  allowedPatientIds: string[];
  mfaEnabled: boolean;
  passwordChangeRequired: boolean;
};

function setCookie(name: string, value: string, maxAgeSeconds: number) {
  if (typeof document === "undefined") return;
  const isHttps =
    typeof window !== "undefined" && window.location.protocol === "https:";
  const parts = [
    `${name}=${encodeURIComponent(value)}`,
    "Path=/",
    `Max-Age=${maxAgeSeconds}`,
    "SameSite=Lax",
  ];
  if (isHttps) parts.push("Secure");
  document.cookie = parts.join("; ");
}

function deleteCookie(name: string) {
  if (typeof document === "undefined") return;
  document.cookie = `${name}=; Path=/; Max-Age=0; SameSite=Lax`;
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_LS_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_LS_KEY);
}

export function getStoredUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_LS_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function persistAuth(token: string, refreshToken: string, user: AuthUser) {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_LS_KEY, token);
  localStorage.setItem(REFRESH_LS_KEY, refreshToken);
  localStorage.setItem(USER_LS_KEY, JSON.stringify(user));
  setCookie(TOKEN_COOKIE, token, COOKIE_MAX_AGE_SECONDS);
  // Cookie de usuário só serve pra middleware ter um hint do role nas
  // primeiras renderizações. Nada sensível.
  setCookie(
    USER_COOKIE,
    JSON.stringify({ id: user.id, role: user.role, tenantId: user.tenantId }),
    COOKIE_MAX_AGE_SECONDS,
  );
}

export function clearAuth() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_LS_KEY);
  localStorage.removeItem(REFRESH_LS_KEY);
  localStorage.removeItem(USER_LS_KEY);
  deleteCookie(TOKEN_COOKIE);
  deleteCookie(USER_COOKIE);
}
