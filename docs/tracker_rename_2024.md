# Tracker RENAME 2024 — Cobertura do Motor Clínico Sofia

> Material para curadoria clínico-farmacológica · ConnectaIACare © 2026
> Editor primário: equipe clínica · Atualização contínua

---

## Sobre este documento

A ConnectaIACare adota **RENAME 2024** (Relação Nacional de Medicamentos Essenciais — Ministério da Saúde / CONITEC) como **base oficial de cobertura do motor clínico Sofia**.

Cada fármaco do RENAME tem status declarado no motor:

- ✅ **covered** — codificado nas 12 dimensões e em produção
- 🔵 **in_progress** — em codificação ativa neste sprint
- ⏳ **pending** — identificado como gap, aguardando curadoria
- ⊘ **not_applicable** — em RENAME mas fora do escopo (pediatria pura, oftalmologia, etc.)

**Meta**: 100% RENAME 2024 Componente Básico **relevante para adultos/idosos** (~150 princípios ativos), em 4-6 semanas a partir da contratação do farmacêutico sênior.

---

## Estado consolidado (snapshot inicial · pré-curadoria sênior)

### Componente Básico (atenção primária — prioridade máxima)

| # | Princípio ativo | Grupo | Relevância geriátrica | Status motor | Notas |
|---|---|---|---|---|---|
| 1 | losartana | BRA | high | ✅ covered | — |
| 2 | enalapril | IECA | high | ✅ covered | — |
| 3 | anlodipino | BCCa-DHP | high | ✅ covered | Cascata edema → diurético |
| 4 | propranolol | β-bloqueador não-seletivo | medium | ✅ covered | Beers AVOID se asma/DPOC |
| 5 | atenolol | β-bloqueador cardiosseletivo | high | ✅ covered | — |
| 6 | metoprolol | β-bloqueador cardiosseletivo | high | ✅ covered | — |
| 7 | carvedilol | β-bloqueador α/β | high | ✅ covered | IC sistólica preferencial |
| 8 | **hidroclorotiazida** | **Diurético tiazídico** | **high** | ⏳ **pending** | **Gap crítico** |
| 9 | **furosemida** | **Diurético de alça** | **high** | ⏳ **pending** | **Gap crítico** |
| 10 | **espironolactona** | **Diurético poupador K+** | **high** | ⏳ **pending** | **Gap crítico** |
| 11 | metformina | Biguanida | high | ✅ covered | Ajuste renal codificado |
| 12 | glibenclamida | Sulfonilureia | medium | ✅ covered | Beers AVOID idoso |
| 13 | gliclazida | Sulfonilureia | high | ✅ covered | — |
| 14 | **insulina_nph** | **Insulina basal** | **high** | ⏳ **pending** | **Schema diferente: dose por kg/glicemia** |
| 15 | **insulina_regular** | **Insulina rápida** | **high** | ⏳ **pending** | **Schema diferente** |
| 16 | acido_acetilsalicilico | Antiplaquetário | high | ✅ covered | — |
| 17 | clopidogrel | Antiplaquetário | high | ✅ covered | — |
| 18 | varfarina | Anticoagulante | high | ✅ covered | INR monitor |
| 19 | sinvastatina | Estatina | high | ✅ covered | — |
| 20 | atorvastatina | Estatina | high | ✅ covered | Interação anlodipino codificada |
| 21 | omeprazol | IBP | high | ✅ covered | Cascata B12/Ca codificada |
| 22 | fluoxetina | SSRI | medium | ✅ covered | — |
| 23 | sertralina | SSRI | high | ✅ covered | — |
| 24 | clonazepam | BZD | medium | ✅ covered | Beers AVOID, fall risk 2 |
| 25 | diazepam | BZD | medium | ✅ covered | Beers AVOID, fall risk 2 |
| 26 | haloperidol | Antipsicótico típico | medium | ✅ covered | Beers AVOID demência |
| 27 | risperidona | Antipsicótico atípico | high | ✅ covered | Beers AVOID demência |
| 28 | levodopa+carbidopa | Antiparkinsoniano | high | ✅ covered | — |
| 29 | metoclopramida | Procinético | medium | ✅ covered | Cascata discinesia tardia |
| 30 | ondansetrona | Antiemético 5HT3 | high | ✅ covered | QT longo cuidado |
| 31 | amoxicilina | Antibiótico β-lactâmico | high | ✅ covered | — |
| 32 | amoxicilina+clavulanato | Antibiótico β-lactâmico | high | ✅ covered | — |
| 33 | azitromicina | Macrolídeo | high | ✅ covered | QT longo |
| 34 | ciprofloxacino | Quinolona | high | ✅ covered | Tendinite, ajuste renal |
| 35 | sulfa+trimetoprima | Sulfa | medium | ✅ covered | Hipercalemia + IECA |
| 36 | paracetamol | Analgésico | high | ✅ covered | Ajuste hepático |
| 37 | dipirona | Analgésico | high | ✅ covered | — |
| 38 | ibuprofeno | AINE | high | ✅ covered | Triple Whammy codificada |
| 39 | alendronato | Bifosfonato | high | ✅ covered | Esofagite |
| 40 | levotiroxina | Hormônio tireoidiano | high | ✅ covered | Time-separation Ca++ |
| 41 | carbonato_calcio | Suplemento | medium | ✅ covered | — |
| 42 | **prednisona** | **Glicocorticoide** | **high** | ⏳ **pending** | **Cascata corticoide→hiperglicemia** |
| 43 | **prednisolona** | **Glicocorticoide** | **high** | ⏳ **pending** | — |
| 44 | **dexametasona** | **Glicocorticoide potente** | **high** | ⏳ **pending** | — |
| 45 | **hidrocortisona** | **Glicocorticoide** | **medium** | ⏳ **pending** | — |
| 46 | **verapamil** | **BCCa não-DHP** | **high** | ⏳ **pending** | **Bradicardia** |
| 47 | **diltiazem** | **BCCa não-DHP** | **high** | ⏳ **pending** | **Bradicardia** |
| 48 | **carbamazepina** | **Anticonvulsivante** | **high** | ⏳ **pending** | **Hiponatremia, indução enzimática** |
| 49 | **valproato_sodico** | **Anticonvulsivante** | **medium** | ⏳ **pending** | **Hepatotoxicidade** |
| 50 | **fenitoina** | **Anticonvulsivante** | **medium** | ⏳ **pending** | **Janela estreita** |
| 51 | **gabapentina** | **Dor neuropática** | **high** | ⏳ **pending** | **Ajuste renal** |
| 52 | **salbutamol** | **Beta-2 agonista** | **high** | ⏳ **pending** | — |
| 53 | **formoterol** | **LABA** | **high** | ⏳ **pending** | — |
| 54 | **budesonida** | **ICS** | **high** | ⏳ **pending** | — |
| 55 | **ipratropio** | **SAMA** | **high** | ⏳ **pending** | **ACB Score** |
| 56 | **tiotropio** | **LAMA** | **high** | ⏳ **pending** | **ACB Score** |
| 57 | **amitriptilina** | **Tricíclico** | **medium** | ⏳ **pending** | **Beers AVOID, ACB 3** |
| 58 | **nortriptilina** | **Tricíclico** | **high** | ⏳ **pending** | **Preferida vs amitriptilina** |
| 59 | **biperideno** | **Anticolinérgico** | **medium** | ⏳ **pending** | **ACB 3** |
| 60 | **acido_folico** | **Vitamina** | **medium** | ⏳ **pending** | — |
| 61 | **sulfato_ferroso** | **Mineral** | **high** | ⏳ **pending** | **Cascata IBP→ferro** |

