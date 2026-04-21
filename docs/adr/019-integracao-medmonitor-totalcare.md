# ADR-019: Integração MedMonitor (TotalCare) — ConnectaIACare como plataforma principal

- **Date**: 2026-04-20
- **Status**: Accepted
- **Deciders**: Alexandre (ConnectaIA), Murilo (Tecnosenior), Matheus Campello (dev TotalCare)
- **Tags**: integration, tecnosenior, api, sync, positioning

## Context and Problem Statement

O cliente de lançamento (Tecnosenior) já opera o TotalCare — sistema da Contactto.care que gerencia dispositivos (Vidafone, GPS), cadastro de assistidos, cuidadores e anotações de cuidado (`care-notes`). É um sistema **estático e difícil de operar** (relato do próprio time), mas é onde está **a base de assistidos reais, os dispositivos de monitoramento e a base de cuidadores profissionais**.

A visão estratégica articulada pelo Murilo (2026-04-20, 18h) é:

> *"A nossa plataforma precisa ser a principal. A médio prazo, a plataforma deles vai ficar como backend dos dispositivos e leitores de sinais — o cérebro e a operação ficam no ConnectaIACare."*

A Tecnosenior nos forneceu acesso à **"Agent API"** do TotalCare (documento `Documentação Agente de API.pdf`, 2026-04-20):
- URL base: `https://<tenant>.contactto.care/agent/` (nosso tenant: `totalcare-vidafone`)
- Auth: `Authorization: Api-Key <plaintext-key>`
- Leitura: `/patients/`, `/caretakers/`, `/members/`, `/care-notes/`
- Escrita: `POST /care-notes/` (única operação de escrita)

Precisamos decidir **como integrar** — e o mais importante: **em que sentido os dados fluem**.

## Decision Drivers

- **Visão estratégica Murilo**: ConnectaIACare = plataforma principal, TotalCare = camada de dispositivos
- **Source of truth de cadastros**: TotalCare é onde o vínculo legal/comercial está (Vidafone ativo, contrato com a família)
- **Source of truth de eventos clínicos**: ConnectaIACare precisa ser (porque é onde a IA analisa, a escalação executa, o dashboard vive)
- **Legado não-invasivo**: não podemos exigir que Tecnosenior reescreva nada — nossa integração precisa ser append-only
- **Compliance (LGPD Art. 11)**: dado sensível de saúde não pode ser duplicado sem DPIA clara — mirror local tem que ter justificativa técnica
- **Resiliência**: API externa pode cair (como caiu temporariamente em 2026-04-20 devido a endpoint errado) — plataforma não pode ficar offline
- **Custos de API**: rate limit não declarado; uso moderado (sync inicial + create on close)

## Considered Options

- **Option A**: Proxy/pass-through — nosso backend sempre consulta o TotalCare em tempo real
- **Option B**: Mirror completo bidirecional com sync contínuo
- **Option C**: Mirror de leitura + append-only de escrita (escolhida)
- **Option D**: Mirror completo, mas TotalCare continua como source of truth único

## Decision Outcome

Chosen option: **Option C — Mirror de leitura + write-through append-only**.

### Arquitetura de fluxo

```
                ┌─────────────────────────────────────────────────┐
                │                   ConnectaIACare                │
                │  (source of truth: eventos clínicos + IA)      │
                │                                                 │
                │  aia_health_patients  (espelho + dados próprios)│
                │  aia_health_caregivers (espelho + biometria)    │
                │  aia_health_care_events                         │
                │  aia_health_escalation_log                      │
                └────┬────────────────────────┬───────────────────┘
                     │                        │
           sync inicial                  write-through
           + on-demand                   (ao fechar evento)
                     ▼                        ▲
                     ▼                        │
┌─────────────────────────────────────────────┴───────────────┐
│                    TotalCare (Contactto.care)               │
│  (source of truth: cadastro, dispositivos)                  │
│                                                              │
│  patients, caretakers, members, care-notes                  │
└──────────────────────────────────────────────────────────────┘
```

