# Sofia — Levantamento técnico para análise externa
> ConnectaIACare · revisão 2026-04-26
> Documento preparado pra análise/consultoria externa avaliar arquitetura
> e recomendar evolução.

## 0. Sumário executivo

A **Sofia** é a IA assistente da ConnectaIACare, posicionada como **camada
única de relacionamento** com 4 personas (paciente, familiar, cuidador,
profissional clínico) através de **3 canais técnicos** (chat texto, voz no
browser e ligação telefônica) cobrindo **3 propósitos** (suporte ao
cuidado, relacionamento contínuo e conversão comercial). Compartilha entre
os canais: **memória persistente do usuário** (cross-session), **base de
conhecimento RAG** com lições aprendidas anonimizadas (cross-tenant),
**motor de cruzamentos clínicos** (dose validator com 12 dimensões / ~48
princípios ativos cobertos) e **playbooks editáveis por admin** sem
release de código.

**Visão de longo prazo**: Sofia entrega ciclo completo de cuidado
(comercial → onboarding → monitoramento → suporte clínico → emergência)
**sem intervenção humana obrigatória**. Humano entra como camada premium
do plano OU como última instância em casos críticos. Inspiração de
mercado: Tesla converte ~20% via LLM voz, corporações chinesas operam
ciclo full multicanal com IA. Posicionamento BR: NÃO competir com
EHR enterprise (MV, TOTVS) — atuar **na ponta**, no relacionamento
direto com o usuário final (paciente, família, cuidador).

Estado atual: **chat e voz browser em produção estáveis**. **Voz
telefônica funciona end-to-end** mas trunk SIP do operador (Flux)
atualmente bloqueando outbound. Inbound não implementado ainda. Frontend
admin pra configurar tudo já no ar.

## 1. Visão estratégica e missão

### 1.1 Missão
**Tornar o relacionamento de cuidado totalmente conduzível por IA**,
removendo a dependência de intervenção humana operacional sempre que
possível, e mantendo o humano como camada de **escalação clínica** ou
**diferencial de plano premium**.

A premissa: cuidado de qualidade pra idosos e pacientes crônicos no Brasil
hoje é caro porque cada interação requer enfermeira/cuidadora/atendente.
Em escala B2C massiva (idoso B2C que mora sozinho, família distante,
clínica popular), esse modelo NÃO fecha conta. Sofia muda essa
matemática — o custo marginal de mais 1 paciente acompanhado tende a zero
porque a Sofia faz check-in, captura sintoma, valida medicação e escala
quando precisa, **24/7 sem fadiga**.

### 1.2 Por que 3 canais integrados (Chat, Voz, VoIP)

Cada canal serve melhor um momento da jornada. Mas a SOFIA é **uma só**:
mesma persona, mesma memória, mesmas tools, só muda a interface. O usuário
não precisa "explicar de novo" quando troca de canal.

| Canal | Quando o usuário escolhe | Proposta de valor única |
|-------|---------------------------|-------------------------|
| **Chat texto** (web/mobile) | Curiosidade lenta; consulta clínica do médico; cuidador documenta um relato | Documenta tudo, permite anexar imagens (foto de receita), reflexão |
| **Voz browser** (FAB de voz) | Cuidador com mãos ocupadas; paciente que tem dificuldade pra digitar; consulta rápida | Hands-free, latência baixa, mantém presença mesmo enquanto cuida |
| **Ligação telefônica** (VoIP outbound + futuro inbound) | Idoso que NÃO usa app/web; familiar distante recebendo aviso; check-in proativo de plano B2C | Atinge quem não tem smartphone; sensação de "alguém ligou pra mim"; canal universal |

**Por que integrados (e não 3 produtos)**:
- Idoso B2C usa só telefone (canal único). Sofia liga, ele atende, fala
  com Sofia. Tudo passa pela mesma camada.
- Família às vezes recebe ligação da Sofia avisando evento; depois entra
  no app pra ver detalhes via chat. **Sofia continua a conversa** —
  história única.
- Cuidador profissional recebe ligação pós-relato pra atualizar status,
  depois confirma medicação via chat texto. Sofia memoriza a evolução
  cross-canal.
- Comercial: lead recebe ligação Sofia da campanha, fecha pelo WhatsApp
  texto, vira paciente onboardado tudo na mesma sessão emocional.

### 1.3 Os 3 propósitos × 3 canais

Matriz de uso. Cada célula é um cenário real que a Sofia já cobre ou
tem playbook editável:

| Propósito \ Canal | Chat texto | Voz browser | Ligação telefônica |
|--------------|------|------|------|
| **Suporte (clínico)** | Médico consulta dose máxima de dabigatrana, Sofia roda dose_validator e responde | Enfermeira em plantão pergunta interação enquanto preenche prontuário, Sofia responde por voz | Cuidador profissional liga pra tirar dúvida sobre paciente fora do horário comercial (Fase 2 inbound) |
| **Relacionamento** | Familiar acessa app, Sofia mostra resumo do paciente e tira dúvida | Paciente B2C usa FAB de voz pra check-in informal "Sofia, hoje tá tudo bem?" | Sofia liga 8h30 todo dia pro paciente B2C que mora sozinho, valida medicação, capta sintoma novo |
| **Comercial** | Visitante do site abre chat, Sofia qualifica + agenda demo | Demo ao vivo no site com Sofia explicando proposta por voz | Sofia liga pro lead que se cadastrou na landing, qualifica + agenda humano se quente |

Para cada cenário existe (ou existirá) um **cenário (playbook) editável**
em `aia_health_call_scenarios` com tom, regras, tools permitidas e ações
pós-interação. Admin edita sem release de código.

### 1.4 Onde queremos chegar — cenário aspiracional

