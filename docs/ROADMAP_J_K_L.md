# Roadmap J / K / L — Specs detalhados

**Data:** 2026-05-17
**Contexto:** Entregas E-H concluídas (sidebar, modais, escalation health). Próximas 3 evoluções são substantivas e exigem sessões dedicadas — este doc é o spec pra retomar quando quiser.

---

## J — Re-enrollment automático de voiceprint (90d)

### Por que importa
Voz idosa varia naturalmente: resfriado, prótese dentária mudada, medicação que afeta voz (anticolinérgicos, antipsicóticos), idade. Voiceprint cadastrado há 6 meses pode ter score baixo hoje → falso "voz não bate" → Sofia trata cuidador conhecido como desconhecido.

### Comportamento esperado
1. **Sistema detecta voiceprint > 90 dias** sem re-enrollment via scheduler diário
2. **Sofia inicia conversa proativa** com cuidador (WhatsApp): *"Oi! Faz tempo que não atualizo seu cadastro de voz. Posso pedir 3 áudios curtos pra refrescar? Demora 30s."*
3. **Se aceita** → fluxo idêntico ao enrollment inicial (3 amostras)
4. **Se recusa** → tenta de novo em 30 dias; mantém voiceprint atual
5. **Se ignora** → tenta de novo em 14 dias; alerta admin se > 180d sem atualização

### Componentes necessários

**Migration 082**:
```sql
ALTER TABLE aia_health_voice_embeddings ADD COLUMN
    last_reenrollment_offered_at TIMESTAMPTZ,
    reenrollment_attempts INTEGER NOT NULL DEFAULT 0,
    reenrollment_status TEXT;  -- 'pending' | 'accepted' | 'declined' | 'ignored'
```

**Service** `voice_reenrollment_service.py`:
- `find_stale_voiceprints(days=90)` → lista
- `propose_reenrollment(voiceprint_id)` → cria conversa Sofia
- `record_response(voiceprint_id, status)` → atualiza tracking

**Scheduler** `scripts/voice_reenrollment_cron.py`:
- Rodar 1×/dia (cron) ou via `proactive_scheduler.py` existente
- Pega N stale (limit 50/dia pra não sobrecarregar)
- Dispara `propose_reenrollment` pra cada
- Audit log centralizado

**UI Admin** `/admin/biometria-voz/reenrollment`:
- Tab nova na página `/admin/biometria-voz`
- Lista voiceprints stale + status
- Ação manual: "Propor reenrollment agora"
- Stats: % aceito / recusado / ignorado

**Esforço:** 3-4h (1h migration + service, 2h scheduler + UI, 1h testes)

---

## K — PWA install + push web

### Por que importa
WhatsApp é o canal principal de notificação P1 hoje. **Risco operacional:** se WhatsApp do plantonista falhar (sem internet, bloqueado, app desinstalado), nenhum push chega. Push web direto do browser é fallback robusto + permite **vibração** + **som customizado** + funciona em desktop.

### Comportamento esperado
1. **Plantonista abre painel** pelo browser → vê CTA "Instalar app" no canto
2. **Após install** → painel vira PWA (ícone na tela inicial, fullscreen)
3. **Após permissão** → notificações push ficam ativas mesmo com browser fechado
4. **P1 entra** → 2 canais em paralelo:
   - WhatsApp (canal principal)
   - Push web (canal redundante, mesma mensagem)
5. **Click no push** → abre direto na Central com handoff já filtrado

### Componentes necessários

**Frontend PWA**:
- `frontend/public/manifest.json` — PWA manifest com nome, icons, theme, start_url
- `frontend/public/sw.js` — service worker pra cache + push listener
- `frontend/src/components/pwa-install-prompt.tsx` — CTA install dismissable
- `frontend/src/lib/push-subscription.ts` — request permission + register endpoint

**Backend**:
- Migration 082b: `aia_health_user_push_subscriptions` (user_id, endpoint, keys, created_at)
- Endpoint `POST /api/users/me/push-subscription` — registra subscription do user
- Endpoint `DELETE /api/users/me/push-subscription` — desinscreve
- Helper `send_push_notification(user_id, title, body, url)` usando lib `pywebpush`
- Trigger no `clinical_handoff_initiated` quando user tem subscription

**VAPID keys** (one-time setup):
- Gerar par com `python -c "from pywebpush import VAPID_KEYS; print(VAPID_KEYS())"`
- Public key vai pro frontend (env `NEXT_PUBLIC_VAPID_PUBLIC_KEY`)
- Private key fica só no backend (env `VAPID_PRIVATE_KEY`)

