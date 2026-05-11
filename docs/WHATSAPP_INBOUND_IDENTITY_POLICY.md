# Política de Identificação WhatsApp Inbound + Biometria de Voz

**Status:** Decidido por Alexandre 2026-05-10. Spec pra implementação das Entregas A/B/C.
**Pré-requisitos já entregues:** schema (migrations 003/050/052/059), services (`identity_resolver`, `tenant_resolver`, `voice_biometrics_service`), webhook async (`webhook_async_routes` + `sofia_inbound_worker`).

---

## Princípio fundamental

**O número de WhatsApp é a fonte de verdade primária.** A biometria de voz é um camada **adicional** de identificação **dentro** de um número já cadastrado — nunca substitui o phone.

Decorrência: se o número não está cadastrado, **não tentamos identificar voz** — encaminhamos pro fluxo comercial/suporte.

---

## Matriz de decisão (5 cenários)

### Cenário 1 — Número desconhecido (lead novo ou ruído)

**Trigger:** `IdentityResolver.resolve(phone, tenant)` retorna lista vazia.

**Ação:**
- ❌ NÃO tentar `identify_any_1toN` na voz
- ✅ Rotear pro **fluxo comercial** (lead) ou **suporte** (dúvida administrativa) conforme a primeira mensagem
- Captura mínima: phone + 1ª mensagem + horário + qual instância recebeu

**Por que:** o número é a chave. Sem cadastro prévio, qualquer match biométrico seria coincidência (risco de falso-positivo grave em LGPD/atendimento).

---

### Cenário 2 — Número cadastrado · voz **bate** com identidade do número

**Trigger:** Phone resolve para 1 identidade no `IdentityResolver`. Áudio passa pelo `verify_1to1` ou `identify_any_1toN` e o score ≥ threshold (0.75 para 1:1, 0.65 para 1:N).

**Ação:**
- ✅ `reporter_person_type` = role da identidade (paciente, cuidador, familiar, médico, enfermeiro)
- ✅ Trust score alto — segue fluxo normal de relato/conversa
- ✅ Log em `voice_consent_log` com `action='identity_resolved'`

---

### Cenário 3 — Número do PACIENTE · voz **NÃO bate** com voiceprint do paciente

**Trigger:** Phone resolve pra paciente. Voz tem score < threshold OU bate com identidade de pessoa do mesmo grupo de cuidado (familiar/cuidador/médico vinculado àquele paciente).

**Sub-caso 3.1 — Voz bate com pessoa vinculada ao paciente (familiar/cuidador/médico do círculo dele):**
- ✅ Sofia confirma: "Olá [nome], notei que você está usando o telefone do(a) [paciente]. Tudo bem com ele(a)? Está acontecendo alguma emergência?"
- ✅ Reporter = a pessoa identificada pela voz, **contexto = paciente do número**
- ✅ Trust score normal pra emergência (alguém do círculo de cuidado usa celular do idoso só em momento crítico)
- ✅ Log: `identity_resolved` com `metadata = {phone_owner: patient_id, voice_match: caregiver_id, scenario: "caregiver_on_patient_phone"}`

**Sub-caso 3.2 — Voz não bate com ninguém do círculo:**
- ⚠️ Sofia pergunta: "Olá! Notei que esse é o telefone do(a) [paciente]. Posso saber com quem estou falando? É da família, cuidador(a) ou outra pessoa?"
- Resposta determina próximo fluxo:
  - "Sou o filho/neto/etc." → propõe enrollment (Cenário 5)
  - "Sou cuidador novo" → propõe enrollment + alerta o gestor da unidade
  - "Sou amigo/visita ocasional" → registra mas não pede enrollment

---

### Cenário 4 — Número aparece em **mais de 1 tenant** (cuidador em 2 ILPIs)

**Trigger:** `IdentityResolver` retorna identidades em `tenant_id` diferentes.

