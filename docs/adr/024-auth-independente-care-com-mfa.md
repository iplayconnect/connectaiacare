# ADR-024 — Autenticação independente da Care (M&A-ready) com MFA + compliance reforçado

**Status**: Aceito
**Data**: 22/04/2026
**Decisores**: Alexandre (CEO), Claude Code (engenharia), Opus Desktop (arquitetura)

---

## Contexto

ConnectaIACare foi concebida para ter stack técnica isolada da ConnectaIA comercial
(ADR-001, ADR-003: DB separado). O usuário considerou brevemente a possibilidade
de SSO entre as duas plataformas (reaproveitar a tela de login da ConnectaIA),
mas a análise levantou questões:

1. **M&A-readiness**: se no futuro um grande grupo quiser investir em / comprar
   a ConnectaIACare, ela precisa ser **um ativo inteiro e independente**. SSO
   com ConnectaIA comercial criaria acoplamento que teria que ser desfeito no
   carve-out — red flag em due diligence.
2. **LGPD Art. 11 (dado sensível de saúde)**: compartilhar tabela de usuários
   entre saúde e comercial enfraquece o argumento de isolamento físico que
   justificou DB separado.
3. **Segurança por layer**: autenticação em saúde exige camadas mais pesadas
   (MFA, password rotation, session TTL curto) que em SaaS comercial.

Por outro lado, reconstruir auth do zero é trabalho desnecessário. A ConnectaIA
já tem sistema maduro de login que pode ser **copiado e evoluído**, não
referenciado.

---

## Decisão

**ConnectaIACare terá sistema de autenticação próprio, independente,
operacionalmente isolado da ConnectaIA comercial, com camadas extras de
segurança apropriadas ao contexto de saúde.**

Estratégia de desenvolvimento: **fork lógico** — copiar código da ConnectaIA
(tela, schema, handlers) para dentro do repositório ConnectaIACare, adaptar
pro contexto healthcare, e evoluir independentemente a partir daí.

### Camadas de segurança adicionais (vs ConnectaIA comercial)

1. **MFA obrigatório** para perfis de acesso a dados clínicos:
   - Médicos (obrigatório, sem exceção)
   - Gestores de SPA/hospital (obrigatório)
   - Admins + equipe Atente (obrigatório)
   - Recepção/operadores apenas-leitura: opcional na v1, obrigatório fase 2

   Método: TOTP via Google Authenticator, Authy ou similar. **Sem SMS** —
   SIM-swap é vetor conhecido.

2. **Password policy reforçada**:
   - Mínimo 12 caracteres (vs 8 na comercial)
   - Pelo menos 1 maiúscula + 1 minúscula + 1 dígito + 1 especial
   - Verificação contra HaveIBeenPwned API (senha vazada = bloqueia cadastro)
   - Rotação obrigatória a cada **90 dias** para médicos e gestores
   - Proibição de reuso das últimas 5 senhas

3. **Session TTL agressivo**:
   - Session ativa: **30 minutos de inatividade** (vs 4h na comercial)
   - Session absoluta: **8 horas** (vs 24h na comercial)
   - Força logout ao fechar aba (session cookie, não persistent) para perfis
     com dados clínicos
   - Refresh token rotativo (one-time use)

4. **Rate limiting severo**:
   - Login: 5 tentativas / 5 minutos antes de lockout
   - Reset de senha: 3 tentativas / 15 minutos
   - MFA: 3 códigos errados → bloqueio 10 minutos + alerta email + Atente
   - Lockout geral: 30 min após limite atingido

5. **Trusted devices**:
   - Primeiro login em novo device: exige email + MFA
   - Device "confiável" tem fingerprint (user-agent + IP range + cookie
     persistente assinado) por 30 dias
   - Lista de devices visível e revogável pelo usuário

6. **Backup codes** (obrigatório quando ativar MFA):
   - 10 códigos one-time gerados ao cadastrar MFA
   - Armazenados em hash (bcrypt)
   - Cada código uso único
   - Usuário pode regerar, mas os antigos invalidam

7. **Audit trail completo** (LGPD Art. 37):
   - Login, logoff, failed attempts, privilege escalation
   - **Acesso a prontuário**: registra user + patient_id + timestamp + IP
   - **Modificação de prescrição**: diff completo (antes/depois) + user
   - Exportável em JSON/CSV pra auditoria

