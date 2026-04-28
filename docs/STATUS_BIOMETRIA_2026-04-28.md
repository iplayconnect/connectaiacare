# Status — Biometria de Voz + Atualização Sofia (sessão noturna)

**Data**: 2026-04-28 (madrugada)
**Branch**: `claude/auth-impl`
**Status**: implementado, validado (TS clean, Python compile OK),
commitado e pushed. **Não deployado**.

---

## TL;DR

Dois tracks paralelos, ambos prontos pra revisão:

1. **Voice biometrics expandida pra pacientes** — base existente (só
   cuidador) ganhou paciente + UI admin completa pra cadastrar amostras
   pelo navegador.

2. **Sofia knowledge atualizado** — 8 novos chunks na knowledge base
   pra que Sofia conheça revisão clínica, RENAME 2024, cascatas batch 2,
   antibióticos, biometria, proactive caller e o time técnico.

---

## Commits

```
86d57b9 feat(voice-biometrics): suporte paciente + admin UI completa
aaba53f feat(sofia-memory): atualiza knowledge chunks com features abr/2026
```

PR: https://github.com/iplayconnect/connectaiacare/compare/main...claude/auth-impl

---

## O que precisa de você antes do deploy

### Decisões de produto/clínicas

1. **Consentimento implícito vs explícito** (LGPD Art. 11)
   Hoje: admin clica "cadastrar" e o ato implica consent (gravado em
   audit_log com IP). O Henrique tem opinião sobre isso? Para POC
   parece suficiente; pra GA precisa modal explícito.

2. **Endpoints de cuidador sem `@require_role`**
   Os 3 endpoints originais de cuidador (`/api/voice/enroll`, `/enrollment/<id>`,
   `DELETE`) não tem RBAC. Os de paciente que adicionei JÁ tem.
   Quer que eu mova os de cuidador pra mesma proteção? (PR separado
   pra não esconder nessa entrega.)

3. **Validação clínica do Henrique**
   Faz sentido perguntar: tem contraindicação pra identificação
   automática em paciente com doença que altera fala
   progressivamente (Parkinson, ELA, AVC pós-fala)? Pode ser que
   biometria fique instável demais e não valha o overhead.

### Operacionais

4. Aplicar migration 049 e 050 em ordem em staging antes de produção.
5. Dry-run: enrollar 1 paciente real + 1 cuidador real, observar
   qualidade média e taxa de match em áudios reais antes de
   generalizar.

---

## O que foi entregue

### Voice biometrics

**Backend**
- `backend/migrations/050_voice_biometrics_patient_support.sql`
  - ALTER aia_health_voice_embeddings: person_type + patient_id (XOR)
  - ALTER aia_health_voice_consent_log: idem
  - ALTER aia_health_reports: reporter_person_type
  - VIEW aia_health_voice_coverage_summary

- `backend/src/services/voice_biometrics_service.py` (estendido)
  - Métodos novos: enroll_patient, verify_patient_1to1,
    identify_patient_1toN, identify_any_1toN, delete_patient_enrollment,
    get_patient_enrollment_status, list_coverage_summary.
  - _CacheEntry agora carrega cuidadores E pacientes em uma passada.
  - Helper _aggregate_embeddings reutilizável.

- `backend/src/handlers/routes.py` (novos endpoints)
  - POST `/api/voice/patient/enroll` (require_role)
  - GET `/api/voice/patient/enrollment/<id>` (require_role)
  - DELETE `/api/voice/patient/enrollment/<id>` (require_role admin)
  - GET `/api/voice/coverage` (require_role)
  - GET `/api/voice/enrollments` (require_role)

**Frontend**
- `frontend/src/app/admin/biometria-voz/page.tsx`
  - Cards de cobertura (pacientes/cuidadores/amostras/qualidade)
  - Tabela com filtro por tipo + busca
  - Modal de gravação: escolher pessoa → MediaRecorder 5-10s →
    preview → envia base64 → feedback de qualidade + N amostras
  - Botão revogar (LGPD)