> **Plano "Cuidado Sem Limites" (B2C, idoso que mora sozinho)**:
>
> Dona Helena, 82 anos, mora sozinha em Porto Alegre. Filha em Lisboa,
> sem cuidador presencial. Compra o plano via WhatsApp — Sofia faz toda
> a venda sem humano. Onboarding via ligação: Sofia coleta condições,
> medicações, contato familiar. Cadastra tudo.
>
> A partir do dia 1:
> - 8h30: Sofia liga pra Helena. Boa tarde, como passou a noite?
>   Tomou losartana? Sentiu alguma coisa? Helena conversa 3 minutos.
> - 14h: Sofia liga lembrete de hidratação no calor.
> - 20h: Sofia liga lembrete de janta + medicação noturna.
>
> Quarta de manhã Helena fala "tô com tontura". Sofia roda
> `check_medication_safety`, vê interação com novo medicamento, registra
> care_event=urgent, liga pra filha em Lisboa explicando "sua mãe
> reportou tontura, podem estar relacionada a XYZ que ela começou ontem,
> orientei a parar de tomar e procurar atendimento". Filha agradece
> aliviada, Sofia agenda teleconsulta.
>
> Sexta noite Helena sente dor no peito. Sofia liga emergência 192,
> mantém Helena na linha consolando, liga pra filha em paralelo. Tudo
> registrado.
>
> Custo operacional ConnectaIACare por mês de cuidado dessa Helena:
> insignificante. Custo de mercado equivalente (cuidador 24/7): R$5k+.
> Plano custaria 3-10% disso e gera margem.

Esse é o cenário-norte. Cada feature que construímos hoje (memória
persistente, motor de cruzamentos, ligação outbound com playbooks)
existe pra **viabilizar ESTA história em escala**.

### 1.5 Posicionamento de mercado

**NÃO somos**:
- EHR enterprise (MV, TOTVS, Tasy) — eles são a infra hospitalar,
  sistemas de prontuário pra grandes operadoras
- Telemedicina pura (Doctoralia, Conexa) — eles conectam paciente
  ao médico humano por consulta
- Healthtech B2B SaaS administrativa (Memed, iClinic) — eles
  digitalizam workflow do médico

**Somos**:
- Camada de **relacionamento contínuo** com o paciente/cuidador
- Atuamos **na ponta** (último centímetro) — onde o cuidado vira
  conversa diária
- Modelo **B2B2C** (clínica + paciente final) e **B2C** (idoso direto
  sem clínica intermediária)
- Diferencial: **deterministic clinical engine** + **conversational
  AI nativa** + **multi-canal unificado** rodando em escala

**Coexistimos (não substituímos)**:
- Hospital usa MV pro prontuário, ConnectaIACare pra acompanhar pós-alta
- Operadora de saúde usa sistema próprio pra gestão, ConnectaIACare pra
  monitoramento contínuo do beneficiário crônico
- Família contrata cuidador presencial 8h, ConnectaIACare cobre as
  outras 16h

### 1.6 Referências externas que validam a tese

**Tesla** opera vendas em alguns mercados com IA por voz que converte
~20% (vs 5-10% de SDR humano). LLM faz qualificação, captação de
preferências, agendamento. Custo por lead processado cai 90%+.

**Corporações chinesas** (Alibaba, JD.com, ICBC) já operam atendimento,
suporte e cobrança full multicanal LLM (texto + voz + ligação). Volume
de centenas de milhões de interações/mês com taxa de satisfação igual
ou superior a humano em first-line.

**Hippocratic AI** (US) faz check-ins clínicos pós-alta hospitalar via
voz. Validado em estudos com 200k+ pacientes — não-inferioridade vs
enfermeira humana em 90% dos protocolos.

**Sensi.ai** (US) monitora idosos via sensores + IA conversacional, sem
visita presencial. Avaliação 2024 mostrou redução de 40% em hospitalização.

Brasil ainda não tem player nativo nesse espaço com **arquitetura de
ponta integrada** (chat + voz + ligação + motor clínico + memória). Aí
está nossa janela.

### 1.7 Métricas-norte (KPIs a perseguir)

| Dimensão | Métrica | Alvo 12m | Alvo 36m |
|----------|---------|----------|----------|
| **Adoção** | Pacientes ativos com ≥3 interações/semana | 1.000 | 50.000 |
| **Conversão comercial** | Lead → paciente onboardado | 15% | 25% |
| **Satisfação** | NPS familiar | >50 | >70 |
| **Eficiência** | % das interações sem escalação humana | 70% | 92% |
| **Segurança** | False negatives críticos (Sofia não escalou e devia) | <0.1% | <0.01% |
| **Cobertura clínica** | Princípios ativos no motor | 80 | 300+ |
| **Receita** | ARR | R$1M | R$30M |

Esses números só são atingíveis com Sofia como **operadora primária do
relacionamento**. Não é "Sofia ajuda humano" — é "Sofia opera, humano
supervisiona escalações".

## 2. Visão arquitetural

### 1.1 Containers (Docker Compose, VPS Hostinger)

| Container | Função | Port | Stack |
|-----------|--------|------|-------|
| `connectaiacare-postgres` | PG 16 + pgvector dedicado (LGPD: separado da outra plataforma) | 5432 (interno) | pgvector/pgvector:pg16 |
| `connectaiacare-api` | API REST principal (Flask + Gunicorn) | 5055 | Python 3.12 |
| `connectaiacare-sofia-service` | Sofia Chat + Sofia Voz browser + tool registry | 5031 (REST) + 5032 (WS ASGI) | Flask + FastAPI + websockets |
| `connectaiacare-voice-call` | Sofia em ligações SIP (Grok Realtime + PJSIP) | 5040 (HTTP) + 5060 (SIP UDP) + 10500-10600 (RTP) | Python 3.11 + PJSIP 2.14 nativo |
| `connectaiacare-frontend` | Next.js 14 (admin + UIs operacionais) | 3000 | Next.js + React 18 + Radix UI + Tailwind |

Todos atrás de Traefik (compartilhado com outra plataforma SaaS — apenas
roteamento, dados isolados em PG dedicado).

### 1.2 Domínios/Hosts
- `care.connectaia.com.br` — frontend (admin + UI operacional)
- `api.connectaia.com.br` (TBD) — API REST direto
- `sofia-voice.connectaia.com.br` — WebSocket Sofia Voz browser
- `voice-call.connectaia.com.br` — admin do voice-call-service (uso interno)

### 1.3 Persistência (PG)

Todas as tabelas com prefixo `aia_health_*` (LGPD: separado de outras
plataformas que usam `bbmd_*`):

