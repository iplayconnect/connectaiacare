# Panel LLM — Respostas brutas (pré-consolidação)

**Estudo de origem**: `docs/estudo_classificacao_inputs_cuidadores.md`
**Data**: 2026-04-28

Cada LLM respondeu sem ver os outros. Consolidação comparativa em
documento separado depois das 3 chegadas.

---

## 1. Gemini

> Recebido em 2026-04-28.

### 1.1 Respostas Q1-Q12

| Q | Recomendação | Risco | Métrica |
|---|--------------|-------|---------|
| Q1 Granularidade | 12 classes no backend, **6 macro na UI** do gestor | Fragmentação dificulta triagem | % uso equilibrado das classes |
| Q2 Multi-label | Multi-label JSON sem split de áudio (contexto ajuda) | Confusão de entidades em áudio longo | Taxa acerto multi-tópico |
| Q3 Extração | Opção A (inline) — reduz latência+custo | Prompt complexo "estourar" modelo menor | Latência E2E < 5s |
| Q4 Confirmação | **Híbrida** — ativa só em crítico ou confidence<0.7 | Fadiga de notificação | % confirmações ignoradas |
| Q5 Gírias | Few-shot com dicionário "médico-cuidador" | Regionalismos novos não cobertos | Taxa "Outros" por região |
| Q6 Onboarding | Cartilha física no posto + aprendizagem orgânica | Cuidador sentir vigilância | Dias até 1º input |
| Q7 Paralinguagem | **Ignorar inicialmente** | Perder pânico sem palavra-chave | Falsos negativos socorro |
| Q8 Multi-tópico em áudio | **Opção B** — care_events linkados ao parent_id | Poluição visual na timeline | Facilidade auditoria |
| Q9 Aferições rotineiras | Push proativo só pra métricas obrigatórias | Virar "robô de cobrança" | % conversão push em dado |
| Q10 Trust score | **Sim, por classe** (Profissional > Família em vitais) | Viés contra família | Correlação score × validação enfermeira |
| Q11 Casos sociais/abuso | Categoria "Ocorrência Social/Administrativa" + alerta silencioso ao gestor | Acusações falsas | Tempo resposta gestor |
| Q12 KPI master | **Taxa de Escalação Relevante** — % alertas que geraram ação clínica real | Otimizar para "não incomodar" | Eventos adversos não detectados |

### 1.2 Crítica à taxonomia

**Classes que faltaram (Seção 2):**
1. **Cuidados paliativos / óbito** — manejo fim de vida, comunicação de óbito (protocolos legais e emocionais distintos)
2. **Segurança do ambiente** — chão molhado, cama quebrada, luz queimada (impacta risco de queda)
3. **Saúde mental do cuidador / burnout** — "não aguento mais esse plantão", crítico em lares carentes pra gestão de RH

**Fusão sugerida:**
- Higiene (8) + Pele/Lesões (7) → "Integridade Cutânea e Higiene"

### 1.3 Avaliação da arquitetura (Seção 3)

- **Concorda fortemente** com regex fast-path para emergência ("decisão técnica mais correta do documento" — em 3G/4G instável não dá pra depender de LLM 70B pra decidir parada respiratória).
- **Concorda** com schema híbrido (hub + tabelas tipadas) — preserva contexto narrativo (áudio) + ganha poder analítico (números).

### 1.4 Prompt zero-shot proposto

```
### Role
Você é um classificador clínico geriátrico para Instituições de
Longa Permanência (ILPI).

### Task
Classifique a TRANSCRIÇÃO do cuidador em categorias estruturadas.

### Classes
[Aferição, Evento_Agudo, Medicação, Alimentação, Eliminação,
Comportamental, Pele, Higiene, Estoque, Solicitação, Equipe, Social,
EMERGENCIA]

### Regras
1. Se houver risco de morte imediata, use severidade: "CRITICAL" e
   classe: "EMERGENCIA".
2. Extraia valores numéricos de sinais vitais para os campos
   adequados.
3. Identifique se o cuidador precisa de uma resposta
   (needs_clarification).

### Exemplos (Few-shot)
Input: "Seu João tá com a pressão 15 por 9 e recusou o café."
Output: {"primary_class":"Aferição",
  "labels":["Aferição:PA","Alimentação:Recusa"],
  "extracted":{"pa_sistolica":150,"pa_diastolica":90,
    "refeicao":"cafe_da_manha","status":"recusou"},
  "severity":"routine","confidence":0.95,"needs_clarification":false}

Input: "A dona Maria caiu agora, tá com um corte feio na cabeça e
não tá falando coisa com coisa."
Output: {"primary_class":"EMERGENCIA",
  "labels":["Evento_Agudo:Queda","Pele:Ferida","Comportamental:Confusão"],
  "extracted":{"tipo_evento":"queda","lesao":"corte_cabeca",
    "consciencia":"alterada"},
  "severity":"CRITICAL","confidence":0.98,
  "needs_clarification":false}

### Transcrição do Cuidador
"{{transcription}}"
```

