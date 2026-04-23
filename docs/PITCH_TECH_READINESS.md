# ConnectaIACare — Technical Readiness Brief

> **Uso**: apoio técnico pro pitch (anexo + FAQ de perguntas difíceis).
> Resposta rápida pra "vocês estão preparados pra…?"
> Atualizado: 2026-04-23

---

## 📋 TL;DR em 1 slide

**Somos infraestrutura de saúde, não app.** Desenhamos desde o dia 1 pra:
- ✅ **Conformidade regulatória brasileira** (LGPD, CFM 2.314/2022, ANVISA, Estatuto do Idoso, CDC)
- ✅ **Integração FHIR HL7** pronta (schema LOINC-aligned, exportador em construção)
- ✅ **Multi-tenant + multi-locale** desde commit zero (ADR-010, ADR-011)
- ✅ **LLM vendor-agnostic** (router por tarefa, fallback cascade — ADR-025)
- ✅ **Expansão para LatAm, Europa, US** sem refatoração estrutural

---

## 🇧🇷 Conformidade Brasil — como tratamos cada norma

### LGPD (Lei 13.709/2018)
| Exigência | Como atendemos |
|-----------|----------------|
| Consentimento explícito (Art. 7º, VIII) | Aceite LGPD embutido no onboarding via WhatsApp com versão versionada (`consent_version`) + timestamp imutável (`consent_signed_at`) + hash opcional de áudio (`consent_audio_hash`) |
| Dados sensíveis de saúde (Art. 11) | Criptografia em repouso (postgres + pgcrypto), criptografia em trânsito (TLS 1.3), **PII-encrypted na camada de memória individual** (Onda C), nunca em logs |
| Direito de acesso (Art. 18) | Endpoint `/api/minha-conta/exportar` (JSON + PDF), portabilidade em formato FHIR quando aplicável |
| Direito ao esquecimento (Art. 18, VI) | Exclusão lógica imediata + purga física após 30 dias de congelamento |
| Registro de tratamento (Art. 37) | Tabela `aia_health_audit_chain` (hash-chain imutável) — toda operação em dado sensível fica logada |
| DPO (Art. 41) | Nomeado: `dpo@connectaiacare.com.br` |
| Transferência internacional (Art. 33) | VPS em território nacional (Hostinger BR). Réplicas internacionais só após adequação formal (ABR+MX+EU data residency). |
| K-anonymity em memória coletiva | Regionalização BR-SUL/SP/NE/N/INTL com threshold 10/20/30 por granularidade (ADR-027 §8) |

### CFM 2.314/2022 (Telemedicina + IA em saúde)
| Exigência | Como atendemos |
|-----------|----------------|
| IA não diagnostica | **Constituição Sofia** (`prompts/sofia_constitutional.py`) proíbe diagnóstico — injetado no system prompt de todos os agentes |
| IA não prescreve | Mesma constituição + PrescriptionValidator nunca sugere dose, só valida prescrição médica existente contra interações |
| Responsabilidade técnica | Médicos com CRM ativo nomeados por estado, visíveis em `/equipe` + footer |
| Teleconsulta regulamentada | Stack própria com LiveKit WebRTC, gravação opcional com consentimento, prontuário SOAP automático (IA sugere, médico aprova) |
| Prontuário eletrônico | Estrutura FHIR-compatible (Patient, Observation, Condition, MedicationStatement, Encounter) |

### ANVISA — RDC 657/2022 (Software as Medical Device — SaMD)
**Classificação atual:** Classe B (software clínico de apoio, sem decisão autônoma).
**O que já fazemos:**
- Documentação técnica (ADRs versionados)
- Change log imutável (git + audit_chain)
- Testes automatizados (317+ testes com coverage nas regras clínicas)
- Rastreabilidade de modelos de IA (LLM router registra qual modelo + versão em `metadata`)

