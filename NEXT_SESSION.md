# Próxima sessão — Onde paramos e por onde continuar

> **Data do último handoff**: 2026-04-24 (sexta, 22h)
> **Contexto do dia**: reunião com Murilo (Tecnosenior) + Vinicius (MedMonitor) — sucesso. Eles ofereceram sociedade. Decisão: rodar POCs primeiro, formato societário depois.

---

## 1. ⚡ PRIORIDADE #1 — Implementar autenticação

**Por quê é urgente**:
- Murilo recebeu acesso à plataforma → impossível saber se ele está testando (não há login).
- Qualquer URL pública (ex: `care.connectaia.com.br/patients/maria`) abre dados clínicos pra qualquer pessoa.
- Sem auth ⇒ não passa em audit LGPD, não passa em conversa com operadora, não tem como medir engajamento.
- Não há trilha de auditoria por usuário (`aia_health_audit_chain.actor` está sempre vazio).

**Escopo mínimo viável (1-2 dias de trabalho)**:

### Backend
- [ ] Criar tabela `aia_health_users` (id, email, password_hash, role, tenant_id, full_name, crm/coren opcional, last_login_at, created_at)
- [ ] Endpoints auth:
  - `POST /api/auth/login` (email + senha → JWT 24h)
  - `POST /api/auth/refresh`
  - `GET /api/auth/me`
  - `POST /api/auth/logout` (invalida token)
- [ ] Middleware Flask que valida JWT em todos endpoints `/api/*` exceto `/health` e `/api/auth/*`
- [ ] Roles iniciais: `super_admin`, `admin_tenant`, `medico`, `enfermeiro`, `cuidador_pro`, `familia`, `parceiro` (Murilo cai aqui)
- [ ] Audit log: preencher `aia_health_audit_chain.actor` com user_id em toda mutação
- [ ] Seed inicial: criar usuário Alexandre (super_admin) + Murilo (parceiro com escopo read-only nos pacientes demo)

### Frontend
- [ ] Página `/login` com email + senha (estilo glass-card como o resto)
- [ ] `middleware.ts` Next.js que redireciona pra `/login` se não tem JWT em cookie
- [ ] AuthContext em `frontend/src/context/auth-context.tsx`
- [ ] Esconder/mostrar items da Sidebar conforme role (parceiro não vê `/configuracoes` nem `/equipe`)
- [ ] Top bar: nome do usuário + botão logout

### Stretch (próxima onda)
- [ ] OAuth Google (médicos/parceiros)
- [ ] 2FA por email/SMS pra roles `super_admin` e `medico`
- [ ] Recuperação de senha
- [ ] Sessão persistente vs single-sign

---

## 2. Estado atual do produto (snapshot 24/04)

### O que está em produção (`care.connectaia.com.br`)
| Módulo | Status | Notas |
|--------|--------|-------|
| Onboarding via WhatsApp | ✅ Ativo | Sofia recebe áudio cuidadora, transcreve (Deepgram), classifica (Gemini), responde |
| Auto-close por reassurance | ✅ Ativo | Detecta "tá ok", "só susto" e encerra evento (commit recente) |
| Áudio OGG→MP3 player | ✅ Ativo | ffmpeg conversion endpoint cacheado em disco |
| Alertas + dialpad VoIP | ✅ Ativo | Botão Ligar abre dialpad com timer; tela só fecha após hangup |
| Histórico múltiplos relatos | ✅ Ativo | Aba transcrição mostra todos reports do care_event |
| Equipe (cuidadores CRUD) | ✅ Ativo | GET/POST/PATCH/DELETE `/api/caregivers` |
| Teleconsulta agendar | ✅ Ativo | Cria registro real, gera 2 links separados (médico vs paciente) |
| Teleconsulta sala WebRTC | ✅ Ativo | LiveKit + token JWT 2h, auto-fetch se ausente |
| Teleconsulta encerrar | ✅ Ativo | Médico → SOAP editor; paciente → tela agradecimento |
| Dashboard Teleconsulta | ✅ Ativo | Lista real do banco (não mock), badges por estado |
| OCR de medicação | ✅ Ativo | Foto de caixa/bula/receita extrai posologia |
| MedicationTimeline no prontuário | ✅ Ativo | Restaurado (commit 92336f1) |
| Configurações técnicas | ✅ Ativo | Página com 9 grupos de integrações + selo Ativo/Piloto/Roadmap |
| Error boundaries | ✅ Ativo | `/app/error.tsx` global + `/consulta/[room]/error.tsx` |
| Auth | ❌ **FALTA** | Item #1 acima |

