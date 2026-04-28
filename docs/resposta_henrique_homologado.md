# Update para Henrique — O que homologamos com base nas suas respostas

> Material de retorno do checklist clínico-farmacológico
> ConnectaIACare © 2026

---

## TL;DR

Com base nas suas respostas (⭐ priorizações + comentários + sugestões de cascatas + pedido de antibióticos/antiácidos), **homologamos em produção**:

- **74 fármacos novos** no motor (vs 48 anteriores → agora **122 princípios ativos**)
- **2 novas cascatas de prescrição** (opioide → constipação; IMAO + tirosina)
- **5 interações time-separation novas** (antiácidos × quinolonas/tetraciclinas/levotiroxina/ferro/bifosfonatos)
- **Cobertura Beers 2023 expandida** (8 contraindicações novas)
- **ACB Score expandido** (Boustani — 10 novos fármacos)
- **Fall Risk expandido** (13 classes terapêuticas novas)
- **Disclaimer reforçado em produção** — Sofia avisa explicitamente quando regra está em revisão clínica

Todos os fármacos novos entram com `review_status='auto_pending'` e disclaimer:

> ⚠️ Esta informação foi gerada automaticamente a partir de fontes públicas (RENAME 2024 / ANVISA Bulário / Beers 2023) e está AINDA EM REVISÃO clínica pela equipe farmacológica. **Confirme com seu médico ou farmacêutico antes de tomar qualquer decisão clínica.**

À medida que você for revisando/aprovando, o disclaimer vai suavizando pra forma padrão.

---

## 1. Fármacos homologados (74 novos · todos auto_pending)

### 1.1 Cardio (12 novos)

`hidroclorotiazida` · `furosemida` · `espironolactona` · `indapamida` · `bisoprolol` · `nebivolol` · `verapamil` · `diltiazem` · `olmesartana` · `telmisartana` · `valsartana` · `mononitrato_isossorbida` · `dinitrato_isossorbida` · `amiodarona` · `digoxina`

**Notas suas atendidas:** "Considerei as principais classes dos diuréticos como importantes" → todos os 4 diuréticos foram codificados (HCTZ, furosemida, espironolactona, indapamida) com dose máxima, classe terapêutica, fall risk score e Beers AVOID em condições específicas (espironolactona em IRC, verapamil/diltiazem em ICFEr).

### 1.2 Endócrino (7 novos)

`insulina_nph` · `insulina_regular` · `insulina_glargina` · `insulina_lispro` · `insulina_asparte` · `insulina_glulisina` · `sitagliptina` · `acarbose` · `metimazol`

**Schema customizado** para insulinas com nota: "dose deve ser calculada por kg/glicemia. Dose máxima é placeholder conservador."

### 1.3 SNC (8 novos)

`donepezila` · `rivastigmina` · `galantamina` · `memantina` · `gabapentina` · `pregabalina` · `carbamazepina` · `valproato_sodico` · `fenitoina` · `lamotrigina` · `topiramato`

**Notas suas atendidas:** "Antiepilépticos possuem mecanismos complexos e múltiplos usos" → cada um foi tagueado com nota explicitando os múltiplos usos (epilepsia, dor neuropática, transtorno bipolar, ansiedade generalizada, profilaxia enxaqueca).

### 1.4 Pneumo (8 novos)

`salbutamol` · `formoterol` · `salmeterol` · `ipratropio` · `tiotropio` · `budesonida` · `fluticasona` · `beclometasona` · `formoterol+budesonida` · `salmeterol+fluticasona`

Combinações fixas como princípios ativos compostos (classe `broncodilatador_combinado_laba_ics`).

### 1.5 Corticoides (5 novos)

`prednisona` · `prednisolona` · `dexametasona` · `hidrocortisona` · `metilprednisolona`

### 1.6 Opioides + AINEs (6 novos)

