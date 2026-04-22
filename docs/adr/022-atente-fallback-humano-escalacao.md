# ADR-022: Atente como fallback humano de escalação (substitui SAMU automático)

- **Date**: 2026-04-21
- **Status**: Accepted
- **Deciders**: Alexandre (ConnectaIA/Atente), Milene (Atente)
- **Tags**: escalation, compliance, partnership, human-in-the-loop
- **Relates to**: [ADR-020](020-escalacao-hierarquica-evolution-sofia.md) (escalação), [ADR-018](018-care-events-com-ciclo-de-vida.md) (care events)

## Context and Problem Statement

ADR-020 definiu a cascata hierárquica de escalação: central → enfermagem → médico → família 1/2/3. Em discussões iniciais (2026-04-20), consideramos **acionamento automático do SAMU/192** como último nível quando família 3 também não respondesse.

Durante sprint review em 21/04, duas questões importantes vieram à tona:

1. **Responsabilidade jurídica**: acionar SAMU via IA é terreno jurídico pantanoso — CFM 2.314/2022 limita autonomia de IA em decisões clínicas, e SAMU não tem API pública no Brasil (ligação automatizada via bot pode ser rejeitada pelo operador humano e gerar risco legal).

2. **Ecossistema empresarial pertencente ao Alexandre/Milene**: a **Atente** (empresa do Alexandre + Milene, "BPO de atendimento humanizado 24h pra saúde") **já opera central humana** hoje, recebendo alertas de dispositivos Vidafone/botões SOS de idosos em parceria com a Tecnosenior. Atente é **operação irmã** da ConnectaIA, não terceiro.

Isso reformula o problema: **por que acionar SAMU via IA se temos central humana profissional operando 24/7 com equipe treinada?**

## Decision Drivers

- **Menor responsabilidade algorítmica**: decisões de acionamento de emergência ficam com humano treinado, não IA
- **Compliance CFM mais simples**: IA é triagem + orquestração, não tomada de decisão crítica
- **Reuso de infraestrutura existente**: Atente já tem operadores, processos, relacionamento com famílias
- **Experiência humanizada**: "IA humanizada" é o tagline da Atente — nossa plataforma potencializa o produto deles, não substitui
- **Integração com SAMU (quando aplicável) fica no lado humano**: Atente decide + aciona conforme protocolo interno
- **Escalabilidade preservada**: Atente pode expandir equipe conforme volume cresce; IA continua fazendo triagem e filtrando ruído

## Considered Options

- **Option A**: Cascata termina em família 3; se sem resposta, evento fica em `expired` silencioso
- **Option B**: Acionamento automático SAMU via Sofia Voice (descartado por ADR inicial)
- **Option C**: Atente como **último nível** da cascata, recebendo eventos sem resposta como prioridade humana (escolhida)
- **Option D**: Atente como **primeiro nível** sempre (recebe todos os eventos)

## Decision Outcome

Chosen option: **Option C — Atente como fallback humano priorizado**.

### Fluxo de escalação atualizado

```
Evento urgent/critical aberto
  ↓
Paralelo imediato: central + nurse + doctor (WhatsApp + Sofia Voice)
  ↓ (nenhum respondeu em escalation_level1_wait_min)
Família nível 1 (cascata)
  ↓ (sem resposta em escalation_level2_wait_min)
Família nível 2
  ↓ (sem resposta em escalation_level3_wait_min)
Família nível 3
  ↓ (sem resposta)
**ATENTE — operador humano recebe caso priorizado** ← novo último nível
  ↓
Atente decide (protocolo interno):
  - Liga família manualmente (com mais contexto técnico)
  - Aciona SAMU (se paciente em risco real)
  - Despacha enfermeira do plantão (se parceria com SPA ativa)
  - Agenda follow-up com equipe
  - Marca evento como "escalation_exhausted_contacted_atente"
```

### Papel novo no tenant_config

Adicionar `atente` como role na `escalation_policy`:

```yaml
# tenants/connectaiacare_demo.yaml  (exemplo)
escalation_policy:
  critical:  [central, nurse, doctor, family_1, family_2, family_3, atente]
  urgent:    [central, nurse, family_1, atente]
  attention: [central, atente]
  routine:   []

# Contatos institucionais
tenant_config:
  atente_central_phone: "5551XXXXXXXXX"  # central 24h Atente
  atente_central_name: "Central Atente"
  atente_voice_url: null                 # ligação voice futura via Sofia
  atente_escalation_priority: high       # fura fila: chegam antes de alertas de rotina
```

### Mensagem específica para Atente (role técnica)

Operadores Atente são profissionais treinados — a mensagem que eles recebem é **técnica e contextualizada**, não acolhedora (como é pra família):

```
🆘 ESCALAÇÃO EXAURIDA — Atente #1234

Paciente: Maria da Silva Santos (Dona Maria)
Unidade: SPA Vida Plena — Ala B · Quarto 5
Evento #0011 · Classificação: CRÍTICO (escalado de urgente por padrão)
Aberto: há 22min (iniciado pelo cuidador Lúcia)

HISTÓRICO TENTATIVAS (todas sem resposta):
  ✗ Central (sent há 22min, no_answer)
  ✗ Enfermagem plantão (sent há 22min, no_answer)
  ✗ Dra. Ana (sent há 21min, no_answer)
  ✗ Filha · nível 1 (sent há 17min, no_answer + voice)
  ✗ Neto · nível 2 (sent há 12min, no_answer + voice)
  ✗ Sobrinho · nível 3 (sent há 7min, no_answer)

RESUMO CLÍNICO:
Queda com possível trauma (bateu a cabeça), paciente consciente mas confusa,
PA 145/95, SpO₂ 94%. Anticoagulante (Xarelto 20mg) em uso — risco de
sangramento intracraniano.

PADRÃO HISTÓRICO: 3ª queda em 15 dias (histórico semantico detectado).

AÇÃO SUGERIDA: acionar SAMU + tentar contato alternativo família.

Ver detalhes: https://care.connectaia.com.br/eventos/{event_id}
```