**Ação:**
- Sofia pergunta: "Você atua em [Tenant A] e [Tenant B]. Em qual você está atendendo agora?"
- Resposta cria **contexto de sessão** (Redis, TTL 4h) que sobrepõe o webhook routing dali pra frente
- Próximas mensagens da mesma sessão vão pro tenant escolhido sem reperguntar
- Log: `identity_resolved` com `metadata = {scenario: "multi_tenant_disambiguation", chosen: tenant_id, candidates: [...]}`

**Edge case:** se o cuidador não responder em 5min, padrão é o tenant **mais recentemente ativo** (último relato/interação) e a Sofia avisa: "Vou seguir como [Tenant X], me corrija se for outro."

---

### Cenário 5 — Familiar/cuidador novo no celular **dele próprio** (não do paciente)

**Trigger:** Phone bate com `responsible.phone` (cadastrado quando o paciente foi cadastrado), mas **ainda não tem voiceprint próprio** registrado.

**Ação — proposta de enrollment via WhatsApp:**
1. Sofia: "Oi [nome]! Vi aqui que você é [filho(a) / esposo(a) / cuidador(a)] do(a) [paciente]. Posso fazer um cadastro rápido da sua voz? Isso me ajuda a identificar você quando ligar pra falar do(a) [paciente] e a entender se quem está falando é familiar ou o(a) próprio(a) [paciente]. Demora ~30 segundos."
2. Se aceita ("sim", "pode", "claro"):
   - Sofia: "Perfeito! Me manda 3 áudios de uns 5 segundos cada, dizendo livremente uma frase qualquer (ex: 'meu nome é [nome] e eu cuido do(a) [paciente]')"
   - Cada áudio recebido vai pro `enroll_caregiver` (ou novo `enroll_responsible_family`) automaticamente
   - Após 3 amostras válidas: confirmação "Pronto! Cadastrado. Já consigo te reconhecer da próxima vez."
3. Se recusa ("não", "agora não"):
   - Sofia: "Sem problema. Quando quiser fazer, é só me avisar 'cadastrar minha voz'."
   - Marca `voice_enrollment_offered_at` no perfil pra não reperguntar antes de 30 dias

**Quem é elegível pra enrollment via WhatsApp (B2C):**
- ✅ Lead que veio do fluxo comercial e virou paciente
- ✅ Familiar responsável cadastrado no `responsible` do paciente
- ✅ Cuidador novo cadastrado no tenant
- ✅ Médico ou enfermeiro vinculado a um paciente
- ❌ Quem não está em nenhuma das categorias acima

---

## Suporte a fluxos por **voz E texto** (não só voz)

Decisão Alexandre: a plataforma trabalha **com os dois canais sempre**. Texto e áudio recebem o mesmo tratamento de identificação:
- **Áudio** → tenta biometria de voz quando aplicável
- **Texto** → identifica só pelo phone + role declarado
- **Mensagem mista** (texto + áudio na mesma sessão) → texto roteia, voz adiciona confiança

Ou seja: o sistema **nunca exige** áudio pra identificar — voz é um sinal complementar quando disponível.

---

## Calibração de thresholds — política provisória

**Hoje:** thresholds 0.75 (1:1) e 0.65 (1:N) vêm da literatura do Resemblyzer, sem validação local.

**Esta semana:** Alexandre vai solicitar áudios reais de usuários atuais pra cadastrar amostras. Plano:
1. Coletar 3 amostras de ≥10 usuários distintos (idosos + cuidadores + familiares)
2. Rodar `tools/voice_threshold_calibration.py` (script a criar) que computa:
   - Distribuição de scores intra-pessoa (mesmo falante × suas próprias amostras)
   - Distribuição inter-pessoa (falantes diferentes)
   - EER (Equal Error Rate) e DCF (Detection Cost Function)
3. Ajustar thresholds pra **FAR=1%** (false accept rate — alguém ser identificado errado) com FRR mínimo
4. Documentar curva ROC em `docs/STATUS_BIOMETRIA_<data>.md`

