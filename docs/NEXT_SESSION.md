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

## 3. Backlog imediato — Waves curtas (próximas 2-4 semanas)

> Granularidade tática. As Ondas oficiais (numeradas, originais do roadmap)
> estão na seção 4. Estas Waves preenchem o que falta entre Onda 4 (em
> produção) e Onda 5 (próxima oficial).

### Wave 1 — Polimento pós-demo + Auth (PRIORIDADE)
- [ ] **Autenticação completa** (item #1 do topo deste doc)
- [ ] **Rastreamento de uso de parceiros**: dashboard interno mostrando quem logou, o que clicou. Necessário pra reportar pro Murilo "estamos vendo X interações suas" + métricas de engajamento.
- [ ] **Audit log LGPD funcional**: preencher `aia_health_audit_chain.actor` em toda mutação (hoje está vazio).
- [ ] **Onboarding cuidadora B2B**: fluxo "Murilo cadastra ILPI X" → ILPI cadastra cuidadoras → cuidadoras recebem instrução por WhatsApp pra começar relatos.
- [ ] **Dashboard executivo (`/`)**: quando logar como `parceiro`, ver só os tenants/clínicas dele com métricas. Hoje a home é genérica.

### Wave 2 — Robustez técnica
- [ ] **Erros do LLM Router**: log mostra `openai_not_configured` constantemente. O fallback está funcionando (Gemini), mas sujeira no log atrapalha. Limpar config ou silenciar log.
- [ ] **Embedding falhando**: `embedding-001 not found for v1beta`. Trocar pra `gemini-embedding-001` ou similar — RAG não está vetorizando.
- [ ] **Modelo Anthropic 404**: `claude-3-5-haiku-20241022` retornando 404. Atualizar pra `claude-haiku-4-5` ou similar.
- [ ] **Cron de auto-close lento**: `awaiting_ack → awaiting_status_update` levou 10min. Avaliar se intervalo está ok.
- [ ] **Logging de acessos no Traefik / Next**: ativar pra ter trace mínimo enquanto auth não chega.

### Wave 3 — Demos novas / features de venda
- [ ] **Áudio TTS Sofia (Gemini)**: testar 4 samples em `docs/testes/gemini/audios/`. Decidir migração ElevenLabs → Gemini Flash TTS (ADR-028).
- [ ] **Glossário de nomes próprios**: prompt engineering pra STT acertar "Armindo Trevisan" (hoje vira "Arlindo Trevizan"). Bloqueador da migração Gemini STT.
- [ ] **Relatório semanal automático em PDF**: gerar e enviar pro grupo familiar todo domingo (`weekly_report_service.py` já pronto, falta conectar agendador).
- [ ] **Modo "Parceiro" white label**: visão restrita do CRM com co-branding sutil (logo Tecnosenior + ConnectaIACare).
- [ ] **Pacote demo pra Murilo**: ambiente staging dedicado com 5-10 pacientes seed pra ele testar com cuidadoras reais sem misturar com produção.

### Wave 4 — Robustez B2B / multi-tenant
- [ ] Multi-tenancy real (hoje tem campo `tenant_id` mas não é enforced em todas queries)
- [ ] Onboarding de novo tenant via dashboard (formulário admin → cria tenant + usuário admin)
- [ ] Limites por plano (msgs/dia, pacientes, teleconsultas/mês)
- [ ] Faturamento + integração com Stripe/Pagar.me
- [ ] Webhook de saída pra integrações com hardware Tecnosenior (sinais vitais → ConnectaIACare)
- [ ] FHIR export real (hoje só tem o stub)

---

## 4. Roadmap oficial — Ondas (numeradas, sequência canônica)

> Origem: `docs/BRIEFING_OPUS_2026-04-22.md` + `docs/PLANO_EXPANSAO_B2B_B2C_v2_2026-04-22.md`
> ADR-028 (`docs/adr/028-gemini-voice-migration-plan.md`) cobre voz em paralelo.

### ✅ Onda 0 — Base (concluída)
- Cadastro de pacientes (FHIR-like): foto, nickname, condições, medicações, alergias, responsável
- Seed 3 pacientes realistas (Sra. Carmen, Sra. Antônia, Sr. Otacílio)
- Reports: áudio cuidador → Deepgram STT → entidades → análise clínica LLM
- Classificações: `routine · attention · urgent · critical`
- Sinais vitais com aferições circadianas (HAS 60%, DM2 22%, IC 12%, DPOC 15%)

### ✅ Onda 1 — Care Events / ADR-018 (concluída)
- Modelo de eventos com ciclo de vida: `analyzing → awaiting_ack → pattern_analyzed → escalating → awaiting_status_update → resolved | expired`
- Múltiplos eventos paralelos por cuidador
- Timeline agregada: messages, checkins, escalations, reports
- Scheduler `pg_try_advisory_lock` single-writer
- Auto-resolve por reassurance (commit recente: "tá ok", "só susto", "está bem")
- 9 closed reasons: `cuidado_iniciado | encaminhado_hospital | transferido | sem_intercorrencia | falso_alarme | paciente_estavel | expirou_sem_feedback | obito | outro`

### ✅ Onda 1.5 — Sinais vitais / ADR-014 (concluída)
- Integração MedMonitor (pull horário de vitais reais)
- Visualização tabs 7d/30d/90d, sparklines Recharts
- LLM cruza vitais com sintomas

### ✅ Onda 2 — Framework Íris + Atente / ADR-021, 022 (concluída)
- **Íris**: framework agêntico multi-papel (mensageira entre LLMs especializados)
- **Atente**: substitui SAMU automático; humano real avalia e escala

### ✅ Onda 3 — Teleconsulta completa / ADR-023 (concluída)
- Sala LiveKit + JWT por role (doctor | patient)
- Persona médica demo: Dra. Ana Silva CRM/RS 12345
- State machine 9 estados: `scheduling → pre_check → consent_recording → identity_verification → active → closing → documentation → signed → closed`
- 6 agentes IA: SOAP writer, prescription validator, FHIR emitter, etc.
- Editor SOAP 4 seções (S/O/A/P) + CID-10 + diferenciais
- Validação **Critérios de Beers + interações + alergias + dose geriátrica**
- **FHIR R4 Bundle** determinístico (Patient, Practitioner, Encounter, Condition, MedicationRequest, ClinicalImpression)
- Sync automática com TotalCare (care-note)
- **Aprimorado 24/04**: 2 links separados (médico/paciente) para evitar paciente cair em SOAP editor

### ✅ Onda 4 — Portal do paciente + preços (concluída — em produção)
- PIN 6 dígitos (bcrypt, expira 24h)
- Rota pública `/meu/[tc_id]` com PIN gate
- Resumo SOAP em linguagem simples (LLM reformula)
- Busca real de preços de medicamentos prescritos
- Envio WhatsApp automático com link+PIN pós-assinatura
- Download PDF formatado + JSON FHIR

### 🔜 Onda 5 — Biometria expandida (próxima oficial após auth)
**Bloqueador**: precisa decidir esquema FK com Opus.
- [ ] Enrollment de **paciente** (novo FK em `aia_health_voice_embeddings`)
- [ ] Enrollment de **familiar** (nova tabela ou polimórfica)
- [ ] UI de enrollment web + fluxo WhatsApp ("grave 10s dizendo X")
- [ ] Verify pré-teleconsulta (state `identity_verification` da Onda 3)
- [ ] Anti-spoofing / deepfake detection
- [ ] Multi-tenant isolation (hoje só `connectaiacare_demo`)
- [ ] Revogação self-service (LGPD Art. 18)
- [ ] Key rotation do encoder (sem reenrollar)

### 🔜 Onda 6 — Consent LGPD + identity pré-sala
- [ ] Modal de consentimento de gravação na entrada da sala (CFM 2.314/2022 + LGPD Art. 11)
- [ ] Verificação de identidade pré-sala usando biometria da Onda 5
- [ ] Trilha de auditoria do consentimento (já tem tabela `voice_consent_log`, falta UI)

### 🔜 Onda 7 — Teleconsulta sob demanda + Programa Indicação B2B→B2C
- [ ] Botão "Iniciar teleconsulta agora" no prontuário longitudinal (sem WhatsApp prévio)
- [ ] Programa de indicação formalizado (ver `docs/PROGRAMA_INDICACAO_B2B_B2C.md`)
- [ ] Portal B2B com seção "Indique pra família" + QR code + link rastreável
- [ ] Portal B2C banner "Cuide também de outros entes queridos"
- [ ] Comissão / cashback automatizado por indicação convertida

### 🔜 Onda 8 — Rede comunitária + geolocalização
- [ ] Geolocalização de paciente (consentida, opt-in família)
- [ ] Rede comunitária georreferenciada (vizinhos cuidadores opt-in)
- [ ] Acionamento de cuidador próximo em emergência (pré-Atente)
- [ ] Dashboard regional para parceiros (Murilo) ver clusters

### 🔜 Onda 9 — Clube de Benefícios
- [ ] Marketplace de parceiros (dentistas, academias, sindicatos, farmácias)
- [ ] Integração de descontos B2C (assinante Premium ganha acesso)
- [ ] API pra parceiros consultarem assinantes elegíveis
- [ ] Cashback / programa de fidelidade

### 🔜 Onda 10 — Chat humano (atendimento)
- [ ] Chat texto humano-humano (família ↔ Atente, família ↔ médico)
- [ ] Filas de atendimento por SLA
- [ ] Histórico de mensagens persistido por care_event

---

## 5. Roadmap macro — Fases (visão de produto)

> Origem: `docs/PLANO_EXPANSAO_B2B_B2C_v2_2026-04-22.md` (ajustado pós-reunião 24/04)

### Fase 1 — Demo B2B + piloto (até ~10/mai/2026)
- [x] Ondas 0-4 em produção
- [x] Scheduler proativo + weekly report (esqueleto)
- [x] Reunião Murilo (24/04) — ofertou sociedade
- [ ] **Auth + audit log** (PRIORIDADE absoluta)
- [ ] Módulo Cadastros (Pacientes/Familiares/Profissionais/Usuários)
- [ ] Programa indicação B2B→B2C MVP
- [ ] **MoU de POC remunerado 60-90d com Tecnosenior**
- [ ] Piloto 30 dias com 10 SPAs Tecnosenior (Murilo)

### Fase 2.A — B2C MVP Essencial (mai-jul/2026)
- [ ] Auth independente com MFA (extensão do Wave 1)
- [ ] Migrations 010-012 (family_members + subjects_v + billing)
- [ ] Onboarding WhatsApp conversacional (Sofia faz cadastro B2C — schema pronto, falta pluggar)
- [ ] Check-in diário (schedule_templates já seedado)
- [ ] Escalação família → Atente
- [ ] Grupo familiar via DMs individuais (contorna limite Evolution)
- [ ] Relatório semanal automático no grupo (pronto, falta plug)
- [ ] Billing Stripe/PagSeguro (SKU Essencial R$49,90)
- [ ] Verificação CPF + SMS OTP
- [ ] Onda 5 (biometria expandida)

### Fase 2.B — Diferenciação (ago-set/2026)
- [ ] Motor medicamentos 5 camadas (extensão validator)
- [ ] Biomarkers de voz como "padrão de fala" (não-diagnóstico, evita SaMD)
- [ ] Plano Família R$89,90 + Premium R$149,90
- [ ] Rede comunitária (Onda 8)
- [ ] Teleconsulta avulsa R$80
- [ ] Migração WhatsApp Cloud API
- [ ] Onda 6 + 7

### Fase 2.C — Ecosystem (out-dez/2026)
- [ ] Integração Apple Watch fall detection
- [ ] API pública pra fabricantes SOS
- [ ] Canal operadora de saúde (white-label)
- [ ] Onda 9 (Clube de Benefícios)
- [ ] Onda 10 (Chat humano)

### Fase 3 — Plataforma (Q1-Q2/2027)
- [ ] Marketplace (farmácias, labs, fisio)
- [ ] API prefeituras
- [ ] Internacionalização Portugal + LATAM
- [ ] Hospital-at-home com reembolso ANS

---

## 6. Roadmap paralelo — Voz / Gemini 3.1 (ADR-028)

> Não é Onda numerada — é um eixo transversal de otimização de custo + qualidade.

### Q2/2026 — Transcrição híbrida
- [ ] Script `compare_stt_quality.py` shadow mode 50+ áudios/mês (Gemini + Deepgram em paralelo, só loga)
- [ ] Glossário de nomes próprios (prompt engineering)
- [ ] Decisão: migrar 100% Gemini Flash-Lite OU Gemini primário + Deepgram em trechos com entity detection

### Q2/2026 — TTS via Vertex AI
- [ ] Migrar pra `vertexai` SDK (não `google.generativeai`)
- [ ] Implementar `backend/src/services/gemini_tts_service.py`
- [ ] A/B test com ElevenLabs em 10% do tráfego Sofia Voz
- [ ] Integrar prefixos de classificação ("Say warmly:", "Say firmly:") com classification layer

### Q3/2026 — Flash Live POC (substituir Ultravox)
- [ ] Estudar integração Asterisk + WebSocket Live API
- [ ] POC dev com 1 chamada de teste
- [ ] Avaliar gravação + transcrição pós-call pra audit LGPD
- [ ] Se OK → migração gradual Ultravox → Flash Live no `sofia-service`

**Economia projetada se tudo migrar**: ~$313k/ano em STT (10k usuários B2C ativos).

---

## 7. Decisões importantes registradas

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

## 8. Checklist pra abrir nova sessão

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

## 9. Arquivos / paths chave

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

## 10. Comandos rápidos

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