### Tratamento especial da resposta Atente

Quando operador Atente responde, o sistema marca evento como `resolved` com closed_reason específico:

- `"cuidado_iniciado"` — Atente acionou equipe do SPA
- `"encaminhado_hospital"` — Atente chamou SAMU/ambulância
- `"contato_familia_atente"` — Atente conseguiu contato com família por outro canal
- `"falso_alarme"` — sem intercorrência real
- Operador pode inserir notas livres

Essas notas são sincronizadas como `care-note` no TotalCare (ADR-019) marcando **"source: atente-escalation"** pra auditoria cruzada.

### Positive Consequences

- **Zero risco algorítmico de emergência** — IA não decide quando acionar SAMU; humano treinado decide
- **Compliance CFM + LGPD simplificada** — IA faz triagem (permitido amplamente), humano decide (exigido pelo CFM)
- **Reuso da operação existente** — Atente já tem processos, equipe, conhecimento de protocolos com famílias reais
- **Atente ganha potência** — nossa plataforma entrega casos priorizados + contextualizados (menos ruído, mais qualidade). Produto deles melhora.
- **Comercialmente forte pra demo**: Murilo entende que **Tecnosenior (hardware) + ConnectaIACare (IA) + Atente (operação) = ecossistema integrado** que a gente controla verticalmente
- **Futuro parcerias**: outros SPAs contratam ConnectaIACare sabendo que escalação termina em central humana profissional

### Negative Consequences

- **Dependência operacional da Atente** — se Atente estiver sobrecarregada, eventos ficam na fila
- **Horário**: Atente é 24/7, mas tem horários de pico (manhã/noite). Pode precisar SLA interno entre ConnectaIACare e Atente
- **Escala**: quando crescer pra 10+ SPAs, Atente precisa escalar equipe proporcionalmente
- **Custos**: operador humano custa mais que IA — modelo de precificação do produto final tem que prever isso (ex: ConnectaIACare + Atente bundle)

## Pros and Cons of the Options

### Option A — Expirar silencioso ❌

- ✅ Simples, zero dependência
- ❌ Evento crítico pode ser "perdido" sem intervenção humana — risco clínico real
- ❌ LGPD: ausência de follow-up pode ser questionada

### Option B — SAMU automático (descartado) ❌

- ✅ Escalação definitiva
- ❌ API SAMU inexistente, ligação automatizada via bot não é aceita legalmente
- ❌ Responsabilidade algorítmica alta
- ❌ Falsos positivos podem entupir SAMU (má pra reputação da plataforma)

### Option C — Atente fallback ✅ Chosen

- ✅ Usa operação humana existente
- ✅ Compliance limpa
- ✅ Comercialmente forte
- ❌ Depende de Atente ter operador disponível

### Option D — Atente primeiro nível ❌

- ✅ Tudo passa por humano
- ❌ Subaproveita IA (triagem automática é diferencial-chave)
- ❌ Não escala (operador vira gargalo)
- ❌ Aumenta ruído pra Atente (eventos rotina chegam junto)

## Implementation

### Técnico

1. **Alterar `tenant_config`**: adicionar campos `atente_central_phone`, `atente_central_name`, `atente_escalation_priority`
2. **Atualizar `escalation_service.py`**:
   - Role novo `atente` em `_resolve_contact`
   - Template de mensagem técnica em `_build_whatsapp_message`
   - Flag `is_final_fallback` no role — quando Atente responde, transiciona evento pra `resolved`
3. **Atualizar `escalation_policy` no YAML** — incluir `atente` no fim de todas as policies urgent/critical
4. **Dashboard**: marcar eventos escalados pra Atente com badge distinto ("fallback humano ativo")
5. **Audit trail**: registrar resposta de Atente como `closed_by = 'atente_operator'`

### Operacional

- Provisionar número de WhatsApp dedicado pra Atente receber escalações da ConnectaIACare (evitar mistura com outros canais deles)
- Definir SLA interno: Atente responde escalação crítica em <2min, urgente em <5min
- Treinar operadores Atente no dashboard ConnectaIACare (eles abrem evento pra ver contexto)

## When to Revisit

- Se Atente reclamar de volume excessivo → ajustar `escalation_level3_wait_min` pra dar mais tempo antes de chegar neles
- Se Atente não conseguir atender SLA → considerar Option A de fato (expirar) + dashboard destacar "escalação exaurida"
- Se regulação ANS 465/2021 evoluir e permitir acionamento SAMU automático auditado → revisitar Option B
- Se expandir pra 5+ tenants → criar pool de operadores Atente por tenant ou por região

## Links

- [escalation_service.py](../../backend/src/services/escalation_service.py)
- [care_event_service.py](../../backend/src/services/care_event_service.py)
- [ADR-020 Escalação WhatsApp + Sofia Voice](020-escalacao-hierarquica-evolution-sofia.md)
- [Atente — atente.com.br](https://atente.com.br)