### 1.5 Furos no plano (3 itens)

1. **Ambiguidade temporal** — "agora há pouco" pode ser 10min ou 4h
   atrás. Sistema captura `sent_at` da mensagem WhatsApp, mas prompt
   precisa extrair referências temporais relativas pra não poluir
   gráfico de tendências.
2. **Múltiplos pacientes no mesmo áudio** — "A Dona Maria tomou o
   remédio, mas o Seu José tá muito agitado". Arquitetura atual
   assume 1 idoso por mensagem. Precisa camada **NER** antes da
   classificação pra separar contextos por patient_id.
3. **Alucinação de unidades de medida** — cuidadores omitem unidades
   ("glicemia 110", "PA 12 por 8"). Risco de LLM confundir 12/8 com
   120/80 ou ler "38" como idade em vez de febre. Precisa
   **post-processor determinístico Python** que valide range
   biológico antes de salvar nas tabelas tipadas.

### 1.6 Case real citado

- **Sensi.ai** — processamento de áudio ambiente (não WhatsApp, mas
  princípio de classificação idêntico) pra detectar quedas e mudanças
  comportamentais em lares de idosos, focando em reduzir fadiga de
  alerta das enfermeiras.

### 1.7 Notas

- Gemini incluiu referência a "R$ 8.500,00 discutidos antes" —
  parece **memória de conversa anterior do usuário**, não está no
  documento. Ignorar pra fins de consolidação.

---

## 2. GPT

> Recebido em 2026-04-28. **NÃO respondeu Q1-Q12 no formato pedido**.
> Trouxe um framework próprio de arquitetura em 13 seções —
> complementar mas não diretamente comparável. Resumo abaixo.

### 2.1 Framing (diferente do Gemini)

GPT redefiniu o problema: "Você NÃO quer classificar emoção ou
intenção. Você quer classificar inputs em **EVENTOS CLÍNICOS E
OPERACIONAIS PADRONIZADOS**". Sugere ver o sistema como
**interpretação clínica operacional baseada em sinais imperfeitos**,
não como classificador de texto.

### 2.2 Pipeline de 7 camadas proposto

```
INPUT (voz/texto/sensor/vídeo)
   ↓
NORMALIZAÇÃO              ← formato comum independente da fonte
   ↓
EXTRAÇÃO DE FEATURES      ← keywords clínicas + intensidade + negação
   ↓
CLASSIFICAÇÃO BASE        ← determinística + ML leve (resolve 70%)
   ↓
ENRIQUECIMENTO CONTEXTUAL ← histórico paciente + hora + baseline
   ↓
CLASSIFICAÇÃO FINAL       ← LLM SÓ em ambíguos / multi-sinal
   ↓
EVENTO ESTRUTURADO        ← saída padronizada
```

### 2.3 Taxonomia proposta (compacta)

GPT defende **começar com 25-30 eventos**, não 12 classes + N
subcategorias. Top-level:

| Grupo | Exemplos |
|-------|----------|
| Cognitivo | confusão, desorientação, esquecimento agudo |
| Físico | queda, mobilidade reduzida, dor |
| Comportamental | recusa alimentar, apatia, agitação |
| Clínico | medicação não tomada, sintomas relatados |
| Crítico | risco de queda, alteração súbita |

5 grupos vs nossas 12 classes. Bem mais enxuto.

### 2.4 Schema de saída (interessante)

```json
{
  "event_type": "cognitive_change",
  "subcategory": "confusion",
  "severity": "medium",
  "confidence": 0.78,
  "risk_score": 62,
  "requires_attention": true,
  "explanation": "Mudança recente + relato do cuidador +
                  redução de interação"
}
```

Campo `explanation` é diferencial — não está no nosso modelo hoje.

### 2.5 Insights únicos vs Gemini

1. **Multimodalidade explícita** — GPT pensa além do WhatsApp:
   sensor wearable, câmera, log de sistema, áudio paciente. Vale
   ter normalização desde o início.
