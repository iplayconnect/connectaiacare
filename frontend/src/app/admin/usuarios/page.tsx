"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Loader2,
  Plus,
  Search,
  ShieldCheck,
  Trash2,
  UserCog,
  UserPlus,
  X,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { api, type ProfileRecord } from "@/lib/api";
import type { AuthUser, Role } from "@/lib/auth";
import { ROLE_LABEL, hasRole } from "@/lib/permissions";

// ═══════════════════════════════════════════════════════════════
// /admin/usuarios — admin lista, cria, edita, desativa usuários
// ═══════════════════════════════════════════════════════════════

const ROLES: Role[] = [
  "admin_tenant",
  "medico",
  "enfermeiro",
  "cuidador_pro",
  "familia",
  "parceiro",
  "super_admin",
];

export default function AdminUsuariosPage() {
  const { user } = useAuth();
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [profiles, setProfiles] = useState<ProfileRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [includeInactive, setIncludeInactive] = useState(false);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<AuthUser | null>(null);

  const isAdmin = hasRole(user, "super_admin", "admin_tenant");

  const reload = async () => {
    setLoading(true);
    setError(null);
    try {
      const [u, p] = await Promise.all([
        api.listUsers(includeInactive),
        api.listProfiles().catch(() => ({ profiles: [] as ProfileRecord[] })),
      ]);
      setUsers(u.users);
      setProfiles(p.profiles || []);
    } catch (err: any) {
      setError(err?.message || "Falha ao carregar usuários.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isAdmin) reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin, includeInactive]);

  const filtered = useMemo(() => {
    if (!search.trim()) return users;
    const q = search.trim().toLowerCase();
    return users.filter(
      (u) =>
        u.email.toLowerCase().includes(q) ||
        (u.fullName || "").toLowerCase().includes(q) ||
        (u.role || "").toLowerCase().includes(q),
    );
  }, [users, search]);

  if (!isAdmin) {
    return (
      <div className="rounded-xl border border-classification-attention/20 bg-classification-attention/5 p-6 text-center">
        <ShieldCheck className="h-8 w-8 mx-auto text-classification-attention mb-2" />
        <h2 className="text-sm font-semibold">Acesso restrito</h2>
        <p className="text-xs text-muted-foreground mt-1">
          Apenas admins do tenant ou super_admin podem gerenciar usuários.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-5 max-w-6xl">
      <header className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold">Usuários</h1>
          <p className="text-xs text-muted-foreground mt-1">
            Gestão de equipe, parceiros e acesso ao CRM. Cada conta deixa
            rastro completo no log de auditoria.
          </p>
        </div>
        <button
          onClick={() => setCreating(true)}
          className="flex items-center gap-2 px-3 py-2 rounded-lg accent-gradient text-slate-900 text-sm font-medium shadow-glow-cyan hover:brightness-110"
        >
          <UserPlus className="h-4 w-4" />
          Novo usuário
        </button>
      </header>

      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[240px] max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por nome, email ou papel"
            className="input pl-9"
          />
        </div>
        <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
          <input
            type="checkbox"
            checked={includeInactive}
            onChange={(e) => setIncludeInactive(e.target.checked)}
            className="accent-accent-cyan"
          />
          Mostrar inativos
        </label>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-classification-attention/10 border border-classification-attention/20 text-xs text-classification-attention">
          <AlertCircle className="h-4 w-4" /> {error}
        </div>
      )}

      <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] overflow-hidden">
        <table className="w-full text-xs">
          <thead className="text-muted-foreground bg-white/[0.02]">
            <tr>
              <th className="text-left px-4 py-3 font-medium">Nome</th>
              <th className="text-left px-4 py-3 font-medium">Email</th>
              <th className="text-left px-4 py-3 font-medium">Papel</th>
              <th className="text-left px-4 py-3 font-medium">Status</th>
              <th className="text-left px-4 py-3 font-medium">Último acesso</th>
              <th className="text-right px-4 py-3 font-medium">Ações</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={6} className="px-4 py-12 text-center text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin inline mr-2" />
                  Carregando...
                </td>
              </tr>
            )}
            {!loading && filtered.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-12 text-center text-muted-foreground">
                  Nenhum usuário encontrado.
                </td>
              </tr>
            )}
            {!loading &&
              filtered.map((u) => (
                <tr
                  key={u.id}
                  className="border-t border-white/[0.04] hover:bg-white/[0.02]"
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2.5">
                      {u.avatarUrl ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={u.avatarUrl}
                          alt={u.fullName}
                          className="w-7 h-7 rounded-full object-cover border border-white/10"
                        />
                      ) : (
                        <div className="w-7 h-7 rounded-full bg-gradient-to-br from-accent-cyan/30 to-accent-teal/30 border border-white/10 flex items-center justify-center text-[10px] font-bold">
                          {(u.fullName || u.email).slice(0, 2).toUpperCase()}
                        </div>
                      )}
                      <span className="font-medium">{u.fullName}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{u.email}</td>
                  <td className="px-4 py-3">
                    <span className="px-2 py-0.5 rounded bg-white/[0.05] text-[10px] uppercase tracking-wider">
                      {ROLE_LABEL[u.role] || u.role}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {(u as any).active === false ? (
                      <span className="text-classification-attention">Inativo</span>
                    ) : (
                      <span className="text-classification-routine">Ativo</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {(u as any).lastLoginAt
                      ? new Date((u as any).lastLoginAt).toLocaleString("pt-BR")
                      : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => setEditing(u)}
                        className="p-1.5 rounded hover:bg-white/[0.05]"
                        title="Editar"
                      >
                        <UserCog className="h-3.5 w-3.5" />
                      </button>
                      {(u as any).active !== false && u.id !== user?.id && (
                        <button
                          onClick={async () => {
                            if (!confirm(`Desativar ${u.fullName}?`)) return;
                            await api.deleteUser(u.id);
                            reload();
                          }}
                          className="p-1.5 rounded hover:bg-classification-attention/10 text-classification-attention"
                          title="Desativar"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {creating && (
        <UserModal
          mode="create"
          profiles={profiles}
          onClose={() => setCreating(false)}
          onSaved={() => {
            setCreating(false);
            reload();
          }}
        />
      )}
      {editing && (
        <UserModal
          mode="edit"
          user={editing}
          profiles={profiles}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            reload();
          }}
        />
      )}
    </div>
  );
}

// ─── Modal de criar/editar ─────────────────────────────────

function UserModal({
  mode,
  user,
  profiles,
  onClose,
  onSaved,
}: {
  mode: "create" | "edit";
  user?: AuthUser;
  profiles: ProfileRecord[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { user: requester } = useAuth();
  const isSuper = requester?.role === "super_admin";

  const [fullName, setFullName] = useState(user?.fullName || "");
  const [email, setEmail] = useState(user?.email || "");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>(user?.role || "cuidador_pro");
  const [profileId, setProfileId] = useState<string | "">(user?.profileId || "");
  const [phone, setPhone] = useState(user?.phone || "");
  const [crm, setCrm] = useState(user?.crmRegister || "");
  const [coren, setCoren] = useState(user?.corenRegister || "");
  const [partnerOrg, setPartnerOrg] = useState(user?.partnerOrg || "");
  const [active, setActive] = useState(user?.id ? (user as any).active !== false : true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      if (mode === "create") {
        if (password.length < 8) {
          setError("Senha deve ter ao menos 8 caracteres.");
          setSaving(false);
          return;
        }
        await api.createUser({
          email,
          fullName,
          password,
          role,
          profileId: profileId || undefined,
          phone: phone || undefined,
          crmRegister: crm || undefined,
          corenRegister: coren || undefined,
          partnerOrg: partnerOrg || undefined,
          passwordChangeRequired: true,
        });
      } else if (user) {
        await api.updateUser(user.id, {
          fullName,
          phone,
          role,
          profileId: profileId || null,
          crmRegister: crm,
          corenRegister: coren,
          partnerOrg,
          active,
        });
      }
      onSaved();
    } catch (err: any) {
      const reason = err?.reason;
      if (reason === "email_already_exists")
        setError("Já existe usuário com esse email.");
      else if (reason === "password_too_short")
        setError("Senha deve ter ao menos 8 caracteres.");
      else if (reason === "invalid_role")
        setError("Papel inválido.");
      else setError(err?.message || "Falha ao salvar.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <form
        onSubmit={handleSubmit}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-xl border border-white/[0.08] bg-[hsl(225,80%,8%)] p-6 space-y-5"
      >
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold">
            {mode === "create" ? "Novo usuário" : `Editar ${user?.fullName}`}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded hover:bg-white/[0.05]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Nome completo" required>
            <input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="input"
              required
            />
          </Field>
          <Field label="Email" required hint={mode === "edit" ? "Não editável" : undefined}>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="input"
              required
              disabled={mode === "edit"}
            />
          </Field>
          {mode === "create" && (
            <Field label="Senha inicial (mín 8)" required>
              <input
                type="text"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input font-mono"
                required
              />
            </Field>
          )}
          <Field label="Papel" required>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as Role)}
              className="input"
            >
              {ROLES.filter((r) => r !== "super_admin" || isSuper).map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABEL[r]}
                </option>
              ))}
            </select>
          </Field>
          <Field
            label="Perfil customizado"
            hint="Opcional — sobrescreve as permissions do papel."
          >
            <select
              value={profileId}
              onChange={(e) => setProfileId(e.target.value)}
              className="input"
            >
              <option value="">Sem perfil custom</option>
              {profiles.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.displayName}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Telefone">
            <input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="input"
            />
          </Field>
          <Field label="CRM">
            <input
              value={crm}
              onChange={(e) => setCrm(e.target.value)}
              placeholder="ex: 12345/RS"
              className="input"
            />
          </Field>
          <Field label="COREN">
            <input
              value={coren}
              onChange={(e) => setCoren(e.target.value)}
              placeholder="ex: RS-987654"
              className="input"
            />
          </Field>
          <Field label="Organização (parceiro)">
            <input
              value={partnerOrg}
              onChange={(e) => setPartnerOrg(e.target.value)}
              placeholder="ex: Tecnosenior"
              className="input"
            />
          </Field>
          {mode === "edit" && (
            <Field label="Status">
              <label className="flex items-center gap-2 text-xs px-3 py-2 rounded-lg bg-white/[0.04] border border-white/[0.08]">
                <input
                  type="checkbox"
                  checked={active}
                  onChange={(e) => setActive(e.target.checked)}
                  className="accent-accent-cyan"
                />
                Conta ativa
              </label>
            </Field>
          )}
        </div>

        {error && (
          <div className="text-xs text-classification-attention flex items-center gap-2">
            <AlertCircle className="h-4 w-4" /> {error}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2 border-t border-white/[0.04]">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-2 text-xs rounded-lg hover:bg-white/[0.04]"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2 rounded-lg accent-gradient text-slate-900 text-sm font-medium shadow-glow-cyan disabled:opacity-50"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            {mode === "create" ? "Criar" : "Salvar"}
          </button>
        </div>
      </form>
    </div>
  );
}

function Field({
  label,
  required,
  hint,
  children,
}: {
  label: string;
  required?: boolean;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1">
      <span className="text-[11px] text-muted-foreground">
        {label}
        {required && <span className="text-classification-attention ml-0.5">*</span>}
      </span>
      {children}
      {hint && (
        <span className="block text-[10px] text-muted-foreground/70">{hint}</span>
      )}
    </label>
  );
}