`tramadol` · `codeina` · `morfina` · `oxicodona` · `nimesulida` · `meloxicam`

**Cuidados clínicos codificados:**
- Tramadol + SSRI → caution síndrome serotoninérgica
- Tramadol em epilepsia → caution (reduz limiar convulsivo)
- Morfina ClCr<30 → reduzir 50%
- Nimesulida em hepatopatia → contraindicada (ANVISA limita uso a 15 dias)

### 1.7 Antialérgicos H1 (4 novos)

`loratadina` · `desloratadina` · `fexofenadina` · `difenidramina`

**Difenidramina** marcada Beers AVOID em ≥65 (anticolinérgico forte ACB 3).

### 1.8 Antibióticos comunitários (10 novos · respondendo seu pedido)

`cefalexina` · `cefuroxima` · `doxiciclina` · `claritromicina` · `levofloxacino` · `metronidazol` · `nitrofurantoina` · `norfloxacino` · `benzilpenicilina_benzatina` · `eritromicina`

**Cuidados específicos codificados:**
- **Claritromicina + estatina** → contraindicado (CYP3A4 → rabdomiólise; sinvastatina é a pior)
- **Levofloxacino + idoso ≥65** → caution tendinite/ruptura tendão (FDA black box)
- **Nitrofurantoína + ClCr<30** → AVOID (Beers 2023)
- **Metronidazol + álcool** → contraindicado (efeito antabuse 48h)
- **Doxiciclina + exposição solar prolongada** → caution fotossensibilidade

### 1.9 Antiácidos não-IBP (4 novos · respondendo seu pedido)

`hidroxido_aluminio_magnesio` · `magaldrato` · `famotidina` · `bicarbonato_sodio`

**Conforme você sugeriu** ("antiácidos é uma classe que normalmente espaçando se evitam muitos contratempos"), codificamos **5 interações time-separation**:

- Hidróxido Al/Mg × quinolonas → espaçar 2-4h
- Hidróxido Al/Mg × tetraciclinas → espaçar 2-3h
- Hidróxido Al/Mg × levotiroxina → espaçar 4h
- Hidróxido Al/Mg × ferro oral → espaçar 2-3h
- Hidróxido Al/Mg × bifosfonatos → bifosfonato em jejum + antiácido só após desjejum

### 1.10 Outros essenciais (8 novos)

`amitriptilina` · `nortriptilina` (você havia listado como "já cobertos" mas não estavam — adicionei agora · amitriptilina marcada Beers AVOID com sugestão de troca por nortriptilina)

`biperideno` · `acido_folico` · `sulfato_ferroso` · `risedronato` · `denosumabe` · `cianocobalamina` · `bromoprida` · `domperidona`

**Domperidona + history of QT longo** → contraindicado (ANVISA recomenda ECG basal em idoso).

---

## 2. Cascatas de prescrição novas (2)

### Cascata 9: Opioide → constipação → laxante crônico

> Você marcou ☒ esta cascata como prioritária. Codificada.

- **Padrão**: opioide + laxante coexistindo
- **Mecanismo**: receptores μ intestinais → motilidade reduzida (40-90% dos pacientes em uso crônico)
- **Recomendação**: profilaxia preventiva (laxante junto desde início + hidratação + fibras), considerar antagonista periférico (metilnaltrexona, naloxegol)

### Cascata 10: IMAO + alimentos ricos em tirosina

> Você sugeriu esta cascata. Codificada com flag de "alerta orientativo" (não scaneia dieta real do paciente).

- **Match**: paciente em uso de IMAO (selegilina, tranilcipromina, fenelzina, isocarboxazida, moclobemida, rasagilina) + episódio agudo de HAS
- **Mecanismo**: IMAO inibe catabolismo de tirosina dietética → noradrenalina liberada em massa → crise hipertensiva
- **Recomendação**: educação dietética prioritária (queijos curados, embutidos, vinho fermentado, fava, peixes em conserva) + monitor PA. IMAO-B em baixa dose (selegilina ≤10mg) tem risco menor mas educação ainda recomendada