2. **Eventos compostos** — combinação de signals: "baixa
   alimentação + apatia → risco maior". Multi-label conjugado.
3. **Baseline por paciente** — "Confusão + paciente com demência →
   baixa severidade. Confusão + paciente lúcido → alta severidade".
   **Nós já temos isso** via `aia_health_patient_baselines`
   (migration 041) — bom alinhamento.
4. **Roadmap em 3 fases**:
   - Fase 1: 25 eventos + regras simples + score básico
   - Fase 2: contexto + histórico + eventos compostos
   - Fase 3: LLM para exceções + ajuste fino

### 2.6 Armadilhas clássicas que GPT alerta

- Tentar resolver tudo com LLM → caro, inconsistente
- Taxonomia gigante → impossível manter
- Ignorar contexto do paciente → erro clínico
- Não tratar ambiguidade → sistema vira ruído

### 2.7 O que faltou no GPT vs Gemini

- ❌ Não respondeu Q1-Q12 no formato exigido (recomendação + risco
  + métrica + alternativa)
- ❌ Não citou case real (Gemini citou Sensi.ai)
- ❌ Não escreveu prompt zero-shot com few-shot PT-BR
- ❌ Não apontou furos concretos no plano (Gemini apontou 3:
  ambiguidade temporal, multi-paciente em mesmo áudio, alucinação
  de unidades)

### 2.8 O que GPT acertou que Gemini não cobriu

- ✅ Pipeline de 7 camadas explícito (Gemini foi mais alto-nível)
- ✅ Camada de **normalização** antes de classificação (multimodal)
- ✅ Conceito de **eventos compostos** (signals conjugados)
- ✅ Campo `explanation` no output
- ✅ Phasing concreto (25 → contexto → LLM)
- ✅ Defesa de **regras determinísticas resolvem 70%** mais
  enfática que Gemini (que só falou de regex fast-path emergência)

---

## 3. Grok

> Recebido em 2026-04-28. Resposta em 2 fases:
> Fase 1 — análise do doc + taxonomia + pipeline + prompt.
> Fase 2 — conversa interativa que foi muito mais fundo em
> identificação de persona, fallback humano-usuário e celular
> compartilhado/pessoal por plantão.

### 3.1 Fase 1 — resposta ao doc

**Pontos fortes que Grok elogiou no estudo:**
- Taxonomia realista, abordagem híbrida (regex+LLM+confirmação) é
  a correta pra latência <8s e custo <R$0,02
- Schema híbrido (hub + tabelas tipadas) é excelente

**Pontos fracos / lacunas:**
- 12 classes top-level é alto (aumenta custo + risco de confusão)
- Falta fallback de baixa confiança robusto
- Falta priorização clara de quais classes precisam extração
  estruturada imediata vs só tag
- Paralinguística (tom de voz) ainda subestimada — em áudio de
  cuidador estressado isso é ouro

**Taxonomia revisada (8 classes vs nossas 12):**

| # | Classe | Subclasses | Prio extração |
|---|--------|-----------|---------------|
| 1 | Aferições / Sinais Vitais | PA, FC, SatO₂, glicemia, temp, dor | **Alta** |
| 2 | Eventos Clínicos Agudos | Queda, dispneia, dor torácica, sangramento | **Crítica (bypass)** |
| 3 | Medicação | Tomada, recusa, reação adversa, falta | **Alta** |
| 4 | Alimentação / Hidratação | Aceitação, recusa, disfagia | Média |
| 5 | Eliminações | Diurese, evacuação, incontinência | **Alta** |
| 6 | Comportamental / Cognitivo | Agitação, delirium, choro, apatia | Média-Alta |
| 7 | Cuidados Físicos / Pele | Banho, curativo, úlcera, ferida, edema | Média |
| 8 | Operacional / Logístico | Estoque, solicitações, plantão, visitas | Baixa-Média |

> Emergência continua como **flag transversal**, não como classe.

Fusões: nossas Pele(7) + Higiene(8) → "Cuidados Físicos". Nossas
Estoque(9) + Solicitações(10) + Equipe(11) + Eventos sociais(12) →
"Operacional / Logístico".

**Pipeline em 4 etapas (vs 7 do GPT):**

1. Fast-path Emergency + Regex (0.2-0.4s)
2. Classificador top-level multi-label (1.5-3s) — Haiku/Flash/Grok-fast
3. Extração estruturada por classe (paralela) — só pra confidence>0.65
4. Confirmação inteligente — só quando confidence<0.6 ou ambíguo