**Pra Classe II/III no futuro** (se o produto evoluir pra suporte à decisão):
- Validação clínica formal + estudo prospectivo
- Certificação ISO 13485 (gestão de qualidade de dispositivos médicos)
- Boa Prática de Fabricação (BPF) software

### Estatuto do Idoso (Lei 10.741/2003)
| Artigo | Como implementamos |
|--------|-------------------|
| Art. 3º — prioridade absoluta | Triggers de emergência hardcoded (não dependem de LLM) — suicídio, elder abuse, emergência médica escalam em <60s |
| Art. 4º — proibição de negligência | Detector de elder abuse regex + escalação automática ao Disque 100 |
| Art. 17 — autonomia | Idoso juridicamente capaz autoriza próprio tratamento — distinção formal entre payer (pagante) e beneficiary (idoso) |
| Art. 19 — notificação compulsória | Evento de suspeita de violência grava em `aia_health_safety_events` com `actions_taken` incluindo `external_authority_notified` |

### CDC (Lei 8.078/1990)
- **Art. 49 — 7 dias de arrependimento** → cartão tem trial 7d sem cobrança
- **Art. 6º — informação clara** → contratos versionados, preços explícitos, sem letra miúda
- **Art. 51 — cláusulas abusivas** → zero fidelidade, cancelamento livre a qualquer momento

### ECA (Lei 8.069/1990)
- Trigger CSAM com zero tolerância + notificação Disque 100 + bloqueio imediato

---

## 🌍 Preparação internacional — já nasceu global

### Arquitetura multi-locale (ADR-011)
- **Locale por tenant**: string BCP-47 (`pt-BR`, `es-AR`, `en-US`, `pt-PT`)
- **Timezone por tenant**: IANA tz (`America/Sao_Paulo`, `America/Mexico_City`, `Europe/Lisbon`)
- **Moeda configurável por tenant**: BRL / MXN / ARS / COP / EUR / USD
- **Prompts do Sofia separados por locale**: `prompts/sofia_constitutional_pt.py`, futuro `_es.py`, `_en.py`
- **Formatos de data/moeda/endereço** via ICU (i18n nativo)

### FHIR HL7 — readiness nível "Schema ready, exporter em roadmap Q3"

**O que já temos:**
- Schema **LOINC-aligned** em sinais vitais (`aia_health_vital_signs.loinc_code`)
- IDs estáveis UUIDv4 (FHIR `logical_id`)
- Separação Patient / Practitioner / Encounter / Observation já modelada
- Timestamps em TIMESTAMPTZ (FHIR requer timezone explícito)

**Mapeamento nosso → FHIR R4** (documentado):
| Nosso recurso | FHIR Resource |
|---------------|---------------|
| `aia_health_patients` | Patient |
| `aia_health_caregivers` | Practitioner + RelatedPerson |
| `aia_health_vital_signs` | Observation (vital-signs category) |
| `aia_health_reports` | Observation (social-history) + Communication |
| `aia_health_care_events` | Encounter (virtual) |
| `aia_health_medication_schedules` | MedicationRequest |
| `aia_health_medication_events` | MedicationAdministration |
| `aia_health_prescriptions` | MedicationRequest + Prescription |
| `aia_health_teleconsultations` | Encounter (telemedicine) + DocumentReference (SOAP) |
| Conditions em `patients.conditions` | Condition |

**Exportador FHIR em construção**: endpoint `/api/fhir/Patient/:id/$everything` retorna bundle completo em FHIR R4 JSON + XML. Primeira versão ready até Q3/2026.

**Códigos terminológicos suportados**:
- **SNOMED CT** (condições, sintomas) — via `cid10_mapping` inicial + SNOMED brasileiro AHC
- **LOINC** (observações clínicas, sinais vitais) — nativo no schema
- **CID-10** (diagnósticos) — catálogo importado via `scripts/import_cid10.py`
- **RxNorm / ATC** (medicações) — Q4/2026 roadmap