**Esforço:** 4-5h (2h PWA base + manifest + SW, 2h push backend, 1h testes em iOS/Android)

### Trade-offs
- **iOS Safari** só suporta push web em PWA instalada (não navegador). Workaround: prompt obrigatório de install pra iOS.
- **Browsers desktop** funcionam plenamente.

---

## L — Entrega B: Onboarding de voz via WhatsApp (Sofia conduz enrollment)

### Por que importa (recap do plano original)
Hoje voiceprint é cadastrado **apenas** via UI admin (`/admin/biometria-voz`). Pra B2C (idoso solo) ou onboarding em massa de cuidadores, isso não escala — alguém precisa logar no painel.

L muda o paradigma: **Sofia inicia o enrollment via WhatsApp** assim que detecta que o phone está cadastrado mas a voz é desconhecida.

### Cenários cobertos (do `WHATSAPP_INBOUND_IDENTITY_POLICY.md`)

**Cenário 5 — Familiar/cuidador novo no celular dele próprio:**
- Phone bate com `responsible.phone` ou novo cuidador
- Voz não tem voiceprint
- Sofia: *"Oi [nome]! Vi aqui que você é [filho(a)/esposo(a)/cuidador(a)] do(a) [paciente]. Posso fazer um cadastro rápido da sua voz? Demora ~30 segundos."*
- Aceita → 3 áudios → enrollment
- Recusa → marca `voice_enrollment_offered_at` (não pergunta de novo por 30d)

### Componentes necessários

**Service** `voice_onboarding_service.py` (~400 linhas):
- State machine: `not_offered | offered | awaiting_sample_1 | awaiting_sample_2 | awaiting_sample_3 | enrolled | declined`
- Persist em Redis (TTL 24h pra retomar)
- Transições disparadas pelo `sofia_inbound_worker` ao detectar cenário

**Detector** em `sofia_inbound_worker.py`:
- Após `identify_any_1toN` retornar `None` E identidade do phone existir → check eligibility:
  - Lead que veio do fluxo comercial → SIM
  - Familiar responsável cadastrado no paciente → SIM
  - Cuidador novo cadastrado no tenant → SIM
  - Médico/enfermeiro vinculado → SIM
  - Não cadastrado → NÃO (pula pro fluxo comercial)

**Conversational flow** (templates de mensagem):
- Greeting + proposta (com nome inferido do cadastro)
- "Pode ser sim" → instrução pra mandar 3 áudios
- Cada áudio recebido → validação (duração mín 3s, ruído check, fala detectada)
- Após 3 amostras válidas → enroll via `voice_biometrics_service.enroll_caregiver()`
- Confirmação: *"Pronto! Cadastrado. Já consigo te reconhecer da próxima vez."*

**Endpoints admin**:
- `/api/voice/onboarding/status?phone=X` — admin vê estado da conversa
- `/api/voice/onboarding/restart` — reset state pra refazer

**Tabela nova** `aia_health_voice_enrollment_offers`:
- phone, tenant_id, person_type_offered, status, offered_at, accepted_at, declined_at, completed_at
- Audit completo da jornada

**UI** `/admin/biometria-voz/onboarding`:
- Tab nova mostrando ofertas em andamento + métricas (oferta → aceite → conclusão)

**Esforço:** 3-5 dias (1 dia state machine + detector, 1 dia conversational flow, 1 dia testes E2E, 1 dia UI admin, 1 dia integração com voice_biometrics existente)

### Pré-requisitos
- J (re-enrollment) **NÃO** é pré-requisito; podem ser implementados em paralelo
- K (push web) **NÃO** é pré-requisito
- Spec `WHATSAPP_INBOUND_IDENTITY_POLICY.md` (em main desde maio) é o blueprint

---

## Ordem sugerida pra próxima sessão dedicada

1. **L** primeiro — maior valor de produto, destrava B2C real (idoso solo no WhatsApp). 3-5 dias.
2. **J** depois — operacional, voz idosa vai precisar refresh em 90 dias mesmo (caso piloto parceiro integrador dure). 3-4h.
3. **K** por último — robustez de canal, importante mas não bloqueia features. 4-5h.

---

## Decisão de hoje

Esta sessão entregou:
- **I** parcial (5 páginas mais visíveis migradas pra useConfirm/useToast)
- **J/K/L** especificados em detalhe (este doc) pra retomar com contexto completo

Implementação full de J/K/L sai como leva separada — cada uma comporta sessão dedicada com testes, sem misturar muito código de naturezas diferentes.