**Custo projetado: R$ 0,008-0,015/input** (mais conservador que
nossa meta de <R$0,02).

**Prompt zero-shot:** estrutura JSON com `{classes[], severidade,
extracted, confidence, needs_clarification, clarification_question}`.
Recomenda 3-4 few-shots reais.

### 3.2 Fase 2 — Deep dive interativo (foi onde Grok brilhou)

A conversa derivou pra problemas práticos de identificação de
quem está falando + fluxo de fallback. Insights cumulativos:

#### Insight A — Fallback híbrido humano + usuário

Quando `confidence < 75%`:
1. Sofia para e pergunta ao **próprio usuário** primeiro (rápido,
   barato): *"Só pra confirmar: você está sentindo dor no peito?
   Responda só sim ou não."*
2. Se usuário não responde claramente em 8s ou responde confuso →
   escalate pro cuidador com **transcrição + interpretação + contexto**.
3. Cuidador recebe via WhatsApp:
   - Que o usuário falou
   - O que Sofia entendeu (% de confiança)
   - Botões rápidos: confirmar X / confirmar Y / outro / chamar 192

> Diferencial: pergunta de confirmação NÃO é "foi isso?" (idoso
> pode dizer sim por agradar) — é **opção fechada explícita**.

#### Insight B — 3 personas com comportamentos distintos

| Persona | Linguagem | Foco |
|---------|-----------|------|
| Paciente | Simples, calma, lenta | Conforto + segurança, pergunta "sim/não" |
| Cuidador | Técnica, direta, ágil | Relato clínico estruturado |
| Familiar | Acolhedora, empática | Atualização emocional, tranquilizar |

Cada persona = system prompt distinto. Persona é **travada na
conversa** após identificação.

#### Insight C — Biometria + persona ID (encaixa direto no que já fizemos)

Combinação:
- Biometria roda em background nos primeiros 3s do áudio
- Confiança >85% → Sofia abre conversa já sabendo quem é
- Confiança <70% → pergunta "paciente, cuidador ou familiar?"
- **Conflito** (biometria diz X, pessoa diz Y) → Sofia pergunta
  pra desambiguar

#### Insight D — TENANT + PLANTÃO reduz escopo da biometria 1:N

A grande sacada do Alexandre, validada pelo Grok:

- Tenant tem ~10-15 cuidadores cadastrados
- 1:N contra todos = impreciso
- **Mas se sabemos plantão atual** (manhã/tarde/noite), o pool cai
  pra 3-4 cuidadores → 1:N pequeno → muito mais preciso
- Resolve naturalmente o problema de **troca de plantão**:
  cuidador da manhã cobrindo tarde → biometria não acha em pool
  da tarde → fallback pergunta "você é Carla, Joana ou Maria?"
  → pessoa responde "Sou Ana, cobrindo a tarde" → registra
  override temporário

#### Insight E — Celular compartilhado vs pessoal

Cenário REAL que nem Gemini nem GPT tocaram:

**Cenário 1**: Lar oferece **celular por plantão** (compartilhado).
Vários cuidadores usam o mesmo número ao longo do dia.
→ Biometria fica quase inútil (vozes diferentes no mesmo número).

**Cenário 2**: Cuidador usa **WhatsApp pessoal**.
→ Biometria funciona normalmente.

**Solução proposta**: cadastrar no sistema cada número como
`shared` ou `personal`:
- Compartilhado → SEMPRE pergunta "com quem estou falando?"
  + "sobre qual paciente?"
- Pessoal → biometria normalmente, sem pergunta

**Implicação direta na nossa arquitetura** — falta um campo
`phone_type` por (tenant, número) no nosso modelo. Hoje
assumimos sempre pessoal.

### 3.3 Avaliação geral do Grok

- ✅ Q1-Q12: respondeu parcialmente (não no formato estruturado mas
  cobriu boa parte das questões)
- ✅ Prompt zero-shot funcional com estrutura clara
- ✅ Pipeline em 4 etapas com custo projetado concreto
- ✅ **Foi MUITO mais fundo na fase 2** — flow completo de persona +
  biometria + fallback que ninguém mais tocou
- ✅ Cobriu cenário de celular compartilhado/pessoal (lacuna real)
- ❌ Não citou case real de mercado (Gemini citou Sensi.ai)
- ❌ Não apontou furos no plano original com a mesma profundidade
  que Gemini (mas a fase 2 é mais valiosa que isso)
- ⚠️ Levemente repetitivo na fase 2 (mensagens cortadas, erros de
  digitação que ficaram na transcrição)