### Leitura — Mirror local com refresh sob demanda

1. **Sync inicial** (sem bloqueio): script `sync_from_medmonitor.py` popula `aia_health_patients` e `aia_health_caregivers` com `external_id = TotalCare.id`. Mantém `metadata.source = 'medmonitor'` + `has_vidafone`, `has_gps_location`, `cpf_or_cnpj`.

2. **Fallback on-demand**: se durante um relato o LLM menciona paciente que não está no mirror local, `patient_service.best_match` retorna `None` → `pipeline._resolve_patient` faz `medmonitor.list_patients(search=...)` e **espelha inline** o resultado antes de abrir o evento. Assim, pacientes adicionados ao TotalCare depois do último sync são capturados na primeira menção.

3. **Campos espelhados**: `id`, `full_name`, `nickname`, `birth_date`, `gender`, `photo_url`, + `metadata` (cpf, rg, phone, has_vidafone, has_gps).

4. **Campos não espelhados** (ficam só no TotalCare): contratos, faturamento, config de dispositivo, consentimentos originais. Isso reduz superfície LGPD.

### Escrita — Write-through append-only (ao fechar evento)

Único ponto de escrita: `POST /api/events/:id/close` (ADR-018). Ao encerrar:

```python
mm.create_care_note(
    caretaker_id=<id TotalCare>,
    patient_id=<external_id do paciente>,
    content=f"Evento #0011 · classificação URGENT\n"
            f"Resumo: {event.summary}\n"
            f"Desfecho: cuidado_iniciado\n"
            f"Observações: {closure_notes}\n"
            f"Raciocínio: {event.reasoning}",
    content_resume=<≤500 chars>,
    occurred_at=<ISO 8601>,
)
```

TotalCare recebe como `source: "AGENT"` (forçado pelo servidor) e aparece na interface interna deles marcado como "da ConnectaIACare".

### Resiliência — Graceful degradation

`medmonitor_client.py` implementa:

- **Try/catch em todas as chamadas**: falha de rede/auth retorna `None` ou `[]` ao invés de levantar exceção
- **Log warning + seguir**: pipeline continua funcionando com dados locais
- **Feature flag por tenant**: `features.medmonitor_integration` desliga integração sem redeploy
- **Sync de care-note é best-effort**: se create_care_note falhar ao fechar evento, registramos no log mas o evento fica fechado localmente (não bloqueia operador). Retry pode ser adicionado via outbox pattern futuro.

### Matching de identidade (phone → caretaker)

Quando chega webhook WhatsApp de `55196161700`:

1. Busca local `aia_health_caregivers WHERE phone = normalize('55196161700')`
2. Se achou, usa biometria 1:1 para verificar
3. Se não achou, chama `mm.find_caretaker_by_phone(phone)` → busca por `+55...` normalizado
4. Se achou no TotalCare mas não localmente, espelha + associa
5. Fallback: `mm.find_member_by_phone()` (admin/staff que pode ser cuidador ocasional via `caretaker_id`)

Phone é a chave de ponte entre os dois sistemas — não temos SSO.

### Positive Consequences

- **Plataforma principal honesta**: pipeline + IA + dashboard rodam 100% com dados locais — nenhuma chamada TotalCare no caminho crítico
- **TotalCare fica leve**: só recebe 1 POST por evento encerrado (∼dezenas/dia por tenant) — zero carga de leitura
- **Dados ficam sincronizados automaticamente**: cada care-note aparece no sistema oficial da Tecnosenior sem intervenção manual
- **Visibilidade para Tecnosenior**: Matheus/Murilo veem na interface deles tudo que nossa plataforma analisou — reforça confiança
- **Migração futura fácil**: quando TotalCare expor dispositivos/sinais via API, basta adicionar métodos ao `medmonitor_client` sem refatorar resto
- **Dev-friendly**: client com `httpx` + normalização de phone + graceful degradation = plugar outro provedor (SulAmérica, Hapvida, etc) é trocar o URL base