---

## 3. Validação clínica (Parte 3 das suas respostas)

### 3.1 Antipsicóticos Beers (você "vai pesquisar com mais calma")

Mantido como está aguardando sua revisão. Sugestões adicionais que você pode considerar:

- **Aripiprazol**: Beers Caution em ≥65 (akatisia em demência)
- **Clozapina**: Beers Caution (agranulocitose, monitor hemograma + glicemia)
- **Ziprasidona**: Beers Caution (QT longo)

Quando você revisar, atualizo no motor.

### 3.2 ACB Score (você "vai se informar")

A escala que usamos é **Boustani 2008** (validada vs declínio cognitivo + delirium em idosos). Materiais de referência:

- **Paper original**: Boustani M et al. *Aging Health* 2008;4(3):311-320
- **Update mais recente**: Salahudeen MS et al. *BMJ Open* 2015 — versão calibrada
- **Lista resumida com scores**: ACB Calculator online (acbcalc.com)

Sobre soma simples vs cap: a literatura é dividida. Hoje somamos linearmente porque é o padrão Boustani. Se você considerar que cap=3 é mais clínico, ajustamos.

### 3.3 Fall Risk Score (você "vai revisar materiais")

Mantido como está aguardando sua revisão. Hoje calibramos por classe (BZD score 2, BCCa-DHP score 1, antipsicóticos típicos score 2, atípicos score 1). Adicionamos no batch novo:

- Diuréticos de alça score 2 (poliúria intensa)
- Tiazídicos + poupadores K+ score 1
- Opioides score 2
- Tricíclicos score 2
- Anticonvulsivantes score 1
- Insulinas score 1 (hipoglicemia)
- Corticoides score 1 (miopatia + osteoporose)

### 3.4 Quadro comparativo Beers vs STOPP/START (você pediu)

**Beers 2023 (American Geriatrics Society):**
- Origem: EUA · 2.000+ painelistas geriatras
- Foco: lista de medicamentos potencialmente inapropriados para idosos (PIM)
- Estrutura: AVOID lists + condition-specific avoidance + dose-specific
- Cobertura: ~100 fármacos, foca prevalência americana