**Cross-canal (Sofia toda):**
- `aia_health_sofia_sessions` — uma row por sessão (chat/voz/call), `channel` IN ('web','whatsapp','voice','voice_call','api')
- `aia_health_sofia_messages` — histórico unificado de mensagens com `tool_input`/`tool_output` JSONB; chat texto, transcrição de voz e ligação compartilham essa tabela
- `aia_health_sofia_user_memory` — memória cross-session por user_id (summary + key_facts JSONB)
- `aia_health_sofia_audit` — eventos sensíveis da Sofia
- `aia_health_audit_chain` — hash chain LGPD-compliant (todas as ações sensíveis: login, edição de regras, dial)

**Conhecimento:**
- `aia_health_knowledge_chunks` — RAG com `domain` (medications, geriatrics, company, collective_insight, etc.), `keywords[]`, `priority`, embeddings 768d (campo presente, retrieval ainda por ILIKE — pgvector pronto pra ativar)
- `aia_health_sofia_collective_insights_raw` — staging de insights agregados anonimizados
- `aia_health_sofia_collective_cursor` — controle do batch diário

**Motor de cruzamentos clínicos (12 dimensões):**
- `aia_health_drug_dose_limits` — dose máx, classe terapêutica, flag Beers AVOID, NTI
- `aia_health_drug_aliases` — nome comercial → princípio ativo
- `aia_health_drug_interactions` — 60+ pares com `time_separation_minutes` (interações por absorção mitigáveis por horário)
- `aia_health_drug_renal_adjustments` — faixas ClCr (Cockcroft-Gault)
- `aia_health_drug_hepatic_adjustments` — Child-Pugh A/B/C com 142 entries
- `aia_health_drug_anticholinergic_burden` — ACB score 0-3
- `aia_health_drug_fall_risk` — score por classe terapêutica
- `aia_health_drug_vital_constraints` — ex: PA <100 + BCCa = warning
- `aia_health_allergy_mappings` — alergia + classe afetada + cross-reactivity
- `aia_health_condition_contraindications` — condição → fármaco/classe
- `aia_health_condition_aliases` — "cirrose Child B" → child_b

**Outbound calls:**
- `aia_health_call_scenarios` — playbooks editáveis (system_prompt, allowed_tools[], voice, post_call_actions[])
- `aia_health_scheduled_calls` — agendamento outbound (RRULE pra recorrência) — schema pronto, scheduler ainda não implementado

## 3. Sofia Chat (texto)

### 2.1 Arquitetura
- 5 sub-agents Python (`base_agent` + `caregiver`, `family`, `platform`, `patient`, `clinical`)
- Cada um com prompt próprio em `sofia-service/prompts/sofia_*.txt` (~140 linhas total)
- Roteamento por persona via `orchestrator.get_agent_for_persona`
- Multi-round tool calling com até 5 rounds antes de forçar resposta texto
- LLM padrão: `gemini-3-flash-preview` (overridable via env)

### 2.2 Tool registry (16 tools)

Persistidas em `sofia-service/src/tools.py`. Filtragem por persona via `allowed_personas`:

| Tool | Personas | Função |
|------|----------|--------|
| `get_patient_summary` | clínica + família + cuidador | Resumo: condições, meds, alergias, último relato |
| `get_patient_vitals` | clínica + família + cuidador | PA/FC/SatO2/temp/glicemia últimos N dias |
| `read_care_event_history` | clínica + cuidador + família | Últimos N care_events |
| `list_medication_schedules` | clínica + cuidador + família + paciente | Meds ativas |
| `confirm_medication_taken` | cuidador + paciente + enfermagem | Marca dose como tomada |
| `create_care_event` | todos exceto admin | Cria relato/queixa/evento |
| `get_alert_status` | clínica + admin | Lista alertas abertos do tenant |
| `search_patients` | clínica + admin + cuidador | Busca fuzzy por nome |
| `schedule_teleconsulta` | família + paciente + cuidador + clínica | Cria solicitação |
| `query_clinical_guidelines` | clínica + admin | RAG search (token-aware) |
| `query_drug_rules` | clínica + admin | TUDO sobre 1 princípio ativo (12 dim) |
| `check_drug_interaction` | clínica + admin | Par específico, com time_separation |
| `list_beers_avoid_in_condition` | clínica + admin | Contraindicações por condição |
| `check_medication_safety` | clínica + admin | Roda 12 dim sem persistir (preview) |
| `send_check_in` | clínica + admin | Cria care_event de check-in proativo |
| `get_my_subscription` | paciente + família | Plano contratado |

### 2.3 Memória cross-session
A cada turn, `base_agent.run()` chama `memory_service.maybe_update_async()`. Threshold: 20 mensagens novas → re-summariza via Gemini Flash (~$0.0005/extração). Persistido em `aia_health_sofia_user_memory.summary` (text) + `key_facts` (JSONB com role_context, preferences, ongoing_topics, concerns). Carregado e injetado no system prompt de cada nova sessão.

LGPD: opt-in via `aia_health_users.sofia_memory_enabled` (default TRUE pra profissionais, planejado FALSE pra paciente_b2c quando esse fluxo for migrado).

## 4. Sofia Voz (browser)

### 3.1 Arquitetura
- `voice_app.py` (FastAPI ASGI, porta 5032) — bridge WebSocket browser ↔ provider
- JWT short-TTL (5min) emitido pelo api com scope=`sofia_voice` e persona embutida
- Browser conecta direto via `wss://sofia-voice.connectaia.com.br/voice/ws?token=…`
- 2 providers selecionáveis via `SOFIA_VOICE_PROVIDER`:
  - **Grok Voice Realtime** (xAI, default) — speech-to-speech end-to-end, ~500-800ms latência por turn
  - **Gemini Live API** (fallback) — funciona mas instável em produção
- Ambos compartilham mesmo system prompt + memória + tools

### 3.2 Pipeline áudio
- **Browser → Server**: AudioWorklet captura mic, downsample 48k→16k, envia base64 via WS
- **Server → Grok**: upsample 16k→24k, envia como `input_audio_buffer.append`
- **Grok → Server**: recebe `response.output_audio.delta` (PCM 24k base64)
- **Server → Browser**: forward direto, browser reproduz via Web Audio API (24k)

### 3.3 Tools
Mesmas 16 tools do chat, filtradas por persona. Schemas convertidos pra formato OpenAI Realtime (Grok é compatível).