### Negative Consequences

- **Dado duplicado**: nome, foto, birthdate ficam em 2 lugares. Mitigação: sync on-demand + refresh periódico (a implementar) mantém consistência eventual.
- **Split-brain possível**: se TotalCare atualizar nome de paciente depois do sync, nossa cópia fica desatualizada até próximo sync. Aceitável pra dados que mudam pouco; mitigação futura: webhook TotalCare → nosso refresh.
- **Dependência forte de phone como chave**: se cuidador mudar de número sem atualizar TotalCare, biometria 1:1 falha na primeira interação. Mitigação: fallback 1:N via embeddings de voz (ADR-005).
- **API key do TotalCare é por organização (plaintext-key)**: perda da key exige rotação manual pela Tecnosenior. Mitigação: armazenar em `.env` (chmod 600) + nunca commitar.

## Pros and Cons of the Options

### Option A — Proxy/pass-through ❌

- ✅ Sem duplicação de dados
- ❌ Toda operação depende da API externa (latência, uptime)
- ❌ Rate limit imposto pelo TotalCare afeta nossa operação
- ❌ Impossível funcionar offline

### Option B — Mirror bidirecional completo ❌

- ✅ Dados idênticos nos dois lados
- ❌ Conflitos de escrita exigem resolução (último escrita ganha? merge?)
- ❌ Escrita em `patients` do TotalCare via API não está exposta
- ❌ Compliance/DPIA complexa

### Option C — Mirror leitura + write-through append-only ✅ Chosen

- ✅ ConnectaIACare é plataforma principal
- ✅ TotalCare recebe append-only auditável
- ✅ Resiliente a falhas de rede
- ✅ Alinhado com visão estratégica
- ❌ Dados duplicados (aceitável — dados pessoais com TTL longo de mudança)

### Option D — TotalCare source of truth único ❌

- ✅ Zero duplicação
- ❌ Contradiz visão estratégica Murilo
- ❌ Plataforma principal sem autonomia

## Implementation

### Credenciais em produção

`.env` na Hostinger:
```
MEDMONITOR_API_URL=https://totalcare-vidafone.contactto.care/agent
MEDMONITOR_API_KEY=<plaintext-key fornecida por Tecnosenior>
```

### Sincronização inicial realizada (2026-04-20)

- **37 pacientes** espelhados (TotalCare ids 1-148 da organização Tecnosenior)
- **8 cuidadores** espelhados (Matheus, Murilo, Cleuza, Emmilyn, Vilson, Martim, Marlene, Teste Assistente)
- Script: `/tmp/sync_from_medmonitor.py` — executado via `docker exec`

### Next sync triggers (pós-MVP)

- [ ] Refresh periódico (6h) via cron no scheduler
- [ ] Webhook TotalCare (se disponibilizarem) para invalidação pontual
- [ ] Reconciliação manual via endpoint admin

## When to Revisit

- Se TotalCare expuser API de dispositivos (Vidafone, GPS) → expandir integração pra puxar sinais
- Se rate limit começar a morder → adicionar cache local com TTL
- Se houver mais de 1 tenant → migrar credenciais pra `aia_health_tenant_config` com criptografia
- Se a Tecnosenior quiser integração com outra fonte (Hapvida, etc) → abstrair `MedMonitorClient` como interface

## Links

- [medmonitor_client.py](../../backend/src/services/medmonitor_client.py)
- [Documentação Agente de API (PDF)](../Documentação%20Agente%20de%20API.pdf)
- [sync_from_medmonitor.py](../../scripts/sync_from_medmonitor.py) *(a adicionar)*
- [ADR-014 Integração MedMonitor sinais vitais](014-integracao-medmonitor-sinais-vitais.md)
- [ADR-018 Care Events (integração no close)](018-care-events-com-ciclo-de-vida.md)
