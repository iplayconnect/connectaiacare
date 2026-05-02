# Análise · Port do ConversationStateManager (CSM) da ConnectaIA

> Investigação técnica do que portar da ConnectaIA pra resolver o
> gap de fluxo conversacional da Sofia em ConnectaIACare.
> Disparado por feedback do Alexandre 2026-05-02 após teste real
> com Douglas (51994267222) onde Sofia repetiu perguntas várias
> vezes em conversa longa.

## Sintoma observado

Em conversa real (logs 22:45-23:04 UTC):

| Turn | User | Sofia |
|---|---|---|
| 22:46 | "Douglas" | "Prazer Douglas! Você representa instituição ou cuida de alguém?" |
| 22:46 | "Para os meus pais" | "Cuidar dos pais... O que te preocupa?" |
| 22:47 | "Segurança e medicamentos" | "...Quantos medicamentos toma?" |
| 22:48 | "8 medicamentos" | "Moram sozinhos ou com alguém?" |
| 22:48 | "Moram sozinhos" | "Quantos anos eles têm?" |
| 22:49 | "90 e 91" | **"...Quantos idosos seus pais precisam de monitoramento?"** ❌ confuso |
| 23:01 | "Douglas da Silva" | "...você é filho? E qual a maior preocupação?" |
| 23:01 | "Sou filho" | "...qual sua preocupação?" |
| 23:01 | "Quedas" | **"...Quantos idosos você precisaria monitorar?"** ❌ JÁ TINHA RESPOSTA |
| 23:02 | "2" | **"Quantos idosos estão sob seus cuidados?"** ❌ REPETIU |
| 23:02 | "Dois" | "...trabalha em casa ou instituição?" ❌ JÁ TINHA |
| 23:03 | **"Já falei antes"** | "Desculpa! Vi que já conversamos. Lembra qual sua dúvida?" |