### 3.4 Persistência
- Cada utterance vai pra `aia_health_sofia_messages` (mesma tabela do chat)
- Transcrições in/out gravadas (Whisper input + Grok output transcript)
- Tool calls com input/output JSONB
- Audit chain por sessão

## 5. Sofia VoIP (telefone)

### 4.1 Arquitetura

```
Browser → POST /api/communications/dial (api Flask, JWT)
      → carrega scenario do PG, contexto do paciente
      → POST /api/voice-call/dial (voice-call-service)
            → SipLayer.dial() (PJSIP nativo)
                  ⇩
            INVITE → trunk SIP (revendapbx.flux.net.br)
                  ⇩
            paciente atende → state CONFIRMED
                  ⇩
            GrokCallSession.start_kickoff() ← (kickoff só após CONFIRMED)
                  ↕
            audio_bridge 8k ↔ 24k entre PJSIP e Grok WS
                  ↕
            Grok Realtime executa tools via HTTP proxy ao sofia-service
                  ⇩
            speech_started detectado → drain SIP buffer + response.cancel
                  ⇩
            DISCONNECTED → close session + memory write-back
```

### 4.2 Configurações SIP atuais
- Trunk: `revendapbx.flux.net.br:5060` UDP (operador Flux)
- Conta: `5130624363` (anteriormente `5130624656`) — atualmente bloqueada outbound pelo operador
- Display name: `"ConnectaIA Care"` no From header
- Codec aceito: PCMA (G.711 a-law) 8kHz mono
- RTP range: 10500-10600 UDP (segregado da outra plataforma que usa 10000-10100)

### 4.3 Cenários populados (5 outbound, editáveis por admin via `/admin/cenarios-sofia`)

| Code | Tom | Persona | Tools-chave | Pós-call |
|------|-----|---------|-------------|----------|
| `paciente_checkin_matinal` | Acolhedor, sem pressa | paciente_b2c | list_meds, vitals, create_care_event | check_critical_keywords + memory |
| `cuidador_retorno_relato` | Profissional, direto | cuidador_pro | read_history, update_event, schedule_teleconsulta | update_event_status |
| `familiar_aviso_evento` | Seguro, calmo | familia | get_summary, schedule_teleconsulta | log_family_notification |
| `paciente_enrollment_outbound` | Caloroso, investigativo | paciente_b2c | create_enrollment_draft, schedule_teleconsulta | notify_admin_new_lead |
| `comercial_outbound_lead` | Caloroso + conversor | comercial | create_lead, schedule_teleconsulta | update_lead_score, notify_admin |

Cada cenário tem prompt completo (~7-15KB cada) com regras anti-pânico, anti-diagnóstico, RBAC LGPD.

### 4.4 Tools na ligação (8 disponíveis, 5 locais + 3 via HTTP proxy)

**Locais (DB direto na voice-call-service):**
- get_patient_summary, list_medication_schedules, get_patient_vitals
- create_care_event, schedule_teleconsulta

**HTTP proxy ao sofia-service** (evita duplicar 700+ linhas do dose_validator):
- query_drug_rules, check_drug_interaction, check_medication_safety

### 4.5 Interrupção pelo usuário
Quando server VAD da Grok detecta `input_audio_buffer.speech_started` enquanto Sofia falava:
1. **Drain SIP buffer**: `_SocketToSipPort.drain()` esvazia o PCM bufferizado → Sofia para de falar no telefone INSTANTANEAMENTE
2. **response.cancel** pra Grok via WS → para a geração

Tracking via `_sofia_speaking` flag (true em delta, false em done) — evita falso positivo no início da call.

### 4.6 Time-aware
`_time_period_pt()` retorna saudação ("Bom dia/Boa tarde/Boa noite") + despedida + hora BRT, injetadas no kickoff e system prompt. Sofia despede-se apropriadamente quando user falar "tchau/até mais/pode desligar".

### 4.7 Memory write-back
Ao `close()` da sessão SIP, voice-call-service chama `POST /sofia/memory/update` no sofia-service que força re-summarize. Próxima conversa carrega memória atualizada.

## 6. Memória coletiva cross-tenant (anonimizada)

Pipeline batch diário (`collective_insights_scheduler`):

1. Janela de 24h em `aia_health_sofia_messages` (mensagens user + assistant)
2. **Anonimização** dual-stage:
   - Regex: UUID, email, telefone BR (regex E.164), CPF, CRM/COREN, "Dr./Dona Fulano"
   - LLM safety pass (opcional): nomes de unidade, bairros, idades específicas
3. **Extração de insights** via Gemini: agrupa em padrões (clinical_question, prescribing_pattern, feature_doubt, knowledge_gap, workflow_friction)
4. **Upsert com agregação de frequência**: insights similares (overlap de keywords) somam contador
5. **Promoção** quando freq ≥ 3 (default): vira chunk em `aia_health_knowledge_chunks` com `domain='collective_insight'`
6. Sofia consome via `query_clinical_guidelines` automaticamente

LGPD: mensagens crus NUNCA saem da tabela original; staging só guarda texto JÁ anonimizado; mínimo de freq=3 evita re-identificação por combinação rara (privacidade diferencial básica).

## 7. Motor de cruzamentos clínicos (Drug Cross-Reference Engine)

### 6.1 12 dimensões validadas
1. Dose máxima diária (ANVISA / FDA)
2. Beers 2023 AVOID + Caution
3. Alergias documentadas + reações cruzadas
4. Duplicidade terapêutica
5. Polifarmácia (carga total)
6. Interações medicamento-medicamento (com `time_separation_minutes` quando absorção pode ser mitigada espaçando horários)
7. Contraindicações por condição clínica
8. ACB score (Anticholinergic Cognitive Burden cumulativo)
9. Risco de queda por classe terapêutica
10. Ajuste renal por faixa de ClCr (Cockcroft-Gault, regras KDIGO)
11. Ajuste hepático Child-Pugh A/B/C
12. Constraints de sinais vitais