- `frontend/src/components/sidebar.tsx` — entry "Biometria de Voz"
- `frontend/src/lib/api.ts` — 9 métodos novos

**Docs**
- `docs/plano_biometria_voz.md` — arquitetura, schema, thresholds,
  riscos, checklist de deploy, roadmap

### Sofia knowledge

- `backend/migrations/049_sofia_knowledge_apr2026.sql` — 8 chunks
  novos cobrindo todas as features de abril 2026.

---

## Como revisar manhã

### Fluxo recomendado (15 min)

1. Abre o PR: https://github.com/iplayconnect/connectaiacare/compare/main...claude/auth-impl
2. Lê `docs/plano_biometria_voz.md` (decisões + thresholds + riscos).
3. Verifica `docs/STATUS_BIOMETRIA_2026-04-28.md` (este doc).
4. Confere as 3 questões em "Decisões de produto/clínicas" acima.
5. Se OK, autoriza o merge.

### Após merge — comandos de deploy

```bash
# VPS Hostinger
ssh root@72.60.242.245
cd /root/connectaiacare
git pull origin main

# Aplica migrations 049 + 050 (em ordem)
docker compose exec postgres psql -U connectaiacare connectaiacare \
  -f /app/migrations/049_sofia_knowledge_apr2026.sql
docker compose exec postgres psql -U connectaiacare connectaiacare \
  -f /app/migrations/050_voice_biometrics_patient_support.sql

# Rebuild backend (novas rotas) + frontend (nova página)
docker compose up -d --build api frontend
```

> Se o jeito que vocês aplicam migrations é diferente (script
> automatizado tipo `init_db.sh` ou serviço de migrations), use o
> mesmo padrão — só citei `psql` direto pra simplicidade.

### Smoke test pós-deploy

- [ ] Login como admin → /admin/biometria-voz carrega
- [ ] Cards de cobertura aparecem com 0/0 (nenhum paciente enrolado ainda)
- [ ] Modal "Cadastrar amostra" abre, lista pacientes do tenant
- [ ] Gravação 5s funciona no Chrome/Safari (microfone permission)
- [ ] Envio retorna `success: true` + samples_count: 1
- [ ] Após 3 amostras, enrollment_complete: true
- [ ] Botão revogar apaga e some da tabela
- [ ] Sofia (chat ou WhatsApp) responde corretamente sobre features
      novas (ex: "como funciona a revisão clínica?" → cita /admin/
      regras-clinicas/revisao + auto_pending)

---

## Tracks que NÃO entrei (deliberadamente, fora de escopo)

1. **Hook biométrico em `voice-call-service`** — chamada SIP ainda
   identifica caller pela extension/ramal, sem biometria. Roadmap
   Fase 2 do plano.

2. **Liveness detection (replay attack)** — Resemblyzer não tem.
   Mitigação por challenge-response em chamadas críticas é Fase 3.

3. **Re-enrollment automático periódico** — voz idosa varia. Sugestão
   de cron anual fica em roadmap.

4. **Pgvector index IVFFlat** — só vale com 100+ embeddings/tenant.
   Hoje full-scan em RAM é mais rápido.

5. **Modal de consent explícito** — hoje o ato implícito + audit_log
   atende POC. Antes de GA precisa.

---

## Resumo emocional

A biometria não foi greenfield — ela já existia pra cuidadores desde a
migration 003. O que faltava era o paciente, o painel admin pra fazer o
enrollment de forma humana (não via curl) e a documentação de riscos
LGPD. Tudo isso ficou pronto. Agora a Sofia também sabe que isso existe
(chunk #5 da migration 049).

A parte mais sensível do PR é dado biométrico sensível. Por isso
parei antes do deploy: queria você acordar e bater o olho na cadeia
de consent + RBAC + revogação antes de subir.

Bom descanso. 🌙