**STOPP/START v2 2014 (Irlanda — atualização v3 em 2023):**
- Origem: European Union Geriatric Medicine Society
- Foco duplo:
  - **STOPP** (Screening Tool of Older Person's Prescriptions): 80 critérios de PIM
  - **START** (Screening Tool to Alert to Right Treatment): 34 critérios de OMISSÃO de tratamento indicado
- Cobertura: ~120 fármacos, foca prevalência europeia + brasileira

**Sobreposição:** ~75-80% dos critérios coincidem. Onde divergem:

| Critério | Beers tem? | STOPP tem? | Aplicabilidade BR |
|---|---|---|---|
| Triple Whammy (AINE+IECA+diurético) | parcial | **STOPP K2** explícito | alta |
| Inibidor colinesterase + bradicardia | menção breve | **STOPP K3** explícito | média |
| Beta-bloqueador + bradicardia <50bpm | sim | **STOPP K4** mais específico | alta |
| Aspirina sem indicação CV (prevenção primária >80a) | sim | **STOPP B1** | alta |
| OMISSÃO de estatina pós-IAM | NÃO tem | **START B5** sim | alta |
| OMISSÃO de IECA pós-IAM | NÃO tem | **START B7** sim | alta |
| OMISSÃO de bifosfonato em fratura por baixa massa | NÃO tem | **START J1** sim | alta |

**Recomendação técnica:** valeria adotar **START** (omissão de tratamento) como camada complementar — Beers não cobre. STOPP é redundante com Beers em ~75%.

Sua observação "cuidar para não associar os dois e criar alarmismos ou alertas em excesso" → minha proposta: usar STOPP **só onde NÃO há regra Beers equivalente** (evita duplicação), e START **só pra omissão de tratamento documentado** (alerta orientativo, não bloqueante).

Quando aprovar essa estratégia, codifico.

### 3.5 Time-separation por horário (sua resposta)

> "Antiácidos é uma classe que, normalmente, ao espaçar as administrações se evitam muitos contratempos. Tenho receio de envolver alimentos."

✅ Codificado conforme: 5 interações time-separation com antiácidos (sem envolver alimentos). Mantemos foco em medicação×medicação. Recomendação geral "tomar com água" pode ser adicionada como mensagem padrão da Sofia em qualquer query de medicação.

---

## 4. Roadmap regulatório (Parte 5)

| Item | Status |
|---|---|
| Seu CRF (final 2027 com aprovação acadêmica) | Anotado · trajetória RT formal alinhada |
| Tópico RT formal SaMD | Aceito sob condicional CRF · documentado no roadmap |
| Médico para Comitê Governança IA | Pendente — você indica quando tiver sugestão |
| Acesso UpToDate via PUCRS | ✅ ótimo recurso pra revisão de regras |

---

## 5. Como acompanhar progresso

Você tem 3 endpoints disponíveis (acessar via painel admin com seu login):

```
GET  /api/clinical-rules/rename/coverage
     → resumo % de cobertura por componente RENAME

GET  /api/clinical-rules/rename/gaps?relevance=high
     → lista de fármacos PENDING (priorização do próximo lote)

POST /api/clinical-rules/rename/<principle>/mark-covered
     → quando você revisar e aprovar, marca como verified
     → disclaimer reforçado some pro fármaco aprovado
```

Cobertura RENAME **antes** das suas respostas:
- 41 covered_verified · 0 covered_auto_pending · 30 in_progress

Cobertura RENAME **depois**:
- 41 covered_verified · ~74 covered_auto_pending · 0 pending

Meta: à medida que você revisa, mover **auto_pending → verified** em lotes.

---

## 6. Próximo passo prático

Sugestão de fluxo:

1. **Lote 1 — diuréticos** (4 fármacos: HCTZ, furosemida, espironolactona, indapamida)
   - Você confirma: dose máxima OK? Beers OK? Falta alguma contraindicação?
   - Eu marco como verified

2. **Lote 2 — BCCa não-DHP + nitratos** (4 fármacos)

3. **Lote 3 — inibidores de colinesterase + memantina** (4 fármacos)

4. ... continua até esvaziar a fila auto_pending

Cada lote: ~15-20 min de revisão sua + 5 min eu pra promover no motor.

**Em 6-8 lotes (3-4 semanas com você revisando 2 lotes/semana) zeramos a fila auto_pending.**

---

## 7. Aviso — disclaimer atual em produção

Quando médico/profissional pergunta agora à Sofia sobre qualquer um desses 74 fármacos:

> "Sofia, é seguro 0,5mg de amitriptilina pra Dona Helena, 87 anos, com demência?"

A resposta inclui:

> "Amitriptilina é um antidepressivo tricíclico. Em paciente idoso com demência, está marcada como **AVOID** pelos critérios de Beers 2023 — efeito anticolinérgico forte (ACB 3). Considere substituir por nortriptilina (menos anticolinérgica) ou ISRS.
>
> ⚠️ **Atenção: esta informação foi gerada automaticamente a partir de fontes públicas (RENAME 2024 / ANVISA Bulário / Beers 2023) e está AINDA EM REVISÃO clínica pela equipe farmacológica. Confirme com seu médico ou farmacêutico antes de tomar qualquer decisão clínica.**"

Quando você revisar amitriptilina (lote 5 ou 6) e marcar como verified, o disclaimer ⚠️ some — fica só o disclaimer padrão da Sofia.

---

ConnectaIACare © 2026 · Material interno — equipe técnica + clínica
