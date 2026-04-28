# Estudo — Classificação de Inputs de Cuidadores via WhatsApp

**Contexto**: documento estratégico para rodada de análise com 3 LLMs
externos (panel de revisão). Propõe taxonomia de categorias de input,
arquitetura de classificação multi-label e questões abertas para
debate. Resposta esperada de cada LLM: alternativas concretas,
furos no plano e propostas de melhoria.

**Caso de uso**: Sofia (assistente IA da plataforma) recebe relatos
de cuidadores via WhatsApp em **lares de idosos brasileiros** —
incluindo lares carentes onde cuidador tem letramento limitado e
pouco tempo. Áudio é o canal dominante; texto é minoritário.

---

## 1. O problema

### 1.1 Cenário real

- Cuidador de plantão noturno em ILPI (Instituição de Longa Permanência
  para Idosos) cuida simultaneamente de 6 a 12 idosos.
- Tempo médio para registrar uma intercorrência: **<60 segundos**.
- Letramento: muitas vezes incompleto. Erros de português frequentes.
- Aparelho: smartphone modesto, conexão 3G/4G instável.
- Canal preferido: **áudio do WhatsApp**, raramente foto, nunca
  formulário web.

### 1.2 Por que tudo num campo de texto livre é ruim

Hoje o relato vira `aia_health_reports.transcription` (texto cru) +
`event_tags` (array de palavras-chave clínicas como `queda`, `febre`,
`dispneia`). Funciona pra eventos agudos, mas falha em:

- **Aferições rotineiras** ("PA 140/85, FC 78, glicemia 110") —
  cuidador esperado lança em campo separado, mas grava áudio que
  vai pro mesmo campo dos eventos críticos.
- **Consumo / estoque** ("acabou a fralda do seu João") — não tem
  categoria, vira ruído clínico.
- **Eliminações** ("dona Maria evacuou 2 vezes hoje, fezes pastosas")
  — informação clínica importante, mas não dispara nenhum fluxo.
- **Comportamental** ("ela passou a tarde chorando") — atenção, mas
  não vermelho.
- **Solicitações** ("preciso de receita nova de losartana") — virá
  uma intercorrência clínica falsa.

Resultado: **enfermeira recebe enxurrada de alertas mal classificados**
e perde os críticos.

### 1.3 Premissas de design

1. Cuidador escreve/fala **livremente, em uma única mensagem**, sem
   menu prévio.