> _Tabela inicial: 61 itens · 41 covered · 20 pending. Faltam ~90 itens da Componente Básica relevantes pra adultos/idosos pra fechar a meta de 100%._

### Componente Especializado (alto custo/raras — relevância selecionada)

| # | Princípio ativo | Grupo | Relevância geriátrica | Status motor | Notas |
|---|---|---|---|---|---|
| 1 | **donepezila** | **Inibidor colinesterase** | **high** | ⏳ **pending** | **Demência Alzheimer** |
| 2 | **rivastigmina** | **Inibidor colinesterase** | **high** | ⏳ **pending** | **Adesivo transdérmico** |
| 3 | **galantamina** | **Inibidor colinesterase** | **high** | ⏳ **pending** | — |
| 4 | **memantina** | **Antagonista NMDA** | **high** | ⏳ **pending** | **Ajuste renal obrigatório** |

> _Componente Especializado tem ~80 itens no total — a maioria fora do escopo geriátrico primário (oncologia, raras, transplante). Curadoria seleciona apenas relevantes pra cuidado contínuo._

---

## Pra preencher na curadoria sênior

Editor primário: **equipe clínica-farmacológica sênior** (em prospecção).

Para cada fármaco em `⏳ pending`:

```yaml
- principle_active: <nome>
  rename_componente: basico | estrategico | especializado
  geriatric_relevance: high | medium | low | excluded

  # Dim 1 — Dose máxima diária
  dose_max_geriatria: <valor + unidade — pra idoso ≥65>
  dose_max_adulto: <valor + unidade — referência geral>
  fonte_dose: anvisa | fda | rename | beers

  # Dim 2 — Beers 2023
  beers_status: AVOID | CAUTION | OK
  beers_condition: <ex "demência", "history of falls", "any">
  beers_rationale: <texto curto>

  # Dim 8 — ACB Score (0-3)
  acb_score: 0 | 1 | 2 | 3

  # Dim 9 — Fall risk score (0-3)
  fall_risk_score: 0 | 1 | 2 | 3

  # Dim 10 — Ajuste renal por ClCr
  ajuste_renal:
    clcr_50_90: <usar dose normal | reduzir | evitar>
    clcr_30_49: <ajuste>
    clcr_15_29: <ajuste>
    clcr_lt_15: <ajuste>

  # Dim 11 — Ajuste hepático
  ajuste_hepatico_child_a: normal | reduce_25 | reduce_50 | avoid
  ajuste_hepatico_child_b: <ajuste>
  ajuste_hepatico_child_c: <ajuste>

  # Dim 7 — Contraindicações por condição
  contraindicado_em: [<lista CID-10 ou condição clínica>]

  # Dim 6 — Interações principais com fármacos JÁ cobertos
  interage_com:
    - { com: <fármaco>, severity: contraindicated|major|moderate|minor,
        mecanismo: <texto>, recomendacao: <ação> }

  # Dim 12 — Constraints de sinais vitais
  constraint_vitais: [<ex "PA<110 = warning hipotensão">]

  # Schema RENAME-específico
  formas_disponiveis: [<comprimido, injetável, etc>]
  indicacao_sus: <indicação principal no SUS>
  notes_curador: <observações clínicas>
```