### 6.2 Cobertura atual (~48 princípios ativos)
Anti-hipertensivos (8), antidiabéticos (5), antiplaquetários (2), anticoagulantes incluindo DOACs (4), estatinas (3), IBPs (3), antidepressivos (4), hipnóticos/ansiolíticos (4), antipsicóticos (4), antiparkinsonianos (3), antieméticos (2), antibióticos (5) + outros 10.

### 6.3 Endpoint
`POST /api/clinical-rules/validate-prescription` roda dose_validator.validate() **sem persistir**. Usado por:
- Sofia tool `check_medication_safety` (pré-prescrição)
- UI de prescrição (preview antes de salvar)
- POST de medication-schedule (bloqueia se severity=block, requer `force=true` que entra em audit chain)

### 6.4 Revalidação automática
`dose_revalidation_scheduler` re-roda validador sobre TODAS prescrições ativas a cada 7 dias. Cobre o caso de regras novas adicionadas pelo admin tornarem prescrições antigas inseguras. Dedupe de alertas por (paciente, schedule, issue_codes_key) últimos 7 dias.

## 8. Knowledge base (RAG)

### 7.1 Estado atual
- `aia_health_knowledge_chunks` com 19 chunks seedados manualmente:
  - 9 sobre plataforma (motor cruzamentos, admin pages, audit chain, etc.)
  - 10 clínicos (Beers em demência, DOACs renal, AINEs+anticoag, ACB, fall risk, Child-Pugh, QT prolongadores, time_separation por absorção, NTI, polifarmácia)
- + chunks publicados automaticamente pela memória coletiva (freq ≥ 3)

### 7.2 Retrieval
Hoje **token-aware ILIKE** (multi-palavra OR em title/content/summary/keywords[], ordenado por priority). pgvector está habilitado e schema tem campo `embedding vector(768)` mas extração de embeddings ainda não implementada — próxima fase.

## 9. Frontend (Next.js 14 + React 18)

### 8.1 Páginas relevantes pra Sofia
- `/sofia` — Chat texto principal
- `/comunicacao` — hub VoIP outbound (Nova ligação / Em curso / Histórico)
- `/admin/cenarios-sofia` — CRUD playbooks de ligação (super_admin/admin_tenant)
- `/admin/regras-clinicas` — CRUD motor de cruzamentos
- `/alertas/clinicos` — alertas do dose_validator
- "Ligar via Sofia" botão contextual no `/patients/[id]`

### 8.2 Componentes especiais
- **PatientPicker** com search por nome/apelido + auto-fill de telefone do responsável
- **SofiaCallButton** com modal via React Portal (escapa transform do animate-fade-up parent) + polling pós-dial pra detectar trunk 403
- **AlertsPanel** + **ClinicalAlertCard** pra triagem clínica

### 8.3 Auth + RBAC
- JWT HS256 custom (sem PyJWT — implementação própria)
- 8 roles + permissions overridáveis por user (precedência: user.permissions > profile.permissions > role default)
- Multi-tenant via tenant_id em todas as queries

## 10. Scheduler infra (background workers)

| Worker | Tick | Função |
|--------|------|--------|
| `checkin_scheduler` | 30s | Dispara timeline de care events |
| `proactive_scheduler` | 15s | Check-ins B2C, lembretes |
| `dose_revalidation_scheduler` | 6h (efetivo 7 dias por prescription) | Re-roda motor sobre meds ativas |
| `collective_insights_scheduler` | 6h (efetivo 24h) | Anonimiza + extrai padrões cross-tenant |

Todos com `pg_try_advisory_lock` próprio pra single-writer entre workers Gunicorn.

## 11. Custos (estimativa por turn)

| Operação | Provider | Custo aprox. |
|----------|----------|--------------|
| Chat texto turn (3 tools média) | Gemini 3 Flash | ~$0.001 |
| Voz browser turn (Sofia 4-5s) | Grok Voice Realtime | ~$0.05/min de conexão |
| Ligação SIP turn | Grok Voice Realtime | ~$0.05/min Grok + ~R$0.20/min trunk |
| Memory extraction (per-user, 20 msgs) | Gemini Flash | ~$0.0005 |
| Collective insights (200 msgs/dia) | Gemini Flash medium | ~$0.005/dia |
| Dose validation | DB only | $0 (deterministic) |

## 12. Roadmap / pendências conhecidas

### 11.1 Curto prazo (próximas 2 sessões)
- [ ] Cron `outbound_call_scheduler` lê `aia_health_scheduled_calls` (RRULE) e dispara na hora
- [ ] Frontend tab "Agendadas" no `/comunicacao`
- [ ] Hooks pós-call efetivos (hoje placeholders): `create_lead_record`, `notify_admin_new_lead`, `update_lead_score`
- [ ] Trunk SIP — desbloquear com Flux ou trocar de operador (atualmente blocker)

### 11.2 Médio prazo (1-2 semanas)
- [ ] **Inbound calls** (Sofia atender) — exige número definitivo da ConnectaIA Care + roteador de cenário (caller_id resolve persona)
- [ ] **Embeddings ativos** (pgvector retrieval) substitui ILIKE atual
- [ ] **Recall semântico** como tool: `recall(query)` busca top-K mensagens passadas relevantes
- [ ] Service Worker no frontend pra invalidação de cache controlada
- [ ] **Frontend pacientes B2C** consentimento explícito de memória (LGPD)

### 11.3 Longo prazo
- [ ] **Detecção proativa de padrões** longitudinais (ex: 3 quedas em 2 semanas → alerta)
- [ ] **Multi-channel sync**: WhatsApp Business como 4º canal compartilhando memória/tools
- [ ] **Voice cloning** opcional pra cuidadores familiares (Grok suporta)
- [ ] **Intel comercial integrada à Sofia** (lead score baseado em signal externo)
- [ ] **Federated learning** entre tenants (insights coletivos hoje são cross-tenant — proximamente per-tenant com diferential privacy mais formal)

## 13. Visão autoral: prompt, contexto de execução, memória temporária e eterna
> Análise crítica do que está hoje e onde estão os pontos cegos arquiteturais.
> Escrita por Claude (Opus 4.7) co-construindo com o time. Útil pra o analista
> externo entender DECISÕES e TRADE-OFFS, não só o estado atual.

### 12.1 Prompt: bem estruturado mas com risco de "drift" silencioso