2. Sistema **classifica e roteia** automaticamente.
3. Mensagens podem ser **multi-tópico** ("o seu João caiu agora há
   pouco e a glicemia ficou 220, dei o remédio e ele recusou
   janta"). Tudo em 8 segundos de áudio.
4. Quando ambíguo, Sofia **pergunta de volta** em uma única
   mensagem curta — nunca em formulário multi-passo.
5. **Erros de português, gírias regionais, áudio com ruído** são a
   norma, não a exceção.

---

## 2. Universo de inputs em cuidados geriátricos

Mapa exaustivo do que cuidadores de ILPI relatam, organizado em 12
classes top-level. Cada classe tem subcategorias clínicas e exemplos
reais (linguagem coloquial brasileira).

### Classe 1 — Aferições / Sinais Vitais
Medições periódicas, na maioria não-críticas mas que alimentam
baseline.
- PA (sistólica/diastólica, com/sem postura)
- Frequência cardíaca
- SpO₂ (saturação)
- Temperatura axilar/timpânica
- Glicemia capilar (jejum/pós-prandial)
- Frequência respiratória
- Peso
- Dor (escala 0-10 ou descritiva)
- Estado de consciência (orientado, sonolento, agitado)

**Exemplo real**: "PA 14 por 9 do seu Pedro agora, FC 72."

### Classe 2 — Eventos Clínicos Agudos
Categoria já parcialmente coberta hoje. Geralmente vermelho/urgente.
- Queda (com/sem trauma, com/sem perda de consciência)
- Sangramento (epistaxe, gastrointestinal, ferida)
- Convulsão
- Dispneia / falta de ar
- Dor torácica
- Síncope
- Cianose
- Suspeita de AVC (face caída, fraqueza unilateral, fala alterada)
- Suspeita de IAM (dor torácica + sudorese + mal-estar)
- Engasgo / broncoaspiração
- Crise de epilepsia

**Exemplo real**: "dona Maria caiu na hora do banho, tá sangrando o
nariz, mas tá consciente."

### Classe 3 — Medicação
- Tomada confirmada (pode ser opt-in pela rotina)
- Recusa de tomada
- Vômito após dose (definir se redoso)
- Reação adversa suspeita (alergia, rash, prurido, edema)
- Falta no estoque
- Erro de dose (dose dupla, dose esquecida)
- Solicitação de nova receita

**Exemplo real**: "o seu Antonio jogou fora o remédio das 18h, não
tomou."

### Classe 4 — Alimentação / Hidratação
- Quantidade da refeição (½, ¼, recusou, ofereceu mais)
- Disfagia / engasgo durante refeição
- Aceitação de líquidos (volume diário)
- Recusa alimentar persistente
- Mudança de consistência da dieta (tritou, papa, líquida)
- Dieta enteral (sonda) — volume, tolerância

**Exemplo real**: "comeu metade do almoço, recusou a sopa, tomou só
1 copo de água."

### Classe 5 — Eliminações
- Diurese (volume, cor, número de fraldas)
- Evacuação (frequência, consistência Bristol 1-7)
- Constipação (>3 dias sem evacuar)
- Diarreia (frequência, com/sem sangue/muco)
- Incontinência urinária ou fecal
- Hematúria (sangue na urina)
- Retenção urinária

**Exemplo real**: "trocou 4 fraldas, urina escura. Não evacua há 3
dias."

### Classe 6 — Comportamental / Cognitivo
- Agitação / agressividade
- Confusão aguda / delirium
- Choro frequente / depressão
- Insônia / inversão sono-vigília
- Vagar (wandering)
- Apatia / mutismo
- Alucinações
- Recusa de cuidado (banho, medicação, alimentação)

**Exemplo real**: "passou a noite acordada, batendo na porta. Não
reconheceu o filho."

### Classe 7 — Pele / Lesões
- Úlcera de pressão (com estágio I-IV se cuidador souber)
- Ferida (corte, escoriação)
- Rash / eritema
- Equimose / hematoma
- Edema (localização, simétrico ou não)
- Prurido

**Exemplo real**: "apareceu uma escara nova no calcanhar, vermelha."

### Classe 8 — Higiene / Cuidados Diários
- Banho realizado / recusado / parcial
- Mudança de decúbito (turn schedule)
- Higiene íntima
- Curativo realizado
- Tricotomia, corte de unhas
- Cuidado com sonda/cateter

**Exemplo real**: "banho ok, troquei a SVD, drenagem clara."

### Classe 9 — Consumo / Estoque / Financeiro
- Fraldas — qtd usada no dia, alerta de baixo estoque
- Medicamentos — nível por princípio ativo
- Materiais (gaze, soro, álcool, luva)
- Suplementos / dietas enterais (latas, pó)
- Equipamentos médicos (oxigênio, bomba infusão)
- **Custos**: gasto do dia/mês, comparativo com média
- Solicitação de compra

**Exemplo real**: "acabou a fralda M do seu João, só tem G."

### Classe 10 — Solicitações Gerais
- Consulta médica (de rotina ou urgência)
- Exame solicitado / agendado / realizado
- Visita familiar agendada
- Visita social (psicólogo, fisio, fono)
- Manutenção de equipamento
- Documentação (laudo, atestado)
- Transporte para fora (consulta externa, hospital)

**Exemplo real**: "filha do seu Pedro pediu pra agendar fisio essa
semana."

### Classe 11 — Equipe / Plantão
- Passagem de plantão
- Intercorrência durante plantão
- Ausência / atraso de cuidador
- Conflito interpessoal
- Sugestão / reclamação operacional

**Exemplo real**: "saí às 22h, deixei o seu Antonio dormindo e a
dona Maria com o glicosímetro do lado."

### Classe 12 — Eventos Sociais / Atividades
- Visita familiar realizada (quem, duração)
- Atividade ocupacional (terapia, recreação)
- Saída externa (passeio, igreja, consulta)
- Aniversário / data significativa

**Exemplo real**: "filha do seu Antonio veio visitar, ficou 1 hora,
ele chorou de emoção."

### Categoria especial — EMERGÊNCIA
Sub-classe transversal que corta as classes 2/3/5/7. Quando o
classificador detecta sinais de:
- Parada cardiorrespiratória
- Convulsão prolongada (>5 min)
- Trauma crânio-encefálico com perda de consciência
- Sangramento intenso ativo
- Dispneia grave / cianose

→ **Bypass da fila normal**. Aciona protocolo de SAMU/escalation
imediata + Sofia faz call-back automatizado.

---

## 3. Arquitetura proposta

### 3.1 Camadas

```
[áudio/texto WhatsApp]
        │
        ▼
[STT (já existe — Deepgram)]    ← áudio → texto
        │
        ▼
[Voice Biometrics (já existe)]  ← identifica QUEM falou
        │
        ▼
┌──────────────────────────────────────────────────────┐
│  Classifier multi-label hierárquico                 │
│  • Top-level: 12 classes (+ emergência)             │
│  • Sub-level: subcategoria por classe               │
│  • Extração estruturada: campos tipados por classe  │
└──────────────────────────────────────────────────────┘
        │
        ▼
[Routing por classe]
        │
        ├─→ Aferições  → tabela aia_health_vital_signs (typed)
        ├─→ Evento agudo → care_event + escalation
        ├─→ Medicação → med_event + estoque update
        ├─→ Eliminações → tabela eliminations (nova)
        ├─→ Comportamental → behavior_log
        ├─→ Consumo → estoque + financeiro
        ├─→ Solicitação → ticket queue
        └─→ Genérico → care_event "outros" (catch-all)
```

### 3.2 Schema híbrido (recomendação)

**Manter** `aia_health_care_events` como tabela "hub" — toda mensagem
gera 1 linha aqui (event_type = classe top-level + event_tags =
multi-label).

**Adicionar** N tabelas tipadas por classe (já temos algumas):
- `aia_health_vital_signs` (já existe via MedMonitor)
- `aia_health_med_events` (a criar) — confirmações/recusas
- `aia_health_eliminations` (a criar) — diurese/evacuação
- `aia_health_behavior_logs` (a criar)
- `aia_health_inventory_consumption` (a criar)
- `aia_health_service_requests` (a criar)

Cada tabela tipada referencia o `care_event_id` que a originou. Assim
mantém-se rastreabilidade ("essa medição veio do áudio X às 20:35
do cuidador Y").

### 3.3 Estratégia de classificação (proposta)

**Híbrida em 3 etapas:**

1. **Regex/keyword fast-path** — para emergências (não negociável,
   sem latência LLM): se transcrição contém "parada", "convulsão",
   "azulado/cianótico", "sangrando muito", "não acorda" → bypass
   imediato.

2. **LLM zero-shot multi-label** — para mensagem normal: prompt
   estruturado retorna JSON com:
   ```json
   {
     "primary_class": "aferição",
     "labels": ["aferição:pa", "medicação:tomada"],
     "extracted": {
       "aferição": {"pa_sistolica": 140, "pa_diastolica": 85},
       "medicação": {"name": "losartana", "action": "taken", "time": "08:00"}
     },
     "severity": "routine",
     "confidence": 0.84,
     "needs_clarification": false,
     "clarification_question": null
   }
   ```

3. **Confirmação interativa quando confidence < 0.6** — Sofia manda
   resposta única curta: "Entendi PA 140/85 do seu João. Confirma?
   (sim / outro)". Cuidador responde uma palavra; sistema atualiza.

**Por que não fine-tune custom**: dataset não existe ainda. Levar 6
meses de produção rotulada antes de tentar. Zero-shot bem prompted
chega a 85-90% em domínios estreitos como esse.

### 3.4 UI da plataforma — submenu

Cuidador NÃO vê submenu — fala/escreve livre. Mas a **plataforma
admin/clínica** ganha submenu por classe:

```
Inbox de Inputs (novo)
├── Aferições           [124]
├── Eventos clínicos    [8]    ← já existe parcial em /alertas
├── Medicação           [42]
├── Alimentação         [31]
├── Eliminações         [18]
├── Comportamental      [11]
├── Pele/Lesões         [3]
├── Higiene             [60]
├── Consumo/Estoque     [27]    ← novo: alerta vermelho de baixo estoque
├── Solicitações        [15]
├── Equipe/Plantão      [9]
└── Outros              [4]
```

Cada classe tem seu painel com colunas adequadas. Aferições mostra
gráfico de tendência. Consumo mostra ranking de gastos. Pele mostra
fotos anexadas. Etc.

---

## 4. Questões abertas (debate com LLMs)

### Q1 — Granularidade da taxonomia
12 classes top-level + ~8 subcategorias cada = ~100 rótulos. É
demais? Pouco? Cuidador não vê isso, mas o classificador precisa
distinguir.

**Para debate**: vale ter 6 classes mais grossas (Vital, Medicação,
Cuidado, Operacional, Solicitação, Emergência) ou as 12 propostas
acima refletem melhor a realidade clínica?

### Q2 — Multi-label vs single-label
Mensagens reais são multi-tópico. Multi-label resolve, mas
complica UI e routing.

**Para debate**: faz sentido o classificador retornar até N rótulos
(N=3?), ou forçar split do áudio em N mensagens lógicas no
backend antes de classificar?

### Q3 — Extração estruturada inline ou pós-classificação
Opção A: LLM classifica E extrai campos no mesmo prompt.
Opção B: LLM classifica → routing chama LLM novamente com prompt
especializado por classe pra extrair campos.

A é mais rápida, B é mais precisa.

**Para debate**: qual o tradeoff em escala (custo/latência) e
manutenibilidade?

### Q4 — Confirmação ativa ou passiva
- Ativa: Sofia sempre pergunta "confirma X?" antes de gravar
- Passiva: Sofia grava direto, cuidador corrige se errado
- Híbrida: ativa só em severidade≥urgent ou confidence<0.6

**Para debate**: cuidadores em ILPI carente toleram ping de
confirmação ou desistem de usar?

### Q5 — Vocabulário regional / gírias
"O Zé tá ruim das pernas" pode significar dispneia, dor, fraqueza,
queda iminente. Como o classificador robustece?

**Para debate**: vale construir glossário regional por tenant? Ou
investir em few-shot examples por região (NE, Sul, etc.)?

### Q6 — Onboarding
Como apresentar o sistema ao cuidador na primeira mensagem dele?

Opção A: tutorial via WhatsApp em 5 mensagens.
Opção B: cartilha física na ILPI + 1 mensagem de boas-vindas.
Opção C: zero onboarding — Sofia se vira sozinha e pergunta no
primeiro relato.

**Para debate**: qual maximiza adesão sem afastar pelo
"funcionamento mágico"?

### Q7 — Detecção de urgência por paralinguagem
Áudio com voz tremendo/chorando/gritando carrega informação que
texto perde. Vale usar modelo que detecta tom emocional além de
STT?

**Para debate**: ROI de adicionar análise paralinguística
(custo+latência) vs ganho marginal sobre LLM textual?

### Q8 — Multi-tópico em um único áudio (separação)
Cuidador grava 30s falando: "PA 140/85, deu o remédio, ele recusou
a janta, e tô preocupado porque tá com a perna inchada de novo."
São 4 inputs em 1 áudio.

Backend:
- Opção A: 1 care_event com 4 labels (multi-label)
- Opção B: split em 4 care_events linkados (parent_event_id)

**Para debate**: A é mais simples, B é mais "limpo" para
estatísticas. Qual o standard em healthcare?

### Q9 — Aferições "implícitas" (rotina)
PA medida 3x/dia para todos os hipertensos. Cuidador não vai
relatar todas se for repetitivo. Como capturar?

Opção A: Sofia agenda push proativo "manda PA do seu João".
Opção B: cuidador grava 1 áudio por turno listando todos.
Opção C: integração com aparelhos (MedMonitor) bypass humano.

**Para debate**: qual a estratégia que cuidador real adota
sustentavelmente?

### Q10 — LGPD + Trust score
Identificação por voice biometric (já implementado) → quando
cuidador A reporta sintoma da paciente B, qual o peso? Cuidador
treinado vs família vs paciente reportando sobre si.

**Para debate**: trust score por classe de input faz sentido? Ex:
relato de dor é mais confiável vindo do próprio paciente; relato
de PA é mais confiável vindo de cuidador treinado.

### Q11 — Casos sensíveis / abuso
Cuidador relata "o filho do seu João apareceu bêbado e gritou com
ele" ou "acho que a outra cuidadora não trocou a fralda do turno
passado".

São relatos de natureza social/legal que exigem manuseio diferente.

**Para debate**: como classificar e rotear? Categoria "ocorrência
social" separada? Notificar gestor humano sempre?

### Q12 — Métricas de sucesso
Definir KPIs antes de implementar evita métricas-de-vaidade.
Candidatas:
- Taxa de classificação correta (% validada por enfermeira)
- Tempo médio input → ação clínica
- Adesão (% cuidadores com ≥1 input/dia)
- Taxa de pedido de confirmação (proxy de incerteza do LLM)
- Eventos críticos perdidos (false negatives)

**Para debate**: qual KPI deve dirigir o roadmap?

---

## 5. Restrições do mundo real (não negociáveis)

1. **Latência total <8s** entre cuidador soltar o áudio e Sofia
   responder. Acima disso, cuidador desiste.
2. **Custo por input <R$0,02**. ILPI carente paga por uso; precisa
   ser sustentável.
3. **Funcionamento offline parcial**: WhatsApp Business reentrega.
   Sistema deve aceitar reordenamento.
4. **PT-BR coloquial brasileiro** — não é PT-PT, não é "português
   formal". Inclui regionalismos.
5. **Cuidador pode ter celular compartilhado** — dois cuidadores no
   mesmo número. Voice biometric é o desempate.
6. **LGPD**: dado clínico é dado pessoal sensível. Audit de
   consultas é obrigatório (já temos hash chain).

---

## 6. O que pedimos do panel de LLMs

Para cada questão Q1-Q12, retornar:

1. **Recomendação direta** com 1 frase justificativa.
2. **Risco principal** dessa escolha.
3. **Métrica para validar** se foi a escolha certa.
4. **Alternativa viável** caso a primeira falhe em 30 dias.

Adicional (opcional, alto valor):

- Citação de **case real publicado** de ILPI/healthcare usando
  classificação de input via mensageria (Sensi.ai, Hippocratic AI,
  K Health, etc.).
- Exemplo de **prompt zero-shot funcional** para Q3 (extração
  estruturada). Inclua few-shot com 2-3 exemplos PT-BR.
- Sugestão de **classe que faltou** no mapa da Seção 2.

---

## 7. Prompt template para alimentar GPT/Grok/Gemini

Cole o conteúdo deste documento + o trecho abaixo:

```
Você é consultor sênior em sistemas de saúde digital. Analise o
estudo acima sobre classificação de inputs de cuidadores de idosos
via WhatsApp em ILPIs brasileiras (incluindo lares carentes).

Sua tarefa:

1. Para cada questão Q1 a Q12, responda no formato:
   - Recomendação (1 frase)
   - Justificativa (3-5 frases)
   - Risco principal
   - Métrica de validação
   - Alternativa caso falhe

2. Avalie a taxonomia de 12 classes da Seção 2:
   - O que está bom
   - O que falta (3 classes ausentes, máximo)
   - O que é redundante (2 classes que poderiam fundir)

3. Critique a arquitetura da Seção 3:
   - Concorda com classifier híbrido (regex+LLM+confirmação)?
   - Schema híbrido (hub care_event + N tabelas tipadas) é o ideal?
   - Sugestão alternativa, se houver.

4. Forneça 2-3 cases reais (com fonte/link) de plataformas que
   fazem classificação de input semelhante em healthcare.

5. Escreva UM prompt zero-shot funcional (PT-BR, com few-shot de
   2 exemplos) para classificar uma mensagem livre de cuidador
   em (classe top-level, sub-label, severidade, campos extraídos).
   O output deve ser JSON estrito.

6. Aponte 3 furos/problemas no plano que ainda não foram cobertos.

Seja direto. Sem fluff. Resposta em PT-BR.
```

---

## 8. Próximos passos (após panel)

1. Consolidar respostas dos 3 LLMs em tabela comparativa por questão.
2. Cruzar divergências e tomar decisão (Alexandre + curador clínico).
3. Implementar:
   - Migration nova: tabelas tipadas por classe.
   - Service `input_classifier_service.py` (regex fast-path + LLM
     prompt + confirmação fluxo).
   - Frontend submenu por classe.
4. Validar em 1 ILPI piloto por 2 semanas antes de expandir.

---

**Autor**: Sofia/ConnectaIACare team
**Data**: 2026-04-28
**Versão**: 1.0 (pré-panel)
**Para uso interno** — não distribuir externamente sem revisão.