**Até lá:** mantemos os thresholds da literatura mas **toda decisão `verify_1to1` ou `identify_any_1toN`** vai pra `voice_consent_log` com `metadata.calibration=true` (já implementado em `_log_calibration`). Conseguimos retroativamente calcular as métricas reais a partir desse log.

---

## Roadmap de implementação

### Entrega A — Hardening (1-2 dias) · em andamento
- [x] RBAC nos endpoints de voz (já estava feito — não estava no plano antigo)
- [ ] Migration `078_voice_consent_explicit.sql`:
  - Adiciona `consent_text TEXT` e `consent_version TEXT` em `voice_consent_log`
  - Adiciona action `identity_resolved` no CHECK
- [ ] Endpoint `/api/voice/consent` (POST) — registra explicitamente "[fulano] aceitou o termo X em [data]"
- [ ] Adicionar `write_audit()` central nos endpoints de enroll/delete
- [ ] Frontend: modal de consentimento LGPD antes do 1º enrollment (ver Phase 3 abaixo — prazo curto, pode ser PR separado)

### Entrega B — Onboarding via WhatsApp (3-5 dias)
1. **Service `voice_onboarding_service.py`** — gerencia o fluxo conversacional de enrollment
   - Estado: `not_offered | offered | awaiting_sample_1 | awaiting_sample_2 | awaiting_sample_3 | enrolled | declined`
   - Persiste em Redis (TTL 24h pra retomar depois)
   - Transições disparadas pelo worker do webhook quando detecta o cenário
2. **Detector "voz não identificada em phone cadastrado"** no `sofia_inbound_worker`
   - Após `identify_any_1toN` retornar `None`/score baixo, e identidade do phone existir → dispara cenário 3.1 ou 3.2
3. **Helper `propose_enrollment(phone, tenant, person_type)`** — gera texto de proposta + envia via Sofia
4. **Tabela `aia_health_voice_enrollment_offers`** (opcional, simples):
   - phone, tenant_id, person_type_offered, status, offered_at, accepted_at, declined_at, completed_at
5. **Endpoints** `/api/voice/onboarding/status?phone=X` (admin) e `/api/voice/onboarding/restart` (admin)

### Entrega C — Casos ambíguos (planejar agora, implementar depois)
- Política formal "cuidador no telefone do paciente" → já documentada acima (cenário 3.1), restará só implementar
- Política formal "tenant duplicado" → já documentada (cenário 4), restará implementar contexto de sessão Redis
- Re-enrollment programado: scheduler que dispara `propose_enrollment` pra usuários com voiceprint > 6 meses

---

## Métricas de sucesso (próximos 90 dias)

- **Cobertura biométrica:** % de inbound com `caregiver_voice_method` ≠ `none` deve atingir 60%+ em 90 dias
- **Taxa de enrollment offered → accepted:** baseline esperado 40-50% (familiares costumam aceitar; cuidadores variam)
- **False accept rate medido:** após calibração com áudios reais, manter FAR ≤ 1%
- **Casos de "voz no telefone errado" detectados:** medir quantas vezes o cenário 3.1 dispara (proxy de quantas emergências passariam batidas sem o sistema)

---

## Apêndice — Mapping inicial: cenário → action no log

| Cenário | `voice_consent_log.action` | `metadata.scenario` |
|---|---|---|
| 1 — Número desconhecido | (nada — fluxo comercial) | — |
| 2 — Voz bate com phone | `identity_resolved` | `direct_match` |
| 3.1 — Cuidador no fone do paciente | `identity_resolved` | `caregiver_on_patient_phone` |
| 3.2 — Voz desconhecida no fone do paciente | `identity_resolved` | `unknown_voice_on_patient_phone` |
| 4 — Tenant ambíguo | `identity_resolved` | `multi_tenant_disambiguation` |
| 5 — Enrollment proposto | `consent_given` (se aceitar) | `whatsapp_enrollment_offered` |

Esse log dá observabilidade de tudo que o sistema decidiu — base pra debug + futura calibração.