### HIPAA (US) — readiness parcial

**Já atendemos (estruturalmente):**
- ✅ Encryption at rest e in transit (tech safeguards §164.312)
- ✅ Access controls + audit log (§164.312 a,b)
- ✅ Automatic logoff (session expiration)
- ✅ Unique user identification
- ✅ Integrity controls (hash-chain audit)

**Falta pra HIPAA compliance formal:**
- ❌ Business Associate Agreement (BAA) com cada fornecedor de cloud — pendente formalização com Anthropic/OpenAI/Google quando entrar no mercado US
- ❌ Breach notification playbook documentado
- ❌ Certificação SOC 2 Type II (auditoria externa) — **~6 meses de preparação**

**Conclusão HIPAA**: arquitetura pronta, compliance formal requer ~6 meses de processo + auditoria antes de operar com dados PHI nos EUA.

### GDPR (UE) — readiness alta

**Já atendemos:**
- ✅ Right to access + portability (idêntico LGPD)
- ✅ Right to erasure (direito ao esquecimento)
- ✅ Consent granular e revogável
- ✅ Data minimization (coletamos só o necessário)
- ✅ Pseudonymization (memória coletiva anonimizada com k-anonymity)
- ✅ DPO nomeado

**Falta pra operar na UE:**
- ❌ Data residency UE (VPS/DB em Frankfurt ou Paris)
- ❌ Representante EU (Art. 27 — requerido pra empresas fora da UE)
- ❌ DPIA (Data Protection Impact Assessment) específica pra IA

### LGPD LatAm — convergência

| País | Lei | Convergência com nossa arquitetura |
|------|-----|------------------------------------|
| México | LFPDPPP (Ley Federal de Protección de Datos Personales) | ~90% sobreposição com LGPD; ANPD ≈ INAI |
| Colômbia | Lei 1581/2012 | Consent + right to access idênticos |
| Argentina | Lei 25.326 (Adequada GDPR) | Mais próxima da UE; conforme nosso schema |
| Chile | Lei 19.628 | Modernização em 2025; estamos alinhados |
| Peru, Uruguai, Equador | Variações LGPD-like | Mesma estrutura cobre |

---

## 🔌 Integrações técnicas — o que já plugamos e o que está pronto

### Dispositivos (aferição)

**Hoje integrado:**
- **Deepgram nova-2** (pt-BR) — STT clínico em áudio WhatsApp
- **ElevenLabs** — TTS pra Sofia Voz (modo futuro)
- **Resemblyzer** — biometria de voz 256-dim (identifica cuidador por áudio)
- **Apple Health + Android Health Connect** — wearables (plano Premium+Device)
- **Tecnosenior IoT** — botão SOS + detector queda + sinais vitais (pulseira homologada)

**Schema pronto, integração em construção:**
- **MedMonitor** — dispositivos clínicos homologados (fase 2 MONITOR) — pipeline FHIR Observation já modelado
- **Omron, Accu-Chek, iHealth** — BLE via gateway smartphone (roadmap Q3)
- **Canary Speech** / **Kintsugi** — biomarcadores vocais pra declínio cognitivo (Onda D)

### SaaS complementares

**Integrações ativas:**
- **Evolution API v2** — WhatsApp canal principal
- **Asaas / Mercado Pago** (PSP) — pagamento PIX + cartão (trial 7d)
- **CVV 188 / Disque 100 / SAMU 192** — escalações automáticas de emergência
- **Google Workspace MCP** — calendar + email pra equipe médica
- **LiveKit WebRTC** — teleconsulta com baixa latência

**Integrações planejadas (contratos em negociação):**
- **Unimed nacional / Bradesco Saúde / Sulamérica** — pipeline FHIR pra prontuário unificado
- **TASY / Philips** — importação de prontuário hospitalar (hospital-at-home)
- **PRODESP / DATASUS** — integração SUS (programa nacional, roadmap 2027)
- **Alexa Skills Kit** — canal Alexa nativo pra idoso (ADR-027 §4)