**Como está**:
- 5 prompts persona-específicos em arquivos `.txt` (sofia_*.txt) curtos (~140 linhas total)
- Prompt = `sofia_base.txt` + persona-específico + contexto de sessão + bloco de memória
- Cenários de ligação têm prompt PRÓPRIO armazenado em `aia_health_call_scenarios.system_prompt` (substitui o agent prompt no caso da call)

**Forças**:
- Separação clara entre "quem é a Sofia" (base) e "como ela se comporta nesta interação" (persona/cenário) — isso é raro de ver bem feito
- Prompts editáveis por admin sem deploy é poderoso operacionalmente
- Cenários têm regras anti-pânico/anti-diagnóstico EXPLÍCITAS, o que é vital em healthcare

**Riscos que vejo**:
1. **Sem versionamento de prompt**. Admin edita, entra em prod imediato. Não há "draft → review → publish". Se um admin alucinar uma regra ruim, fica em prod até alguém notar.
2. **Não há A/B test nem golden dataset**. Mudei o prompt → como sei que ficou melhor? Hoje só "tato" do user observando ligações.
3. **Prompts longos podem competir entre si**. Cenário tem 7-15KB → injeção de memória + contexto paciente + regras + tools_documentation explode contexto. Não medi degradação mas é matemática: contexto > 16k já começa a "esquecer" parte.
4. **Tom calibrado pro PT-BR é frágil**. Mudança de modelo (Gemini → Grok → Claude) pode mudar SUTILMENTE a interpretação. Comigo testando agora, talvez não percebamos drifts pequenos que cuidadores percebem.

**O que faria diferente**:
- Versionamento (table `aia_health_call_scenarios_versions`) com diff visível
- 1 prompt por arquivo Markdown com YAML frontmatter (model, voice, max_tokens, fallback_persona) → portável, diff-friendly em git
- "Eval set" com 10-20 conversas-tipo por cenário, rodar em CI quando prompt muda → snapshot de comportamento esperado
- Avisar admin "essa edição mudou X% das respostas em Y casos do golden set"

### 12.2 Contexto em execução: ainda subdimensionado

**Como está**:
- Por turn, Sofia recebe: system prompt (base+persona+memória) + últimas 30 mensagens da sessão atual + tool definitions
- No início de uma nova sessão, NÃO carrega histórico de sessões anteriores — só o `summary` da memória per-user
- Tools são carregadas TODAS na sessão (não há lazy loading)

**Forças**:
- Memória summary é pequena e cabe sempre — Sofia "sempre lembra de você" sem custo de contexto explodir
- Tools são deterministically filtradas por persona + cenário — sem ambiguidade de "qual tool a Sofia escolhe"

**Buracos arquiteturais**:
1. **Não há "active context"**: se médico está numa call falando do paciente Maria, e abre chat texto agora, Sofia chat NÃO sabe de Maria a menos que essa call tenha terminado e gerado memory update. Falha óbvia de UX.
2. **Tool documentation é estática**: cada tool tem description fixa. Sofia decide chamar baseada na description. Mas em healthcare contextos sutis importam muito ("dispneia leve" vs "respira mal") — precisaria de **few-shot examples** dentro da description. Hoje não tem.
3. **Não há "guardrail layer"**: Sofia decide sozinha quando chamar `create_care_event` com classification="critical". Se errar (false positive), gera ruído pra equipe; se errar (false negative), perdemos urgência. Idealmente um classifier dedicado validaria a classification ANTES de gravar.
4. **Sessions não compartilham contexto entre canais**: chat + voz browser + ligação criam sessões SEPARADAS por channel. Memória per-user é a ÚNICA conexão. Pra Sofia ser "uma Sofia só", precisaria unificar sessions OU ter "active context buffer" (últimos 5-10 turns de qualquer canal).

**O que faria diferente**:
- "Cross-channel session" com TTL de 30min: se mesmo user_id+patient_id em janela curta, share session_id mesmo trocando channel
- Tool descriptions com 1-2 few-shot examples ("Use isso pra: 'Dona Maria caiu agora' → classification=urgent. NÃO use pra: 'Dona Maria gosta de café' → ignore.")
- Output validator entre Sofia e DB: classification crítica passa por mini-classifier (Gemini Flash $0.0001) antes de virar care_event

### 12.3 Memória temporária (in-session): subutilizada

**Como está**:
- Cada turn lê últimas 30 mensagens da sessão (`list_recent_messages(session_id, 30)`)
- Sessão dura 1h de inatividade (`SESSION_INACTIVE_HOURS`) — depois cria nova
- Não há "scratchpad" para Sofia anotar coisas durante a conversa

**Forças**:
- Window de 30 msgs é honesto — cobre a maioria das interações sem inflar contexto
- 1h de inatividade é um trade-off razoável (continuidade vs separação semântica)

**Pontos cegos**:
1. **Sem working memory estruturada**. Quando user diz "lembra que falei do meu pai com Parkinson?", Sofia faz scan textual das 30 mensagens. Se foi a mensagem 31, perdeu. **Tool de "anote isso na working memory" seria barato e poderoso**.
2. **Sem detection de "fim de tópico"**. Conversa muda de assunto (de medicação pra agendamento), Sofia mantém contexto de medicação carregado. Idealmente: Sofia notaria a mudança e auto-resumiria o tópico anterior pra working memory.
3. **Tool outputs ficam no histórico inteiros**. Se chamou `query_drug_rules('omeprazol')` que retornou 20KB, isso fica pra todas as próximas turns. Custo cumulativo. Idealmente: cachear + sumarizar tool outputs grandes.

**O que faria diferente**:
- Tool `working_memory_set(key, value)` + `working_memory_get(key)` — Sofia anota fatos importantes durante a conversa, lê quando precisar
- Auto-summarize tool outputs > 4KB pra "essência factual"
- Topic tracking (Gemini Flash decide a cada N turns "estamos falando de X agora") — quando muda, fold previous topic into working memory

### 12.4 Memória eterna (cross-session): bom alicerce, mas sem profundidade

**Como está**:
**Per-user (`aia_health_sofia_user_memory`)**:
- 1 row por user
- `summary` (≤800 chars, gerado por LLM)
- `key_facts` JSONB com {role_context, preferences, ongoing_topics, concerns, key_patients}
- Re-extraído a cada 20 mensagens novas (cross-session counter)