---

## Workflow de curadoria

```
1. Curador escolhe próximo lote (5-10 fármacos do tracker)
       ↓
2. Preenche schema YAML acima por fármaco
       ↓
3. Equipe técnica codifica nas tabelas do motor (12 dim)
       ↓
4. Run de testes:
   - Validação contra prescrições reais anonimizadas (golden dataset)
   - Cross-check com pacientes em produção (re-validação semanal)
       ↓
5. Curador aprova lote → status pending → in_progress → covered
       ↓
6. POST /api/clinical-rules/rename/<principle>/mark-covered
       ↓
7. View aia_health_rename_coverage_summary atualiza %
```

Cada lote leva ~30-45 min de curadoria sênior + 1-2 dias de codificação técnica + testes + promoção.

**Velocidade de cruzeiro alvo**: 2 lotes por semana = 10-20 fármacos por semana → 90 itens em 5-9 semanas.

---

## Endpoints disponíveis pra rastrear progresso

```
GET  /api/clinical-rules/rename/coverage
     → resumo % por componente + relevância geriátrica

GET  /api/clinical-rules/rename/gaps?relevance=high&componente=basico
     → lista de fármacos pending (priorização do próximo lote)

POST /api/clinical-rules/rename/<principle>/mark-covered
     → marca um fármaco como concluído (após codificação + revisão)
```

Frontend admin (`/admin/regras-clinicas/rename` — futuro 🔵) mostrará dashboard de progresso visual.

---

## Sobre RENAME 2024

**RENAME (Relação Nacional de Medicamentos Essenciais)** é publicada pelo Ministério da Saúde via CONITEC (Comissão Nacional de Incorporação de Tecnologias no SUS). Define os medicamentos que devem estar disponíveis no SUS pra atenção primária, secundária e terciária.

Estrutura RENAME 2024:

- **Componente Básico** — atenção primária, alta dispensação no SUS
- **Componente Estratégico** — HIV, tuberculose, hanseníase, malária, doenças de notificação compulsória
- **Componente Especializado** — alto custo, doenças raras

A versão completa está em domínio público (Portaria GM/MS Nº 4.876, de 26 de junho de 2024). Lista oficial:
https://www.gov.br/saude/pt-br/composicao/sectics/daf/rename

---

ConnectaIACare © 2026 · Material interno — equipe técnica + clínica