### Banco — números atuais (24/04 noite)
- 45 pacientes cadastrados
- 11 cuidadores
- 17 medication schedules ativas
- 11 teleconsultas (várias agendadas pra 25/04)
- Care events nas últimas 24h: testes seus + **Murilo (555198774144) testando!**

### 🎯 Murilo está testando — atividade rastreada (555198774144)

**WhatsApp**:
- 24/04 13:58 — adicionou Paracetamol 750mg (manual ou via receita)
- 24/04 15:03 — **subiu foto → OCR extraiu "diclofenaco potássico 50mg"** ✅
- 24/04 15:08 — relato em áudio sobre **Sr. Armindo Trevisan** (care_event #24, expirou sem feedback)
- 24/04 18:07 — **subiu foto da caixa do Torsilax → OCR extraiu princípios ativos completos** (Cafeína 30mg + Carisoprodol 125mg + Diclofenaco 50mg + Paracetamol 300mg) ✅
- 24/04 20:57-21:09 — relato em áudio sobre **Sra. Cleusa Trevisan** (care_event #25, ainda aberto, classificado routine)

**Conclusão**: Murilo testou **exatamente** os recursos wow:
1. OCR de medicação (2 vezes — receita + caixa)
2. Sofia recebendo áudio e classificando relato

**Ainda sem trace possível**: o que ele clicou no CRM web (sem auth → invisível).

---

## 3. Backlog imediato (depois da auth)

### Wave 1 — Polimento pós-demo
- [ ] **Rastreamento de uso de parceiros**: dashboard interno mostrando quem logou, o que clicou. Necessário pra reportar pro Murilo "estamos vendo X interações suas, parabéns" + métricas de engajamento.
- [ ] **Login & Audit log para LGPD**: garantir que toda ação clínica tem actor + timestamp + tenant
- [ ] **Onboarding cuidadora B2B**: fluxo de "Murilo cadastra ILPI X" → ILPI cadastra cuidadoras → cuidadoras recebem instrução por WhatsApp pra começar relatos
- [ ] **Dashboard executivo (`/`)**: quando logar como `parceiro`, ver só os tenants/clínicas dele com métricas. Hoje a home é genérica.

### Wave 2 — Robustez
- [ ] **Erros do LLM Router**: log mostra `openai_not_configured` constantemente. O fallback está funcionando (Gemini), mas sujeira no log atrapalha. Limpar config ou silenciar log.
- [ ] **Embedding falhando**: `embedding-001 not found for v1beta`. Trocar pra `gemini-embedding-001` ou similar — RAG não está vetorizando.
- [ ] **Modelo Anthropic 404**: `claude-3-5-haiku-20241022` retornando 404. Atualizar pra `claude-haiku-4-5` ou similar.
- [ ] **Cron de auto-close lento**: `awaiting_ack → awaiting_status_update` levou 10min. Avaliar se intervalo está ok ou se está com problema.

### Wave 3 — Demos novas / features de venda
- [ ] **Áudio TTS Sofia (Gemini)**: testar com 4 samples já gerados em `docs/testes/gemini/audios/`. Decidir migração ElevenLabs → Gemini Flash TTS (ADR-028).
- [ ] **Glossário de nomes próprios**: prompt engineering pra Gemini STT acertar "Armindo Trevisan" (hoje vira "Arlindo Trevizan"). Bloqueador da migração STT.
- [ ] **Relatório semanal automático em PDF**: gerar e enviar pro grupo familiar todo domingo
- [ ] **Modo "Murilo / Parceiro"**: visão restrita do CRM com white label leve (logo Tecnosenior junto)

### Wave 4 — Escala / B2B
- [ ] Multi-tenancy real (hoje tem campo `tenant_id` mas não é enforced em todas queries)
- [ ] Onboarding de novo tenant via dashboard (formulário admin → cria tenant + usuário admin)
- [ ] Limites por plano (msgs/dia, pacientes, teleconsultas/mês)
- [ ] Faturamento + integração com Stripe/Pagar.me
- [ ] Webhook de saída pra integrações com hardware Tecnosenior (sinais vitais → ConnectaIACare)
- [ ] FHIR export real (hoje só tem o stub)

---

## 4. Decisões importantes registradas

### Sociedade Murilo/Vinicius
- **NÃO ACEITAR** equity agora.
- Próximo passo: **MoU de POC remunerado 60-90 dias** (sem equity, sem exclusividade).
- Métricas claras de sucesso documentadas no MoU.
- Só falar de formato societário depois de validar pipeline deles.
- Plataforma ConnectaIACare permanece 100% sua independente do que rolar com Tecnosenior/MedMonitor.

### Compromissos de comunicação externa
- ❌ NUNCA citar fornecedores de IA (Claude/Anthropic, Deepgram, OpenAI, ElevenLabs, etc.) em material externo.
- ✅ Cases públicos OK (Sensi.ai, Hippocratic AI).
- ✅ Padrões clínicos / regulatórios OK e desejáveis (HL7 FHIR, SNOMED, CFM 2.314, LGPD, Beers, etc.).

### Network estratégico
- Construir **network próprio** via:
  - 1 case publicado/mês no LinkedIn (anonimizado)
  - Workshops trimestrais "IA aplicada à saúde sênior"
  - Presença em HIMSS Brasil / Hospitalar / FENASAÚDE
- Não depender só do network do Murilo.

---

## 5. Checklist pra abrir nova sessão

Quando abrir nova sessão Claude, comece com:

1. **Ler este arquivo (`NEXT_SESSION.md`) primeiro.**
2. Ler `CLAUDE.md` na raiz do worktree.
3. Verificar estado atual:
   ```bash
   git log --oneline -10
   ssh root@72.60.242.245 "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep connectaiacare"
   ```
4. Decidir prioridade do dia. Por padrão: **autenticação** (item #1 acima).
5. Atualizar este arquivo no fim da sessão com o que avançou.

---

## 6. Arquivos / paths chave

```
backend/
  src/handlers/
    routes.py                   # API principal + /api/teleconsulta/<room>/token
    teleconsulta_routes.py      # POST schedule/end, GET listing
    alerts_routes.py            # /api/alerts com history[] dos reports
    caregivers_routes.py        # CRUD cuidadores
    voip_routes.py              # POST /api/voip/call (delega pra voip-service)
    pipeline.py                 # Reassurance auto-close + REASSURANCE_TERMS
  src/services/
    teleconsulta_service.py     # generate_quick_token()
  scripts/
    test_gemini_voice.py        # benchmark STT
    test_gemini_tts_rest.py     # TTS via REST

frontend/src/
  app/
    teleconsulta/agendar/page.tsx   # 2 links separados (médico/paciente)
    teleconsulta/page.tsx           # Dashboard real
    consulta/[room]/                # Sala WebRTC
    consulta/finalizada/page.tsx    # Tela paciente pós-call
    teleconsulta/[id]/documentacao/ # SOAP editor (médico)
    configuracoes/page.tsx          # NOVA — integrações técnicas
    patients/[id]/page.tsx          # Prontuário 360°
    alertas/page.tsx                # Alerts panel + dialpad
    error.tsx                       # Error boundary global
  components/
    consulta-room.tsx               # WebRTC + auto-fetch token
    alerts/alerts-panel.tsx         # History com áudio por relato
    alerts/call-confirm-modal.tsx   # CallLifecycle state machine
    medication/
      medication-timeline.tsx       # Tabs upcoming/active/history + Add
      add-medication-wizard.tsx     # Foto/Manual/Áudio → OCR

docs/adr/
  028-gemini-voice-migration-plan.md  # Plano migração voz (Q2-Q3)
```

---

## 7. Comandos rápidos

```bash
# Deploy frontend
ssh root@72.60.242.245 "cd /root/connectaiacare && bash scripts/deploy.sh frontend"

# Deploy backend
ssh root@72.60.242.245 "cd /root/connectaiacare && bash scripts/deploy.sh api"

# Logs sem ruído de scheduler
ssh root@72.60.242.245 "docker logs --since 1h connectaiacare-api 2>&1 | grep -vE 'medication_events_materialized|scheduler_tick'"

# Banco
ssh root@72.60.242.245 "docker exec connectaiacare-postgres psql -U postgres -d connectaiacare"

# Typecheck frontend local
cd frontend && npx tsc --noEmit
```

---

**Bora!** Próxima sessão começa pela auth. 🔐
