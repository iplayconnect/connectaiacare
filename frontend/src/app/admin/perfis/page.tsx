"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Check,
  KeyRound,
  Loader2,
  Plus,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { api, type ProfileRecord } from "@/lib/api";
import { hasRole } from "@/lib/permissions";

// ═══════════════════════════════════════════════════════════════
// /admin/perfis — Bloco C: perfis customizáveis com permissions
//
// Admin cria perfis (ex: "supervisor noturno") com checkboxes do catálogo
// vindo de GET /api/profiles/permissions. Atribui o perfil ao usuário em
// /admin/usuarios → o profile.permissions sobrescreve o role default.
// ═══════════════════════════════════════════════════════════════

export default function AdminPerfisPage() {
  const { user } = useAuth();
  const [profiles, setProfiles] = useState<ProfileRecord[]>([]);
  const [permissionsCatalog, setPermissionsCatalog] =
    useState<Record<string, string[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<ProfileRecord | null>(null);
  const [creating, setCreating] = useState(false);

  const isAdmin = hasRole(user, "super_admin", "admin_tenant");

  const reload = async () => {
    setLoading(true);
    setError(null);
    try {
      const [list, catalog] = await Promise.all([
        api.listProfiles(),
        api.listAvailablePermissions(),
      ]);
      setProfiles(list.profiles);
      setPermissionsCatalog(catalog.groups || {});
    } catch (err: any) {
      setError(err?.message || "Falha ao carregar perfis.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isAdmin) reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin]);

  if (!isAdmin) {
    return (
      <div className="rounded-xl border border-classification-attention/20 bg-classification-attention/5 p-6 text-center">
        <ShieldCheck className="h-8 w-8 mx-auto text-classification-attention mb-2" />
        <h2 className="text-sm font-semibold">Acesso restrito</h2>
        <p className="text-xs text-muted-foreground mt-1">
          Apenas admins do tenant ou super_admin podem gerenciar perfis.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-5 max-w-5xl">
      <header className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold">Perfis customizados</h1>
          <p className="text-xs text-muted-foreground mt-1">
            Crie perfis com listas de permissões específicas. Quando um perfil
            é vinculado a um usuário, suas permissões sobrescrevem as do papel
            padrão.
          </p>
        </div>
        <button
          onClick={() => setCreating(true)}
          className="flex items-center gap-2 px-3 py-2 rounded-lg accent-gradient text-slate-900 text-sm font-medium shadow-glow-cyan hover:brightness-110"
        >
          <Plus className="h-4 w-4" />
          Novo perfil
        </button>
      </header>

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-classification-attention/10 border border-classification-attention/20 text-xs text-classification-attention">
          <AlertCircle className="h-4 w-4" /> {error}
        </div>
      )}

      <div className="grid gap-3">
        {loading && (
          <div className="text-center py-12 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin inline mr-2" />
            Carregando...
          </div>
        )}
        {!loading && profiles.length === 0 && (
          <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-8 text-center">
            <KeyRound className="h-8 w-8 mx-auto text-muted-foreground mb-2" />
            <p className="text-sm">Nenhum perfil customizado ainda.</p>
            <p className="text-xs text-muted-foreground mt-1">
              Os usuários estão usando os papéis padrão. Crie um perfil pra
              ajustar permissões mais finas.
            </p>
          </div>
        )}
        {!loading &&
          profiles.map((p) => (
            <ProfileCard
              key={p.id}
              profile={p}
              onEdit={() => setEditing(p)}
              onDelete={async () => {
                if (!confirm(`Desativar perfil "${p.displayName}"?`)) return;
                await api.deleteProfile(p.id);
                reload();
              }}
            />
          ))}
      </div>

      {(editing || creating) && (
        <ProfileModal
          profile={editing}
          permissionsCatalog={permissionsCatalog}
          onClose={() => {
            setEditing(null);
            setCreating(false);
          }}
          onSaved={() => {
            setEditing(null);
            setCreating(false);
            reload();
          }}
        />
      )}
    </div>
  );
}

function ProfileCard({
  profile,
  onEdit,
  onDelete,
}: {
  profile: ProfileRecord;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4 space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-sm">{profile.displayName}</span>
            <code className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.06] text-muted-foreground">
              {profile.slug}
            </code>
          </div>
          {profile.description && (
            <p className="text-xs text-muted-foreground mt-1">
              {profile.description}
            </p>
          )}
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <button
            onClick={onEdit}
            className="px-2.5 py-1 text-xs rounded hover:bg-white/[0.05]"
          >
            Editar
          </button>
          <button
            onClick={onDelete}
            className="p-1.5 rounded hover:bg-classification-attention/10 text-classification-attention"
            title="Desativar"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5 pt-2 border-t border-white/[0.04]">
        {profile.permissions.length === 0 && (
          <span className="text-[10px] text-muted-foreground italic">
            Sem permissions
          </span>
        )}
        {profile.permissions.map((p) => (
          <span
            key={p}
            className="text-[10px] px-1.5 py-0.5 rounded bg-accent-cyan/10 border border-accent-cyan/20 text-accent-cyan font-mono"
          >
            {p}
          </span>
        ))}
      </div>
    </div>
  );
}

function ProfileModal({
  profile,
  permissionsCatalog,
  onClose,
  onSaved,
}: {
  profile: ProfileRecord | null;
  permissionsCatalog: Record<string, string[]>;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = !!profile;
  const [slug, setSlug] = useState(profile?.slug || "");
  const [displayName, setDisplayName] = useState(profile?.displayName || "");
  const [description, setDescription] = useState(profile?.description || "");
  const [selected, setSelected] = useState<Set<string>>(
    new Set(profile?.permissions || []),
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const groupedKeys = useMemo(
    () =>
      Object.keys(permissionsCatalog).sort((a, b) => {
        if (a === "_wildcard") return -1;
        if (b === "_wildcard") return 1;
        return a.localeCompare(b);
      }),
    [permissionsCatalog],
  );

  function toggle(perm: string) {
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(perm)) n.delete(perm);
      else n.add(perm);
      return n;
    });
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      if (isEdit && profile) {
        await api.updateProfile(profile.id, {
          displayName,
          description,
          permissions: Array.from(selected),
        });
      } else {
        await api.createProfile({
          slug,
          displayName,
          description,
          permissions: Array.from(selected),
        });
      }
      onSaved();
    } catch (err: any) {
      const reason = err?.reason;
      if (reason === "slug_already_exists") setError("Slug já existe.");
      else if (reason === "invalid_slug")
        setError("Slug inválido (use letras minúsculas, números, hífen, underscore).");
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
            {isEdit ? `Editar perfil "${profile.displayName}"` : "Novo perfil"}
          </h2>
          <button type="button" onClick={onClose} className="p-1 rounded hover:bg-white/[0.05]">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <label className="block space-y-1">
            <span className="text-[11px] text-muted-foreground">Nome do perfil *</span>
            <input
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="input"
              required
            />
          </label>
          <label className="block space-y-1">
            <span className="text-[11px] text-muted-foreground">
              Slug (id técnico) *
            </span>
            <input
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              placeholder="supervisor_noturno"
              className="input font-mono"
              disabled={isEdit}
              required
            />
          </label>
        </div>
        <label className="block space-y-1">
          <span className="text-[11px] text-muted-foreground">Descrição</span>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            className="input resize-none"
          />
        </label>

        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium">Permissões</span>
            <span className="text-[10px] text-muted-foreground">
              {selected.size} selecionada{selected.size === 1 ? "" : "s"}
            </span>
          </div>
          <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
            {groupedKeys.map((group) => (
              <div key={group}>
                <div className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground mb-1.5">
                  {group === "_wildcard" ? "Acesso total" : group}
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                  {permissionsCatalog[group].map((perm) => {
                    const checked = selected.has(perm);
                    return (
                      <label
                        key={perm}
                        className={`flex items-center gap-2 px-2 py-1.5 rounded text-xs cursor-pointer border transition-colors ${
                          checked
                            ? "border-accent-cyan/30 bg-accent-cyan/5 text-accent-cyan"
                            : "border-white/[0.06] hover:bg-white/[0.03]"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggle(perm)}
                          className="accent-accent-cyan"
                        />
                        <span className="font-mono text-[10px]">{perm}</span>
                        {checked && <Check className="h-3 w-3 ml-auto" />}
                      </label>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
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
            {isEdit ? "Salvar" : "Criar"}
          </button>
        </div>
      </form>
    </div>
  );
}