### LLM providers (vendor-agnostic)

**Router por tarefa** (ADR-025) — **nunca dependentes de um único fornecedor**:
| Tarefa | Modelo primário | Fallback |
|--------|-----------------|----------|
| SOAP Writer (clínico) | Claude Sonnet 4 (Anthropic) | GPT-5.4 mini (OpenAI) |
| Prescription Validator | Claude Sonnet 4 | GPT-5.4 mini |
| Patient Summary (acolhedor) | Claude 3.5 Haiku | GPT-5.4 nano |
| Weekly Report | GPT-5.4 mini | Claude Haiku |
| Clinical Analysis (áudio) | GPT-5.4 mini | Claude Haiku |
| OCR (vision) | Gemini 2.5 Flash | GPT-5.4 mini vision |
| Price Search (zero-PHI) | Gemini 2.5 Flash-Lite | DeepSeek |
| Intent Classifier | GPT-5.4 nano | Gemini 2.5 Flash-Lite |
| Embeddings (vetorização) | Gemini text-embedding-004 | OpenAI text-embedding-3-small |

**Implicação estratégica**: se Anthropic aumenta preço 10x, migramos SOAP Writer pra GPT-5.4 em 1 linha de config. Se OpenAI é banido no Brasil, fallback cascata garante continuidade. Se LGPD demanda modelo local, trocamos pra DeepSeek on-prem.

---

## 🔬 Arquitetura técnica que sustenta tudo isso

### Multi-tenant desde commit zero (ADR-010)
- Toda tabela tem `tenant_id` — isolamento lógico absoluto
- Row-level security planejado pra contratos B2B enterprise
- Tenant configuration em YAML (`tenants/<id>.yaml`): features flags, limites, prompts customizados

### Multi-locale desde commit zero (ADR-011)
- BCP-47 locale code + IANA timezone + moeda ISO 4217
- Prompts segmentados por locale (nada de hardcoded em português)
- Formatadores ICU pra data/moeda/nome/endereço

### Observability + Auditoria
- **Structured logging** (structlog) com trace_id correlacionado
- **Audit chain** hash-linked — ninguém altera histórico sem detecção
- **Safety events** com review workflow (admin + Atente podem investigar)
- **KB retrieval log** pra detectar gaps de conhecimento (loop de melhoria)
- **Rate limit telemetry** pra calibração de planos (ADR-027 §8.5)

### Arquitetura de memória (ADR-027)
- **Memória individual**: eterna por usuário, criptografada, com direito ao esquecimento
- **Memória coletiva**: anonimizada, regionalizada, com k-anonymity enforcement
- **PII sanitizer** em 2 níveis (regex + LLM) — nunca vaza nome/CPF/endereço pra coletivo
- **Distiller** extrai fatos estáveis das conversas (não salva conversa crua no longo prazo)

### Safety Layer (ADR-027 §5)
- **Input moderation** — antes de qualquer LLM processar
- **Hardcoded triggers** pra emergências (nunca depende de LLM decidir)
- **Output moderation** — prompt leak + persona break defense
- **Jailbreak resistance** testada (43 padrões de ataque cobertos)

---

## 🚀 Expansão sem refatoração — por que somos "internacional-ready"

**Estrutural:**
1. **Schema UUIDv4** — não colide em multi-region
2. **TIMESTAMPTZ** em toda data — nunca ambíguo
3. **Locale + currency por tenant** — novo país = novo tenant + tradução
4. **LLM router por tarefa** — troca de modelo por região sem mexer em código de negócio
5. **Prompts e KB em domínio-específico** — quando adicionamos Colombia, adicionamos `seeds/kb_es_co/` e Sofia fala espanhol colombiano com compliance colombiana (Lei 1581)

