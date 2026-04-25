/**
 * Permissions/RBAC client-side — espelho de backend/src/services/permissions.py.
 *
 * Não é a fonte da verdade (backend valida em todo endpoint), mas serve pra:
 *   - filtrar items da Sidebar por permission (ou role)
 *   - esconder botões/ações que o user não pode executar
 *   - redirecionar de páginas que ele não pode acessar
 *
 * Mantemos sincronizado com o backend; quando o backend ganhar `/api/ui/config`
 * dinâmico (Bloco C v2), trocamos a fonte por aquela rota.
 */

import type { AuthUser, Role } from "./auth";

export const ROLE_LABEL: Record<Role, string> = {
  super_admin: "Super admin",
  admin_tenant: "Admin do tenant",
  medico: "Médico",
  enfermeiro: "Enfermeiro(a)",
  cuidador_pro: "Cuidador(a)",
  familia: "Familiar",
  parceiro: "Parceiro",
  paciente_b2c: "Paciente",
};

export function hasPermission(user: AuthUser | null, required: string): boolean {
  if (!user) return false;
  const perms = user.permissions || [];
  if (perms.includes("*")) return true;
  if (perms.includes(required)) return true;
  if (required.includes(":")) {
    const [resource] = required.split(":");
    if (perms.includes(`${resource}:*`)) return true;
  }
  return false;
}

export function hasRole(user: AuthUser | null, ...roles: Role[]): boolean {
  return !!user && roles.includes(user.role);
}

export function isAdmin(user: AuthUser | null): boolean {
  return hasRole(user, "super_admin", "admin_tenant");
}

/**
 * Catálogo de permissions usadas no frontend. Mantém o set sincronizado com
 * ROLE_PERMISSIONS no backend. Auxilia também a UI de criação de perfil
 * quando o admin quer escolher permissions sem ler `/api/profiles/permissions`.
 */
export const KNOWN_PERMISSIONS = [
  "patients:read",
  "patients:write",
  "patients:delete",
  "events:read",
  "events:write",
  "reports:read",
  "reports:write",
  "caregivers:read",
  "caregivers:write",
  "teleconsulta:read",
  "teleconsulta:create",
  "teleconsulta:sign",
  "medications:read",
  "medications:write",
  "medications:prescribe",
  "medications:confirm",
  "alerts:read",
  "alerts:resolve",
  "users:read",
  "users:write",
  "profiles:read",
  "profiles:write",
  "tenant:read",
  "tenant:write",
  "audit:read",
  "soap:read",
  "soap:write",
  "vital_signs:read",
  "vital_signs:write",
] as const;