8. **LGPD right-to-forget nativo**:
   - Campo `erased_at TIMESTAMPTZ` em `care_users`
   - Identificador não-reversível: hash SHA-256 de CPF, não o CPF em claro
   - Soft delete + scrub de PII em 30 dias da solicitação
   - `personal_data` JSONB com campos que podem ser apagados sem quebrar
     integridade referencial (logs mantêm user_id mas sem nome/email)

9. **HTTPS-only + HSTS preload**:
   - ConnectaIACare.com.br já no HSTS preload list
   - Strict-Transport-Security max-age=63072000; includeSubDomains; preload
   - Cookies com `Secure`, `HttpOnly`, `SameSite=Strict`

10. **Separação de perfis com RBAC granular**:
    - `medico`: acesso a prontuário + prescrição + teleconsulta
    - `enfermeiro`: acesso a prontuário + escalação (não prescreve)
    - `gestor_spa`: dashboard agregado + relatórios (sem PHI individual por padrão)
    - `cuidador_familiar` (B2C): acesso limitado ao próprio paciente
    - `atente_operador`: pode acessar qualquer paciente em escalação ativa
    - `admin`: gestão de usuários + billing (sem PHI por padrão)
    - `super_admin`: auditoria + configurações platform-wide

---

## Schema (migration 010)

```sql
-- Usuários da plataforma Care (separado de tudo)
CREATE TABLE aia_health_platform_users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL,
    
    email CITEXT UNIQUE NOT NULL,
    cpf_hash TEXT UNIQUE,                      -- hash SHA-256, não CPF em claro
    password_hash TEXT NOT NULL,               -- bcrypt cost 12
    password_set_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    password_history JSONB DEFAULT '[]'::jsonb,  -- últimos 5 hashes
    
    full_name TEXT NOT NULL,
    phone TEXT,
    role TEXT NOT NULL,                        -- medico/enfermeiro/gestor_spa/...
    crm_number TEXT,                           -- se role=medico
    crm_state TEXT,
    specialties TEXT[],
    
    -- MFA
    mfa_required BOOLEAN NOT NULL DEFAULT FALSE,
    mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    mfa_secret TEXT,                           -- encrypted TOTP seed
    mfa_backup_codes JSONB,                    -- array de hashes
    
    -- Estado
    active BOOLEAN NOT NULL DEFAULT TRUE,
    locked_until TIMESTAMPTZ,
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    
    -- LGPD
    consent_version TEXT,
    consent_signed_at TIMESTAMPTZ,
    erased_at TIMESTAMPTZ,
    personal_data JSONB,                       -- campos apagáveis
    
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ON aia_health_platform_users(tenant_id);
CREATE INDEX ON aia_health_platform_users(active, erased_at) WHERE erased_at IS NULL;

-- Sessões (refresh tokens, não JWT stateless)
CREATE TABLE aia_health_platform_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES aia_health_platform_users(id) ON DELETE CASCADE,
    
    refresh_token_hash TEXT NOT NULL,
    access_token_jti TEXT,
    
    ip_address INET,
    user_agent TEXT,
    device_fingerprint TEXT,                   -- trusted device
    is_trusted_device BOOLEAN NOT NULL DEFAULT FALSE,
    
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    revoked_reason TEXT,
    
    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ON aia_health_platform_sessions(user_id, expires_at);
CREATE INDEX ON aia_health_platform_sessions(refresh_token_hash);

-- Audit log de autenticação (LGPD Art. 37)
CREATE TABLE aia_health_auth_audit_log (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES aia_health_platform_users(id) ON DELETE SET NULL,
    user_email_at_time TEXT,                   -- snapshot (pra audit mesmo após erase)
    
    action TEXT NOT NULL CHECK (action IN (
        'login_success', 'login_failed', 'logout',
        'password_reset_requested', 'password_reset_completed',
        'mfa_enabled', 'mfa_disabled', 'mfa_challenge_passed', 'mfa_challenge_failed',
        'session_revoked', 'session_expired',
        'account_locked', 'account_unlocked',
        'privilege_escalation', 'patient_chart_accessed', 'prescription_modified'
    )),
    
    ip_address INET,
    user_agent TEXT,
    device_fingerprint TEXT,
    metadata JSONB,                            -- detalhes específicos por ação
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ON aia_health_auth_audit_log(user_id, created_at DESC);
CREATE INDEX ON aia_health_auth_audit_log(action, created_at DESC);
CREATE INDEX ON aia_health_auth_audit_log(created_at DESC);  -- query SIEM

-- Trusted devices (opcional — evita MFA toda vez)
CREATE TABLE aia_health_trusted_devices (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES aia_health_platform_users(id) ON DELETE CASCADE,
    
    fingerprint TEXT NOT NULL UNIQUE,
    name TEXT,                                 -- "Celular pessoal"
    user_agent_sample TEXT,
    ip_network CIDR,
    
    trusted_until TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    
    last_seen_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## Fluxos principais

### Login + MFA

```
1. POST /auth/login { email, password }
   → bcrypt.verify + check failed_login_attempts
   → se ok + mfa_enabled: retorna { mfa_challenge_id, expires_in: 300 }
   → se ok + sem mfa + mfa_required: força cadastro MFA primeiro
   → se ok + sem mfa: emite sessão direto