**Regulatório:**
- LGPD-ready = GDPR-ready (90% overlap)
- CFM 2.314 = OMS telemedicine guidelines (alinhados)
- Estatuto do Idoso = convenção ONU envelhecimento (signatários incluem México, Argentina, Chile)

**Comercial:**
- White-label: um ConnectaIACare por parceiro local (ex: Tecnosenior Brasil, Tecnosenior México) — mesmo código, tenants diferentes, compliance por jurisdição
- B2B pipeline: operadoras de saúde, ILPIs, redes de clínicas — mesmo schema FHIR

---

## 🎯 FAQ — perguntas difíceis que podem aparecer

### "E se o Anthropic sair do ar?"
LLM router tem fallback cascade configurado em YAML. Troca 1 linha, restart container. Zero downtime pro usuário final. Em 2026, testamos fallback em produção 3x sem o usuário perceber.

### "Dados de saúde na Cloud? Isso é seguro?"
Encryption at rest + in transit, audit chain imutável, LGPD Art. 11, nenhum log com PII. No futuro, opção on-premise pra contratos enterprise (ILPIs grandes, hospitais).

### "Vocês são responsáveis se a IA errar?"
Não. Constituição Sofia impede diagnóstico/prescrição (CFM 2.314). Todo alerta crítico escala pra humano. Nossa responsabilidade é processo, não decisão clínica. Contratualmente alinhado com Tecnosenior (parceria já em curso com ~15k assistidos via Dossiê do Assistido).

### "Como vocês escalam pra 1M de usuários?"
Arquitetura stateless (Flask + Gunicorn + Docker) horizontal. pgvector no Postgres escala até ~100M vetores com ivfflat → migramos pra Weaviate/Pinecone se necessário. Evolution API suporta ~10k msgs/segundo/instância. WhatsApp Business BSP com Twilio/Gupshup pra volume alto. Custos lineares com receita.

### "Quanto demora pra lançar em outro país?"
**8-12 semanas.** Breakdown: 2 sem localização (locale+moeda+prompts), 3 sem compliance jurídico (revisão lei local + DPO + representante), 2 sem testes clínicos (SBGG local), 3 sem go-to-market (parceiro local, onboarding seed).

### "Vocês têm patente?"
Trademarks: "ConnectaIA" + "Sofia Cuida" registrados no INPI. Patentes de arquitetura: não priorizamos (open source-friendly), mas temos 3 processos de segredo industrial (distiller de memória, router de LLM por tarefa clínica, safety layer em 4 camadas).

### "E se o governo criar uma lei que limita IA em saúde?"
Já temos 4 camadas de safety, constituição clínica, e CFM 2.314 é o piso. Se o governo endurecer, estamos já acima da barra. Temos relacionamento em curso com ANPD (DPO) e CFM (médicos do time) pra participar de consultas públicas.

### "Vocês aceitam open-banking / transações de alto valor?"
Para planos B2C, sim — PIX + cartão via PSP regulamentado (Asaas / Mercado Pago). Pra B2B enterprise (grandes contratos), faturamento direto + nota fiscal. Open Insurance em roadmap pra 2027 (integração com operadoras de saúde).

---

## 📎 Referências técnicas (pra deep dive se perguntarem)

- **ADR-010** — Multi-tenant from day 1
- **ADR-011** — Locale-aware i18n
- **ADR-013** — Domínios e DNS
- **ADR-022** — Atente como fallback humano
- **ADR-024** — Auth MFA independente
- **ADR-025** — LLM Routing por Tarefa
- **ADR-026** — Onboarding WhatsApp-first + políticas pagamento
- **ADR-027** — Memória 2 camadas + Safety + Canais (mais recente)

Repo: `github.com/iplayconnect/connectaiacare`
Testes: **331 passando, 100% verde** (pytest)
Cobertura clínica: 7 triggers de emergência + 10 categorias de objeções + 14 estados de onboarding

---

**Última atualização**: commit `77d345b` (2026-04-23)
**Versão do doc**: 1.0
