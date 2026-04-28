# Checklist Henrique — Expansão do Motor Clínico para 80 Fármacos

> Material pra revisão clínica-farmacológica · Henrique Bordin
> Tempo estimado: 30-45 min · Pode ser preenchido direto neste arquivo

---

## Contexto

Motor de cruzamentos da Sofia hoje cobre **48 princípios ativos × 12 dimensões clínicas**. Estamos expandindo pra **80 fármacos** (~95% da prescrição geriátrica brasileira). A escolha de QUE fármacos adicionar e a validação dos parâmetros clínicos precisa da sua expertise.

**O que JÁ está coberto** (pra você não duplicar):
- Anti-hipertensivos: losartana, enalapril, anlodipino, propranolol, atenolol, metoprolol, carvedilol
- Antidiabéticos: metformina, glibenclamida, gliclazida, empagliflozina, dapagliflozina
- Antiplaquetários/anticoag: AAS, clopidogrel, varfarina, rivaroxabana, apixabana, dabigatrana
- Estatinas: sinvastatina, atorvastatina, rosuvastatina
- IBPs: omeprazol, pantoprazol, esomeprazol
- Antidepressivos: sertralina, fluoxetina, escitalopram, mirtazapina
- Hipnóticos/ansiolíticos: clonazepam, diazepam, alprazolam, zolpidem
- Antipsicóticos: haloperidol, risperidona, quetiapina, olanzapina
- Antiparkinsonianos: levodopa+carbidopa, pramipexol, ropinirol
- Antieméticos: metoclopramida, ondansetrona
- Antibióticos: amoxicilina, amoxi+clavulanato, azitromicina, ciprofloxacino, sulfa+trimetoprima
- Outros: paracetamol, dipirona, AINEs (ibuprofeno/naproxeno/diclofenaco), alendronato, levotiroxina, carbonato de cálcio

---

## Parte 1 — Priorização dos 30 fármacos faltantes

Pra cada classe abaixo, marque com ⭐ as moléculas que DEVEM entrar primeiro (ordem de prevalência na sua experiência clínica em geriatria brasileira). Marque com — as que podem esperar.

### 1.1 Anti-hipertensivos / cardiovasculares

```
[ ] Hidroclorotiazida (HCTZ)
[ ] Indapamida
[ ] Furosemida
[ ] Espironolactona
[ ] Bisoprolol
[ ] Nebivolol
[ ] Verapamil (BCCa não-DHP)
[ ] Diltiazem (BCCa não-DHP)
[ ] Nifedipino
[ ] Felodipino
[ ] Lercanidipino
[ ] Olmesartana / Telmisartana / Valsartana (algum BRA específico além de losartana?)
[ ] Mononitrato de isossorbida
[ ] Dinitrato de isossorbida
[ ] Amiodarona
[ ] Propafenona
[ ] Digoxina
```
**Comentários do Henrique:**
> 

### 1.2 Antidiabéticos / endócrino

```
[ ] Insulina NPH
[ ] Insulina Regular
[ ] Insulina Glargina
[ ] Insulina Lispro / Asparte / Glulisina
[ ] Sitagliptina (DPP-4)
[ ] Vildagliptina (DPP-4)
[ ] Linagliptina (DPP-4)
[ ] Pioglitazona
[ ] Acarbose
[ ] Metimazol
[ ] Propiltiouracila
```
**Comentários:**
> 

### 1.3 Sistema nervoso central (não psiquiátrico)

```
[ ] Donepezila
[ ] Rivastigmina
[ ] Galantamina
[ ] Memantina
[ ] Gabapentina
[ ] Pregabalina
[ ] Carbamazepina
[ ] Lamotrigina
[ ] Ácido valproico
[ ] Fenitoína
[ ] Topiramato
```
**Comentários:**
> 

### 1.4 Pneumológicos (DPOC, asma — muito frequente em idoso)

```
[ ] Salbutamol (broncodilatador SOS)
[ ] Formoterol (LABA)
[ ] Salmeterol (LABA)
[ ] Tiotrópio (LAMA)
[ ] Ipratrópio (SAMA)
[ ] Budesonida inalatória (ICS)
[ ] Fluticasona inalatória
[ ] Beclometasona inalatória
[ ] Combinações fixas (formoterol+budesonida, salmeterol+fluticasona)
```
**Comentários:**
> 

### 1.5 Corticoides sistêmicos

```
[ ] Prednisona
[ ] Prednisolona
[ ] Dexametasona
[ ] Hidrocortisona
[ ] Metilprednisolona
```
**Comentários:**
> 

### 1.6 Analgésicos opioides + AINEs adicionais