2. POST /auth/mfa/verify { challenge_id, code }
   → TOTP verify (tolera ±1 janela de 30s)
   → emite sessão: { access_token JWT 30min, refresh_token 8h (httpOnly cookie) }
   → grava em sessions table + audit log

3. GET /api/protected
   → middleware: valida JWT
   → se passou 25min sem request → pede refresh
   → refresh rotativo: descarta refresh_token usado, emite novo
```

### Password reset

```
1. POST /auth/password-reset { email }
   → gera reset_token (random 32 bytes), armazena hash + TTL 15min
   → envia email com link https://care.../reset?token=XXX
   → rate-limit: 3 por IP / 15min

2. POST /auth/password-reset/confirm { token, new_password }
   → valida hash + expires_at
   → checa HaveIBeenPwned (new_password não pode estar em breach known)
   → checa password_history (não reusar últimas 5)
   → bcrypt hash + atualiza + audit
   → revoga TODAS as sessões ativas do usuário
```

### Acesso a prontuário (auditado)

```
1. GET /api/patients/{id}/chart
   → middleware valida JWT + role
   → middleware grava em auth_audit_log:
       action='patient_chart_accessed', user_id, patient_id, IP, UA
   → retorna dados conforme RBAC (gestor_spa não vê PHI individual, médico vê)
```

---

## Bibliotecas

Backend Python:
- `passlib[bcrypt]` — já temos, cost 12
- `pyotp` — TOTP (ou `twofactor` alternativa)
- `cryptography` — criptografia do mfa_secret at-rest
- `pyhibp` ou request direto à HaveIBeenPwned API
- `python-jose` — JWT (já temos)

Frontend Next.js:
- Tela de login inspirada na ConnectaIA mas tema Care (cyan/teal)
- Tela de MFA setup com QR code gerado server-side
- Tela de "backup codes — imprima agora"
- Banner de "sessão expira em N minutos" quando falta 5min

---

## Trade-offs

**Ganho**:
- Sistema M&A-ready (ativo isolado, vendível)
- Compliance HIPAA-like + LGPD Art. 11 defensável
- Segurança alinhada com expectativas do mercado healthcare
- Audit trail exportável pra ANS/CFM se solicitado

**Custo**:
- ~2-3 semanas de engenharia pra implementar do zero (copy+adapt)
- Overhead operacional (suporte a MFA, reset)
- UX levemente mais pesada (MFA em todo device novo, session curta)

**Mitigação do custo UX**:
- Trusted device 30 dias → usuário quase sempre não precisa MFA
- "Lembrar-me neste dispositivo" checkbox
- MFA via app mobile ConnectaIACare (future: push notifications)

---

## Métricas de sucesso

- 100% dos médicos com MFA ativo em 60 dias pós-launch
- <2% taxa de lockout por semana (ajustar rate-limit se maior)
- <5min tempo médio de recuperação de senha
- Zero incidentes de credenciais vazadas por SIM-swap (validação do "sem SMS")

---

## Próximos passos

- Migration 010 (schemas acima)
- Implementação backend (~1 semana)
- Implementação frontend (~1 semana)
- Smoke test + pentest interno
- Rollout para equipe interna primeiro, depois médicos parceiros, depois B2C

---

## Referências

- NIST SP 800-63B (Authentication Guidelines)
- CFM 2.314/2022 (Teleconsulta + identidade digital)
- LGPD Art. 11 + Art. 37 (dado sensível + registro de operações)
- OWASP ASVS 4.0.3 (Authentication Verification Standard)
- HaveIBeenPwned API (k-anonymity range queries)
