"use client";

import { useEffect, useState } from "react";
import {
  Camera,
  CheckCircle2,
  KeyRound,
  Loader2,
  Save,
  ShieldCheck,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { api } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/permissions";

// ═══════════════════════════════════════════════════════════════
// /perfil — usuário gerencia próprio perfil + senha + avatar
// ═══════════════════════════════════════════════════════════════

export default function PerfilPage() {
  const { user, refresh } = useAuth();

  if (!user) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        Carregando perfil...
      </div>
    );
  }

  return (
    <div className="max-w-3xl space-y-6">
      <header>
        <h1 className="text-xl font-semibold">Meu perfil</h1>
        <p className="text-xs text-muted-foreground mt-1">
          Atualize seus dados, foto e senha. As alterações ficam registradas
          no log de auditoria.
        </p>
      </header>

      <ProfileCard onSaved={refresh} />
      <PasswordCard />
      <AccountInfoCard />
    </div>
  );
}

function ProfileCard({ onSaved }: { onSaved: () => void }) {
  const { user } = useAuth();
  const [fullName, setFullName] = useState(user?.fullName || "");
  const [phone, setPhone] = useState(user?.phone || "");
  const [saving, setSaving] = useState(false);
  const [savedFlash, setSavedFlash] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [avatarUploading, setAvatarUploading] = useState(false);

  useEffect(() => {
    setFullName(user?.fullName || "");
    setPhone(user?.phone || "");
  }, [user]);

  if (!user) return null;

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      await api.updateUser(user!.id, { fullName, phone });
      onSaved();
      setSavedFlash(true);
      setTimeout(() => setSavedFlash(false), 1500);
    } catch (err: any) {
      setError(err?.message || "Não foi possível salvar.");
    } finally {
      setSaving(false);
    }
  }

  async function handleAvatar(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 4 * 1024 * 1024) {
      setError("Imagem muito grande (máx 4MB).");
      return;
    }
    setAvatarUploading(true);
    setError(null);
    try {
      const dataUrl = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result as string);
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });
      await api.uploadAvatar(user!.id, dataUrl);
      onSaved();
    } catch (err: any) {
      setError(err?.message || "Falha no upload.");
    } finally {
      setAvatarUploading(false);
    }
  }

  const initials = (user.fullName || user.email)
    .split(" ")
    .map((p) => p[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <form
      onSubmit={handleSave}
      className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-5 space-y-5"
    >
      <h2 className="text-sm font-semibold flex items-center gap-2">
        Identificação
        {savedFlash && (
          <span className="flex items-center gap-1 text-classification-routine text-xs font-normal">
            <CheckCircle2 className="h-3 w-3" /> salvo
          </span>
        )}
      </h2>

      <div className="flex items-start gap-5">
        <label className="cursor-pointer group" title="Trocar foto">
          {user.avatarUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={user.avatarUrl}
              alt={user.fullName}
              className="w-20 h-20 rounded-full object-cover border-2 border-white/10 group-hover:border-accent-cyan/50 transition-colors"
            />
          ) : (
            <div className="w-20 h-20 rounded-full bg-gradient-to-br from-accent-cyan/30 to-accent-teal/30 border-2 border-white/10 flex items-center justify-center text-lg font-bold group-hover:border-accent-cyan/50 transition-colors">
              {initials || "?"}
            </div>
          )}
          <div className="mt-2 flex items-center justify-center gap-1 text-[10px] text-muted-foreground">
            {avatarUploading ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Camera className="h-3 w-3" />
            )}
            <span>Trocar</span>
          </div>
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="hidden"
            onChange={handleAvatar}
            disabled={avatarUploading}
          />
        </label>

        <div className="flex-1 grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Nome completo">
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="input"
              required
            />
          </Field>
          <Field label="Telefone">
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="(51) 99999-0000"
              className="input"
            />
          </Field>
          <Field label="Email" hint="Falar com admin para alterar">
            <input
              type="email"
              value={user.email}
              disabled
              className="input opacity-60 cursor-not-allowed"
            />
          </Field>
          <Field label="Papel">
            <input
              type="text"
              value={ROLE_LABEL[user.role] || user.role}
              disabled
              className="input opacity-60 cursor-not-allowed"
            />
          </Field>
          {(user.crmRegister || user.corenRegister) && (
            <Field label="Registro profissional">
              <input
                type="text"
                value={user.crmRegister || user.corenRegister || ""}
                disabled
                className="input opacity-60 cursor-not-allowed"
              />
            </Field>
          )}
          {user.partnerOrg && (
            <Field label="Organização parceira">
              <input
                type="text"
                value={user.partnerOrg}
                disabled
                className="input opacity-60 cursor-not-allowed"
              />
            </Field>
          )}
        </div>
      </div>

      {error && (
        <div className="text-xs text-classification-attention">{error}</div>
      )}

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 rounded-lg accent-gradient text-slate-900 font-medium text-sm shadow-glow-cyan disabled:opacity-50"
        >
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          Salvar
        </button>
      </div>
    </form>
  );
}