```
[ ] Tramadol
[ ] Codeína (puro ou com paracetamol)
[ ] Morfina
[ ] Oxicodona
[ ] Tapentadol
[ ] Nimesulida
[ ] Meloxicam
[ ] Celecoxibe (COX-2)
[ ] Etoricoxibe (COX-2)
```
**Comentários:**
> 

### 1.7 Antialérgicos / outros

```
[ ] Loratadina (não-sedativo)
[ ] Desloratadina
[ ] Cetirizina
[ ] Fexofenadina
[ ] Difenidramina (sedativo — Beers AVOID)
[ ] Hidroxizina (sedativo — Beers AVOID)
[ ] Prometazina (sedativo — Beers AVOID)
```
**Comentários:**
> 

### 1.8 Outros frequentes em geriatria

```
[ ] Tamsulosina (BPH)
[ ] Finasterida (BPH)
[ ] Dutasterida (BPH)
[ ] Doxazosina (BPH + HAS)
[ ] Oxibutinina (urgência urinária — Beers AVOID)
[ ] Mirabegrona (urgência urinária)
[ ] Risedronato (osteoporose)
[ ] Denosumabe (osteoporose)
[ ] Cianocobalamina (B12)
[ ] Sulfato ferroso
[ ] Bromoprida
[ ] Domperidona
```
**Comentários:**
> 

### 1.9 Falta alguma classe importante que eu não listei?

> _Escreva aqui o que falta:_

---

## Parte 2 — Para cada fármaco que você marcar com ⭐, precisamos disso

Pra cada fármaco aprovado, eu vou codificar nas 12 dimensões. **Pra acelerar, preciso que você responda essas 7 perguntas pra cada um** (ou pra um lote agrupado por classe — preferência sua).

Template de input que vou usar:

```yaml
- principle_active: <nome>
  alias_comerciais: [<lista>]
  classe_terapeutica: <usar taxonomia já existente: ieca, ara, betabloqueador_cardiosseletivo, etc — se nova classe, sugerir nome>

  # Dim 1 — Dose máxima diária
  dose_max_geriatria: <valor + unidade — pra idoso ≥65>
  dose_max_adulto: <valor + unidade — referência geral>
  fonte_dose: <ANVISA bulário | FDA | Beers | Outras>

  # Dim 2 — Beers 2023
  beers_status: <AVOID | CAUTION | OK>
  beers_condition: <ex "demência", "history of falls", "any" — qual condição dispara o AVOID/CAUTION>
  beers_rationale: <texto curto explicando>

  # Dim 8 — ACB Score (0-3)
  acb_score: <0=nenhum | 1=baixo | 2=moderado | 3=alto>

  # Dim 9 — Fall risk score (0-3)
  fall_risk_score: <0=baixo | 1=moderado | 2=alto>

  # Dim 10 — Ajuste renal por ClCr
  ajuste_renal:
    clcr_50_90: <usar dose normal | reduzir | evitar>
    clcr_30_49: <ajuste>
    clcr_15_29: <ajuste>
    clcr_lt_15: <ajuste>

  # Dim 11 — Ajuste hepático
  ajuste_hepatico_child_a: <normal | reduce_25 | reduce_50 | avoid>
  ajuste_hepatico_child_b: <ajuste>
  ajuste_hepatico_child_c: <ajuste>

  # Dim 7 — Contraindicações por condição
  contraindicado_em: [<lista de CID-10 ou condição: ex "G20", "I50", "demência">]

  # Dim 6 — Interações principais com fármacos JÁ cobertos
  interage_com:
    - { com: <fármaco>, severity: <contraindicated|major|moderate|minor>, mecanismo: <texto>, recomendacao: <ação> }

  # Dim 12 — Constraints de sinais vitais
  constraint_vitais: [<ex "PA<110 = warning hipotensão">]
```

**Não precisa preencher TUDO pra cada — só o que você sabe de cabeça/fontes confiáveis. Onde tiver dúvida, deixa em branco e eu busco em ANVISA/Beers/FDA.**

---

## Parte 3 — Validação clínica de regras existentes (auditoria)

Reservadas pra confirmar/corrigir o que já está no motor.

### 3.1 Beers 2023 — está completo nos antipsicóticos?

Hoje codificamos:
- haloperidol, risperidona, olanzapina, quetiapina → todos com Beers AVOID em demência

**Pergunta:** falta algum aripiprazol, ziprasidona, paliperidona, clozapina, lurasidona com regra Beers específica?

> Resposta:
>

### 3.2 ACB Score — alguma regra de cálculo está errada?

Hoje somamos linearmente: 1 amitriptilina + 1 oxibutinina = ACB 4 (cada conta como 3 + 3).

**Pergunta:** o ACB é mesmo aditivo ou tem cap? Algum fármaco no nosso motor tem score errado?

> Resposta:
>

### 3.3 Fall Risk Score — calibração