**Cross-tenant coletiva (`aia_health_sofia_collective_insights_raw`)**:
- Pipeline batch diário: anonimiza → extrai padrões → freq ≥ 3 promove pra knowledge_chunks
- 5 tipos de insight: clinical_question, prescribing_pattern, feature_doubt, knowledge_gap, workflow_friction

**Forças**:
- Estrutura simples mas funcional — Sofia "lembra do Dr. Alexandre interessado em Beers + Losartana"
- Privacidade diferencial básica (freq ≥ 3) na camada coletiva é clean
- Anonimização dual-stage (regex + LLM safety pass) — robusta pra LGPD

**Limites significativos**:
1. **Memória per-user é SUMMARIZAÇÃO, não recall**. Sofia sabe que você se interessa por Beers, mas não consegue **recall verbatim** de "Lembra a 3ª pergunta que você fez sobre dose máxima de losartana?". Pra healthcare longitudinal isso importa.
2. **Sem "episodic memory"**. Não há "data X, conversa sobre paciente Y, decisão tomada Z". Tudo virou summary genérico. Médico que volta semanalmente perde rastreio fino.
3. **Memória per-user não captura RELACIONAMENTO**. Não sei "esse cuidador desconfia da Sofia, prefere falar com humano" mesmo se aconteceu 10x.
4. **Coletiva está em "insights" estruturados**, não memória emocional. "47 cuidadoras se preocuparam com queda de paciente Parkinson" vira 1 chunk frio. Tom emocional do coletivo se perde.
5. **Não tem decay**. Insight de 6 meses atrás continua com mesma confiança que insight de ontem. Em healthcare isso é PERIGOSO (regra clínica desatualizada continua sendo "verdade").

**O que faria diferente**:
- 3 camadas em vez de 2:
  - **Working memory** (in-session, sub-32k tokens, ephemera)
  - **Episodic memory** (per-user + per-patient: lista de "eventos memoráveis" com timestamp, nunca summarizado, busca via embedding)
  - **Semantic memory** (per-user, generalizações: preferências, papel, padrões recorrentes — o que temos hoje)
- Embeddings em messages históricas pra recall semântico ("você lembra quando falamos de X?")
- Decay function nos insights: confiança × exp(-0.05 × age_days) → insights antigos viram "histórico" mas não "fato corrente"
- Tracking de "trust signal": user concordou? user corrigiu? user repetiu pergunta? — sinais que afetam memory weight

### 12.5 Visão integrada: o gap conceitual mais importante

Hoje a Sofia tem:
- ✅ **Prompt** sólido por persona/cenário
- ✅ **Tool registry** completo e bem RBAC
- ✅ **Memória de longo prazo** funcional (summary + key_facts)
- ✅ **Knowledge base** com RAG
- ❌ **"Sense of self" longitudinal** — Sofia não sabe que o Dr. Alexandre tinha 30 pacientes ontem, perdeu 2 essa semana, e está mais ansioso. Sabe FATOS mas não TENDÊNCIAS.
- ❌ **Reasoning loop sobre o próprio comportamento** — Sofia não pode dizer "ontem te respondi X sobre Beers, hoje você corrigiu — vou ajustar minha approach pra futuro"

Esse gap é o que diferencia uma "ferramenta de IA" de uma "assistente de cuidado real". Pra cuidador familiar especialmente — eles formam VÍNCULO com cuidador humano, querem o mesmo com Sofia.

Caminho sugerido (sem ser feature-creep):
1. **Embeddings em messages históricas** + tool `recall(query)` → Sofia consegue lembrar fatos verbatim
2. **Trust signals** capturados (user corrigiu? agradeceu? repetiu?) → memória ganha "qualidade"
3. **Self-reflection** mensal: Sofia gera summary de "como evoluí com user X esse mês" → entra em key_facts.relationship
4. **Trend detection cross-message**: Sofia detecta padrões emocionais ("user mencionou cansaço 5x esse mês" → flag soft pra equipe).

### 12.6 Nota meta: como construímos isso

Esse sistema foi construído iterativamente em sessões de 4-8h com Claude no comando técnico e Alexandre direcionando produto. Cada decisão foi pragmática (deploy rápido, fix in-flight, memória dos bugs). O resultado é **funcional mas com pegadas de iteração** — alguns nomes legados (`bbmd_` em outras tabelas, mocks misturados a dados reais), schemas que evoluíram via ALTER em produção antes de migration commitada, e código com "marca d'água" do bug que originou (`# fix do incident X`).

Pra escala enterprise, vai precisar:
- **Refatoração de `voice_session.py` (Gemini)** — fica como zombie code, ninguém mais usa
- **Test suite real** — hoje só compile-checks + smoke manual
- **Observabilidade**: hoje é `docker logs | grep`. Pra pega bugs sutis (memória não atualizando, tool retornando errado), precisa de Sentry/Datadog/Grafana
- **Rate limiting por tenant** — hoje qualquer admin pode disparar 100 ligações em 1min e ninguém sabe

Mas a fundação está sólida. O motor de cruzamentos clínicos especialmente é diferencial competitivo real (não vi outro player BR de cuidado integrado com 12 dimensões + revalidação automática).

---

## 14. Limitações honestas (pra discutir com analista externo)

1. **Latência VoIP**: 500-800ms é boa pra Realtime, mas pra interação clínica (paciente idoso) ainda parece "robótico". Idealmente <300ms.

2. **VAD interrompe demais**: server VAD da Grok dispara em ruídos de fundo. Threshold ajustável mas ainda gera false positives.

3. **Memória per-user é enxuta**: 800 chars summary + key_facts agregados. Não captura nuances de longas sessões. Embeddings semânticos resolveriam.

4. **Knowledge chunks ainda manuais**: 19 chunks foram escritos por humano. Curadoria não escalável. Memória coletiva ajuda mas insights podem virar ruído se threshold não calibrado.

5. **Multi-modalidade não implementada**: Sofia hoje é só texto/áudio. Imagem (foto de receita, etiqueta de remédio) seria game-changer pra cuidador. Foundation já existe (medication_imports) mas não plugada.