Sofia **lembrou** o nome (memória OK pós-fixes #81/#82/#83) mas
**repetiu perguntas**. Causa: contexto é texto bruto, sem
estrutura "pergunta X = resposta Y, não repetir".

## Análise da estrutura ConnectaIA

ConnectaIA tem 3.6k linhas de infra de fluxo conversacional madura:

| Arquivo | Linhas | Função |
|---|---|---|
| `conversation_state_manager.py` | 1592 | CSM completo: state machine + extraction + context injection |
| `humanizer.py` | 881 | Chunking + typing delays |
| `sofia_orchestrator.py` | 757 | Multi-agent orchestrator |
| `message_buffer.py` | 406 | Buffer (detecta digitação contínua, espera) |

### Arquitetura do CSM (resumo)

```
┌──────────────────────────────────────────────┐
│   ConversationState (single source of truth) │
├──────────────────────────────────────────────┤
│  LeadData       — dados cumulativos          │
│  interactions[] — pareadas pergunta+resposta │
│  FlowState      — stage + pending_question   │
└──────────────────────────────────────────────┘
              ▲                ▲
              │                │
   process_lead_message()   get_context_for_agent()
   (input pipeline)         (output pra prompt)
```

### Componentes-chave

#### 1. `LeadData` (cumulativo)
Dataclass com **todos os campos** que se quer coletar. Cada
campo `Optional[T]` — preenchido progressivamente. Tem
`dados_confirmados: list[str]` rastreando o que JÁ foi coletado.

#### 2. `Interaction` (pareada)
```python
@dataclass
class Interaction:
    bot_message: str          # "Qual seu nome?"
    bot_intent: str           # "nome" (QuestionIntent)
    lead_message: str         # "Douglas"
    extracted_data: dict      # {"nome": "Douglas"}
    extraction_confidence: float
    answered: bool
    data_saved: bool
```

#### 3. `FlowState` com `pending_question`
**Crítico**: estado guarda a pergunta que Sofia FEZ no turno
anterior:
```python
pending_question: Optional[str]
pending_question_intent: Optional[str]  # "employment_status"
pending_question_agent: Optional[str]
```

Quando user responde, CSM **associa resposta à pergunta pendente**
e extrai dado correto.

#### 4. `process_lead_message()` (pipeline)
```
1. Carrega state (Postgres)
2. Se pending_question existe:
   → extrai dado tipado pra esse intent específico
3. Extrai TUDO que conseguir da mensagem (regex + LLM)
4. Merge no LeadData (só campos não confirmados)
5. Cria Interaction (history)
6. Persiste
```

#### 5. `get_context_for_agent()` (injection)
Gera dict estruturado pro prompt:
```python
{
    "lead_data": {...},                # dados coletados
    "collected_fields": ["nome", "situacao_emprego"],
    "pending_fields": ["empresa", "salario"],
    "should_ask_name": False,           # ← flag de controle
    "should_ask_employment": False,     # ← flag de controle
    "has_name": True,
    "current_stage": "qualificacao",
    "pending_question": "Qual sua empresa?",
    "recent_history": [...últimas 5 interações...]
}
```

Prompt do agent recebe isso e tem instrução clara:
"Não pergunte X se `has_X=True`. Próxima pergunta lógica é Y
porque está em `pending_fields`."

## Adaptação pra ConnectaIACare

`LeadData` da ConnectaIA é vertical-trabalhista (advogado
demissão). Pra ConnectaIACare é vertical-care:

```python
@dataclass
class CareLeadData:
    # Identificação
    nome: Optional[str] = None
    primeiro_nome: Optional[str] = None
    telefone: Optional[str] = None
    email: Optional[str] = None
    cidade: Optional[str] = None

    # Relação com o(s) idoso(s)
    relacao: Optional[str] = None
        # "self" | "filho" | "neto" | "conjuge" | "cuidador_pro" |
        # "gestor_ilpi" | "medico" | "outro"

    # Beneficiários
    count_idosos: Optional[int] = None
    idades_idosos: List[int] = field(default_factory=list)
    moram_sozinhos: Optional[bool] = None
    moram_com_familia: Optional[bool] = None
    moram_em_ilpi: Optional[bool] = None

    # Dores e necessidades
    dores: Set[str] = field(default_factory=set)
        # {"quedas", "medicacao", "monitoramento_24h",
        #  "companhia", "demencia", "mobilidade", "alimentacao"}

    # Medicação
    count_medicamentos: Optional[int] = None
    tem_dificuldade_medicacao: Optional[bool] = None

    # Status comercial
    ja_cliente_concorrente: Optional[bool] = None
    quer_demo: Optional[bool] = None
    intent_b2c_b2b: Optional[str] = None

    # B2B-specific
    organizacao: Optional[str] = None
    cargo_b2b: Optional[str] = None
    count_residentes: Optional[int] = None  # se ILPI

    # Tracking
    dados_confirmados: List[str] = field(default_factory=list)
    dados_pendentes: List[str] = field(default_factory=list)
```

### `ConversationStage` (care-specific)

```
WARMUP            — saudação + Sofia se apresenta
IDENTIFICACAO     — nome + relação com idoso
QUALIFICACAO      — count idosos + idades + sit. moradia
APROFUNDAMENTO    — dores + dificuldades + contexto clínico-social
APRESENTACAO_VALOR — Sofia explica como pode ajudar (whitelist
                    de capabilities)
ENCAMINHAMENTO    — agendar demo OU encaminhar humano
                    OU explicar produto B2C
ENCERRAMENTO      — confirma próximos passos
```

### `QuestionIntent` (care-specific)

```python
NAME, RELACAO_IDOSO, COUNT_IDOSOS, IDADES, MORADIA,
DORES_PRINCIPAIS, COUNT_MEDS, MEDICACAO_DIFICULDADE,
JA_CLIENTE, QUER_DEMO, EMAIL, ORGANIZACAO_B2B,
CARGO_B2B, COUNT_RESIDENTES_ILPI, GENERIC
```

## Schema Postgres

Migration nova ~063:
```sql
CREATE TABLE aia_health_conversation_state (
    client_id TEXT PRIMARY KEY,  -- phone E.164 normalizado
    tenant_id TEXT NOT NULL,
    lead_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    flow_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    interactions JSONB NOT NULL DEFAULT '[]'::jsonb,  -- últimas 30
    contact_origin TEXT DEFAULT 'inbound',
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_activity TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ON aia_health_conversation_state (tenant_id, last_activity DESC);
```

## Whitelist de capabilities (problema #2)

Sofia inventou "monitoramento de batimentos cardíacos / saturação"
no teste real (22:49). Solução paralela ao CSM:

```sql
CREATE TABLE aia_health_platform_capabilities (
    id UUID PK,
    code TEXT UNIQUE,             -- 'monitor_quedas', 'med_alerts',
                                  --  'voice_calls_proativas', etc.
    label_user TEXT,              -- pra Sofia falar do user
    description TEXT,             -- detalhada
    category TEXT,                -- 'monitoramento'|'medicacao'|...
    public_facing BOOLEAN,        -- pode mencionar em comercial?
    confidence_required NUMERIC,
    audit_id_source UUID
);
```

Prompt do commercial agent recebe lista whitelist + regra:
> "Você SÓ PODE prometer estas features. Pra qualquer pergunta
> técnica fora desta lista, diga: 'vou passar pro time comercial
> te detalhar'. NUNCA invente capability."

## Plano de execução · Phase C v2

### Phase C v2.1 — CSM core (~3 dias)
- Migration 063 + `aia_health_conversation_state`
- `CareConversationState` + `CareLeadData` + `Interaction`
  + `CareFlowState` (dataclasses)
- Persistência com upsert idempotente
- Tests unit

### Phase C v2.2 — DataExtractor adaptado (~2 dias)
- Regex-based pra dados estruturados (nome, idade, count, email)
- LLM-based fallback (Haiku) pra ambiguidade
- Adaptado pra português brasileiro de cuidados ("meus pais",
  "minha mãe", "moram sozinhos", "8 remédios")
- Tests com casos do log Douglas (sanity)

### Phase C v2.3 — Integração no orchestrator (~2 dias)
- `super_sofia_orchestrator.process()`:
  1. Antes do agent: `csm.process_lead_message(phone, text)`
  2. `csm.get_context_for_agent("commercial")` → dict estruturado
  3. Inject no prompt do agent (substitui o `active_context_messages`
     bruto)
  4. Após agent response: detecta pergunta pendente,
     `csm.register_pending_question(intent)`
- Active_context (PR #81) continua mas vira **histórico bruto
  secundário** — CSM é o primário

### Phase C v2.4 — Whitelist capabilities (~1 dia)
- Migration `aia_health_platform_capabilities` + seed
- Service `capability_resolver.list_for_agent(agent_name)`
- System prompt commercial recebe lista + regra anti-invenção

### Phase C v2.5 — Re-test fresh (~0.5 dia)
- Limpeza Douglas
- Mesma conversa de 18 turnos do log
- Validar:
  - Nenhuma pergunta repetida
  - Sofia não inventa features
  - Lead capturado tem dados estruturados (CareLeadData → mapeia
    pra `aia_health_leads`)

**Total**: ~8.5 dias úteis. Mais profundo que Phase C v1 (que
fez tudo em ~2 dias).

## Riscos / cuidados

1. **Regex extraction frágil em PT-BR**: "8 remédios" vs "oito
   remédios" vs "uns 8 remédios" — DataExtractor BR precisa cobrir
   variações. Mitigação: combinar regex + LLM extractor com
   fallback.

2. **Race condition em conversas concorrentes**: usuário manda
   2 msgs em rápida sucessão, 2 workers picam stream → 2
   `process_lead_message` em paralelo. Mitigação: row-level lock
   (`SELECT ... FOR UPDATE`) por client_id durante o turn.

3. **Migration de leads existentes**: `aia_health_leads` (Phase A)
   não desaparece. CSM escreve em `conversation_state` (efêmero,
   detalhado) e propaga pra `aia_health_leads` (durável,
   sumarizado). Sync bidirectional.

4. **TTL conversation_state**: ConnectaIA não tem TTL — pessoa
   pode voltar 6 meses depois e Sofia "lembra". Bom pra B2B.
   Pra B2C clínica, considerar TTL 90d com archive.

5. **Custo extraction LLM**: cada msg dispara 1 call extra.
   Com 10k msgs/dia + Haiku ($0.80/M input) = ~$2/dia adicional.
   Aceitável.

## Componentes secundários (futuro, fora Phase C v2)

- **`humanizer.py`** (881 linhas): chunking + typing delays. ConnectaIACare
  já tem versão simplificada em `pipeline.py` legado. Phase D ou E.
- **`message_buffer.py`** (406 linhas): debounce de typing
  contínuo. Útil pra UX mas não-crítico. Phase E.
- **`objection_handler`**: pra commercial avançado. Útil quando
  Sofia comercial estiver lidando com lead que vai resistindo.
  Phase futura.

## Recomendação imediata

**Começar Phase C v2.1 + v2.4 hoje** (CSM core + whitelist
capabilities). Esses 2 resolvem os 2 sintomas críticos do teste:
- Sofia não repete perguntas (CSM)
- Sofia não inventa features (whitelist)

v2.2 (DataExtractor full) e v2.3 (integração total) podem ser
iteração seguinte se necessário — `aia_health_leads` já é o sink
final dos dados.

**Se Alexandre der GO**: começo agora Phase C v2.1, branch
`feat/super-sofia-phase-c-v2-csm`. Dimensiono 5-7 dias úteis com
commits incrementais.