function PasswordCard() {
  const { logout } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (next.length < 8) {
      setError("A nova senha deve ter pelo menos 8 caracteres.");
      return;
    }
    if (next !== confirm) {
      setError("Confirmação não bate com a nova senha.");
      return;
    }
    setSaving(true);
    try {
      await api.changePassword(current, next);
      setDone(true);
      // Por segurança, fazemos logout pra forçar re-login com a nova senha
      // e descartar refresh tokens antigos.
      setTimeout(() => logout(), 1500);
    } catch (err: any) {
      setError(err?.reason === "invalid_current_password"
        ? "Senha atual incorreta."
        : err?.message || "Falha ao trocar senha.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-5 space-y-4"
    >
      <h2 className="text-sm font-semibold flex items-center gap-2">
        <KeyRound className="h-4 w-4" />
        Senha
      </h2>

      {done ? (
        <div className="text-xs text-classification-routine flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4" />
          Senha alterada. Você será desconectado em instantes.
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Field label="Senha atual">
            <input
              type="password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              autoComplete="current-password"
              className="input"
              required
            />
          </Field>
          <Field label="Nova senha (mín. 8)">
            <input
              type="password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              autoComplete="new-password"
              className="input"
              required
            />
          </Field>
          <Field label="Repetir nova senha">
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
              className="input"
              required
            />
          </Field>
        </div>
      )}

      {error && (
        <div className="text-xs text-classification-attention">{error}</div>
      )}

      {!done && (
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-white/[0.05] hover:bg-white/[0.08] text-sm border border-white/[0.08] disabled:opacity-50"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <KeyRound className="h-4 w-4" />}
            Trocar senha
          </button>
        </div>
      )}
    </form>
  );
}

function AccountInfoCard() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-5 space-y-3">
      <h2 className="text-sm font-semibold flex items-center gap-2">
        <ShieldCheck className="h-4 w-4 text-classification-routine" />
        Conta e segurança
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
        <InfoRow label="Tenant" value={user.tenantId} />
        <InfoRow
          label="MFA"
          value={user.mfaEnabled ? "Ativo" : "Desativado"}
          accent={user.mfaEnabled ? "ok" : "warn"}
        />
        <InfoRow label="ID" value={user.id} mono />
        <InfoRow
          label="Permissões efetivas"
          value={`${user.permissions.length} permission${user.permissions.length === 1 ? "" : "s"}`}
        />
      </div>
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      {children}
      {hint && <span className="block text-[10px] text-muted-foreground/70">{hint}</span>}
    </label>
  );
}

function InfoRow({
  label,
  value,
  mono,
  accent,
}: {
  label: string;
  value: string;
  mono?: boolean;
  accent?: "ok" | "warn";
}) {
  const color =
    accent === "ok"
      ? "text-classification-routine"
      : accent === "warn"
      ? "text-classification-attention"
      : "text-foreground";
  return (
    <div className="flex items-center justify-between gap-2 border-b border-white/[0.04] pb-2">
      <span className="text-muted-foreground">{label}</span>
      <span className={`${color} ${mono ? "font-mono text-[10px]" : ""} truncate`}>
        {value}
      </span>
    </div>
  );
}