6. **Audit chain não tem verificação automática**: hash chain inviolável MAS ninguém roda check periódico de integridade. Se admin malicioso conseguir bypass, ninguém saberia até alguém auditar manualmente.

7. **LGPD opt-in não tem UI ainda**: paciente B2C precisa consentir explicitamente memória, mas a tela de consentimento não foi construída. Hoje TRUE por default só pra profissionais (escopo seguro).

8. **Voice ainda não tem fallback se Grok cair**: queda de WS no meio da call termina sem mensagem TTS pré-gravada. Plano: gerar 1 wav "Tive problema técnico..." e tocar antes de desligar.

9. **Tools clínicas avançadas não estão no chat texto pra todos**: query_drug_rules / check_medication_safety são power-tools dos médicos. Cuidador/família não tem acesso (correto). Mas faltam tools "aplicáveis ao cuidador" como `verificar_se_pode_dar_remedio_agora(med, last_dose)`.

10. **Cross-tenant sharing**: insights coletivos hoje compartilham entre todos os tenants. Pra clientes corporativos enterprise pode ser deal-breaker. Plano: opt-out per-tenant + namespace.

## 15. Stack de IA usado

| Camada | Provider/Model | Onde |
|--------|----------------|------|
| LLM principal (chat) | Gemini 3 Flash Preview (xAI Grok como fallback) | sofia-service |
| Memory extraction | Gemini 3 Flash Preview | memory_service |
| Anonimização LLM | Gemini 3 Flash | collective_memory_service |
| Speech-to-speech (browser+SIP) | xAI Grok Voice Realtime (`grok-voice-think-fast-1.0`) | voice_session + grok_call_session |
| Speech-to-text (input transcription) | Whisper-1 via Grok | embutido na sessão Grok |
| TTS (fallback chat) | Gemini 2.5 Flash native-audio | tts_client.py |
| Embeddings (planejado, ainda não ativo) | text-embedding-3-small ou Gemini equivalente | knowledge_chunks |

## 16. Arquivos-chave para deep-dive

```
backend/
├── app.py                                          # Flask entrypoint, schedulers
├── migrations/                                     # 34 migrations (schema completo)
├── src/
│   ├── handlers/
│   │   ├── communications_routes.py                # Comunicações (CRUD scenarios + dial)
│   │   ├── alerts_routes.py                        # Alertas clínicos
│   │   ├── clinical_rules_routes.py                # CRUD motor + validate-prescription
│   │   └── voip_routes.py                          # Proxy pra voice-call-service
│   └── services/
│       ├── dose_validator.py                       # 12-dimensional validator
│       ├── dose_revalidation_scheduler.py          # Cron 7d revalidation
│       └── audit_service.py                        # Hash chain LGPD

sofia-service/
├── sofia_app.py                                    # Flask REST (chat + tool/execute + memory)
├── voice_app.py                                    # FastAPI WS bridge (Sofia Voz)
├── prompts/                                        # 5 personas .txt
└── src/
    ├── orchestrator.py                             # Persona routing
    ├── llm_client.py                               # Gemini wrapper
    ├── voice_session.py                            # Gemini Live (fallback)
    ├── grok_voice_session.py                       # Grok Realtime (default)
    ├── tools.py                                    # 16 tools registry
    ├── memory_service.py                           # Per-user memory
    ├── collective_memory_service.py                # Cross-tenant anonymized
    ├── collective_insights_scheduler.py            # Daily batch
    └── persistence.py                              # PG layer

voice-call-service/
├── voice_call_app.py                               # Flask + boot PJSIP
├── Dockerfile                                      # PJSIP 2.14 + Python 3.11
└── services/
    ├── sip_layer.py                                # PJSIP wrapper (singleton)
    ├── audio_bridge.py                             # 8k ↔ 24k resample
    ├── grok_call_session.py                        # Grok WS adaptado pra SIP
    └── persistence.py                              # Mesma PG, replica de tools

frontend/
└── src/
    ├── app/
    │   ├── comunicacao/page.tsx                    # Hub VoIP (3 tabs)
    │   ├── admin/cenarios-sofia/page.tsx           # CRUD playbooks
    │   ├── admin/regras-clinicas/page.tsx          # CRUD motor cruzamentos
    │   └── alertas/clinicos/page.tsx               # Alertas do validator
    └── components/prontuario/
        └── sofia-call-button.tsx                   # Modal contextual (Portal)
```

## 17. Perguntas que gostaria que o analista responda

1. **Arquitetura geral**: faz sentido manter 3 containers separados (api, sofia-service, voice-call-service) ou consolidar? Trade-off: isolamento de falhas vs complexidade ops.

2. **Estratégia de memória**: per-user (atual) é suficiente pra healthcare, ou precisamos episodic + semantic (estilo memGPT)?

3. **Custos vs qualidade**: faz sentido downgrade pra Gemini Lite em algumas tools (extração, anonimização) sem perder qualidade?

4. **Voice cloning** pra Sofia ter "voz de cuidadora confiança" — ROI vs complexidade LGPD (clonagem precisa consentimento explícito)?

5. **Embeddings**: ativar pgvector retrieval ou usar serviço dedicado (Pinecone/Weaviate) — para escalar pra 100k+ chunks?

6. **Inbound roteamento**: faz mais sentido roteador determinístico (caller_id → cenário) ou um LLM router que classifica intent na primeira frase?

7. **Multi-tenant + collective insights**: federated learning real (per-tenant model fine-tune) é exagero pra MVP ou já é diferencial competitivo?

8. **Compliance LGPD avançado**: que controles extras devemos ter antes de scale-up B2C (paciente sem clínica intermediária)?

9. **Quality gate pra prompts**: hoje admin edita prompt direto e entra em produção. Devemos ter fluxo "draft → A/B test → approve" antes?

10. **Telephony estratégia**: continuar com SIP trunk genérico (ATER, Flux), migrar pra Twilio (caro mas robusto) ou WebRTC direto (Vapi, LiveKit)?

---
**Próximo passo sugerido**: tomar essa análise externa e priorizar 3-5 itens
em uma sprint focada. Pessoalmente, considero como prioridade alta: (1)
embeddings ativos no RAG, (2) inbound calls com roteador, (3) UI de
consentimento LGPD pra B2C. Mas a análise externa pode reordenar.