Hoje:
- benzodiazepínicos = score 2
- BCCa di-hidropiridínicos = score 1
- antipsicóticos típicos = score 2
- antipsicóticos atípicos = score 1

**Pergunta:** o Fall Risk Score que estamos somando faz sentido clinicamente? Soma simples ou cap em 3?

> Resposta:
>

### 3.4 STOPP/START — vale somar à Beers 2023?

Hoje usamos só Beers 2023. STOPP/START é mais europeia mas tem critérios complementares (ex: "STOPP K2 — AINE + IECA + diurético = IRA risk").

**Perguntas:**
- Vale a pena adicionar critérios STOPP que NÃO estão em Beers? (Ex: cascatas que já implementamos via Rochon BMJ 2017)
- Ou é redundante e Beers já cobre 80% do clinicamente relevante?

> Resposta:
>

### 3.5 Interações de absorção mitigáveis por horário

Hoje temos: **levotiroxina + carbonato de cálcio** → espaçar 4h (em vez de evitar).

**Pergunta:** que outras interações deste tipo (mitigáveis por espaçamento, não por contra-indicação) você acha que valem codificar?

Candidatos: AAS+IBP? Bifosfonato+leite? Quinolona+antiácido? Ferro+IBP?

> Resposta:
>

---

## Parte 4 — Cascatas de prescrição (dimensão 13)

Acabei de codificar 8 cascatas (já em produção):

1. **Triple Whammy** (AINE + IECA/BRA + Diurético → IRA)
2. **HAS induzida por AINE**
3. **Edema BCCa-DHP → diurético inadequado**
4. **Antipsicótico + antiparkinsoniano (paradoxal)**
5. **Metoclopramida → discinesia tardia**
6. **IBP crônico + suplemento B12/Ca**
7. **Anticolinérgico + laxante crônico**
8. **Corticoide → hiperglicemia → antidiabético**

### 4.1 Falta alguma cascata clinicamente relevante?

Ex que considero adicionar mas você confirma:
- [ ] Diurético tiazídico → hiperuricemia → alopurinol?
- [ ] Beta-bloqueador → bradicardia → marcapasso/atropina?
- [ ] Inibidor de colinesterase → bradicardia → marcapasso?
- [ ] Tramadol/opioide → constipação → laxante (separado de anticolinérgico)?
- [ ] Antipsicótico → síndrome neuroléptica → bromocriptina (rara mas grave)?

> Resposta + outras cascatas que você lembra:
>

### 4.2 Exclusões clínicas (quando uma cascata NÃO é cascata)

Hoje: paciente com Parkinson real (ICD G20/G21) é excluído da cascata "antipsicótico + antiparkinsoniano".

**Pergunta:** que outras exclusões precisamos codificar pra evitar falsos positivos?

> Resposta:
>

---

## Parte 5 — Roadmap regulatório (formal Henrique como farmacêutico responsável)

Pra ANVISA + CFM + papel formal seu no produto.

### 5.1 Você tem CRF ativo?

> _Sim/Não, em qual estado:_
>

### 5.2 Topa ser **Farmacêutico Responsável Técnico** da plataforma quando registrarmos como SaMD na ANVISA (Classe IIa)?

Isso envolve:
- Assinar o documento técnico do motor de validação
- Revisar atualizações trimestrais do motor
- Carimbar com seu CRF as referências usadas

> Resposta:
>

### 5.3 Comitê de governança IA (CFM 2.314/2022 + 2.454/2026)

Precisamos formalizar esse comitê. Você + Alexandre + Médico Responsável (a definir). Tem alguma sugestão de médico geriatra que poderia compor?

> Resposta:
>

### 5.4 Referências para auditoria

Precisamos manter um arquivo de **fontes citadas** por regra (Beers 2023 ed completa, FDA labels, ANVISA bulário, KDIGO 2024). Você tem assinatura institucional de algum desses? (Lexicomp, UpToDate, Stockley's)

> Resposta:
>

---

## Como me devolver

Três opções:

1. **Edita este arquivo** direto e devolve via WhatsApp / Drive
2. **Áudio do WhatsApp** com as respostas (Sofia transcreve depois — irônico que estamos usando recursivamente)
3. **Call de 30min** comigo (Alexandre) percorrendo as perguntas — eu vou tomando notas

**Prioridade**: Parte 1 (lista priorizada) e Parte 2 (formato pra cada fármaco). As Partes 3-5 podem vir depois.

Quanto antes tivermos a Parte 1 fechada, eu já começo a codificar a infra das classes que faltam (algumas demandam novas tabelas — ex: insulina precisa schema diferente porque dose varia por kg/glicemia). Te entrego em iterações de 5-10 fármacos por vez pra você revisar antes do próximo lote.

---

ConnectaIACare © 2026 · Material interno — equipe técnica + clínica
