# Revisão das bases curadas — Henrique e Coordenadora PUC Farmácia

**Status**: pronto pra revisão
**Data**: 2026-05-09
**Onde revisar na plataforma**: `/admin/governance/curated-review`

---

## Sumário executivo

3 bases foram populadas como **baseline `draft`** pra suportar o novo wizard de cadastro de paciente que está sendo construído (PR 1 já mergeado, PR 2 em andamento). Vocês 2 são os reviewers oficiais — **toda entry precisa virar `approved`** pra entrar em produção.

| Base | Total | Categoria | Audit |
|---|---|---|---|
| **CID-10 geriátrico** | 150 entries | Subset clínico relevante pra idoso | versionado, search por nome técnico OU leigo OU código |
| **Medicamentos → classe** | 80+ entries | Mapping princípio ativo + marcas → classe terapêutica | usado pra cross-validation em texto livre |
| **Cross-validation (regras)** | 8 entries | Condição declarada × medicação esperada | dispara soft prompt no wizard |

Todas as 3 tabelas têm o mesmo ciclo: `draft` → `under_review` → `approved`. Cada decisão de review fica registrada (quem, quando, com qual nota). Edições bumpam `version`.

**Acesso na plataforma**: vocês têm role `clinical_reviewer` (Henrique) ou `farmaceutico` (Coordenadora — quando entrar formalmente). A página fica em **Governança Clínica → Revisão · Bases Curadas**.

---

## Base 1 — CID-10 geriátrico (150 entries)

### O que entra
Subset filtrado de CIDs comuns em geriatria, dividido em 13 categorias:

| Categoria | Quantos | Exemplos |
|---|---|---|
| `cardiovascular` | 20 | Hipertensão (I10), IAM (I21), AVC (I63/I64), FA (I48), TVP (I82), TEP (I26) |
| `respiratorio` | 11 | DPOC (J44.9), Asma (J45), Pneumonia (J18), Broncopneumonia (J15.9), Pneumonia aspirativa (J69.0), IRpA (J96.0) |
| `endocrino_metabolico` | 13 | Diabetes (E10/E11.x), Hipotireoidismo (E03), Dislipidemia (E78), Desidratação (E86) |
| `neurologico` | 14 | Parkinson (G20), Alzheimer (G30), Demência (F00/F01/F03), AIT (G45), Polineuropatia (G62), Delirium (F05) |
| `psiquiatrico` | 6 | Depressão (F32/F33), Ansiedade (F41), Insônia (F51.0), Alcoolismo (F10) |
| `osteomuscular` | 10 | Osteoporose (M81/M80), Artrose (M15/M16/M17), Atrofia muscular (M62.5), Fratura fêmur (S72) |
| **`infeccioso`** | **13** | **ITU (N39.0), Cistite (N30), Pielonefrite (N10), Pneumonia bacteriana (J18), Erisipela (A46), Celulite (L03), Herpes-zóster (B02), Sepse (A41), TB (A15), COVID (U07.1)** |
| `oncologico` | 9 | Câncer mama (C50), próstata (C61), cólon (C18), pulmão (C34) |
| `urinario` | 5 | DRC/IRC (N18), HPB (N40), Incontinência (R32) |
| `digestivo` | 7 | DRGE (K21.0), Cirrose (K74), HDA (K92.2), Constipação (K59.0) |
| `sensorial` | 5 | Catarata (H25), Glaucoma (H40), DMRI (H35.3), Presbiacusia (H91.0) |
| `cuidados_paliativos` | 9 | Caquexia (R64), Úlcera por pressão (L89), Cuidado paliativo (Z51.5), Risco de queda (R29.6) |
| `outro` | 9 | Cefaleia (R51), Dispneia (R06.0), Síncope (R55), Febre (R50) |

Cada entry tem:
- **`code`** — CID-10 oficial (ex: `I10`, `E11.9`, `N39.0`)
- **`description_pt`** — nome técnico oficial (ex: "Hipertensão essencial (primária)")
- **`description_layman`** — nome popular pro paciente entender (ex: "Pressão alta")
- **`category`** — uma das 13 acima
- **`description_en`** opcional — pra futuro export FHIR

### O que vocês validam
- A descrição leiga tá clara pra um paciente leigo? Vocês podem editar inline.
- Falta algum CID importante em geriatria que vocês usam frequentemente?
- Algum CID listado é raro demais e poderia sair?
- A categoria escolhida tá certa?

### Casos críticos pra olhar com cuidado
- **Diferenciação demência** (F00 Alzheimer / F01 Vascular / F03 Não-especificada / G30 doença de Alzheimer) — a redundância F00+G30 é proposital? Vocês querem manter?
- **AVC vs AVE** (I63/I64 = AVC, com nome leigo "Derrame") — terminologia que paciente entende mesmo é "derrame"?
- **`U07.1 COVID-19` + `B34.2 Coronavírus não especificado`** — vale manter os dois ou consolidar?
- **HPB (N40) vs IRC (N18) vs HAS hipertensiva (I12) renal** — sobreposição quando paciente declara só "problema de rim"?

### Como agir na UI
1. Filtrar por `Status: Rascunho` + categoria
2. Pra cada entry: clicar **"Aprovar"** (verde) se tá ok como está, OU
3. Clicar no ícone de edição pra mudar descrição/leigo/categoria/notas, depois aprovar
4. Pra entries que precisam discussão entre vocês 2: marcar como **"Em revisão"** + adicionar nota dizendo o porquê

---

## Base 2 — Medicamentos → classe terapêutica (80+ entries)

### Por que essa base existe
O paciente vai escrever medicação em **texto livre** ("tomo Losartana 50mg de manhã"). O sistema precisa identificar que isso é um anti-hipertensivo classe BRA pra rodar a cross-validation contra a HAS declarada.

Cada entry mapeia:
- **`active_ingredient`** — princípio ativo canônico (Losartana)
- **`brand_names`** — marcas comerciais (Cozaar, Aradois)
- **`match_patterns`** — substrings que casam em texto livre (`losartana`, `losartan`)
- **`therapeutic_classes`** — array de classes terapêuticas (`anti_hipertensivo`, `BRA`)
- **`main_indications`** — pra UI explicar (`HAS`, `IC`, `DM_nefropatia`)

### Cobertura por classe (do baseline)

| Classe | Medicamentos cobertos |
|---|---|
| **Anti-hipertensivos IECA** | Captopril, Enalapril, Lisinopril, Ramipril |
| **Anti-hipertensivos BRA** | Losartana, Valsartana, Olmesartana |
| **Diuréticos** | Hidroclorotiazida, Furosemida, Espironolactona, Indapamida |
| **BCC** | Anlodipino, Nifedipina, Verapamil, Diltiazem |
| **Betabloqueadores** | Atenolol, Metoprolol, Carvedilol, Bisoprolol, Propranolol |
| **Hipoglicemiantes orais** | Metformina, Glibenclamida, Gliclazida, Glimepirida, Empagliflozina, Dapagliflozina, Sitagliptina, Linagliptina, Liraglutida |
| **Insulinas** | NPH, Regular, Glargina |
| **Estatinas** | Sinvastatina, Atorvastatina, Rosuvastatina, Pravastatina |
| **Antiagregantes/anticoagulantes** | AAS, Clopidogrel, Varfarina, Rivaroxabana, Apixabana, Dabigatrana, Edoxabana |
| **Tireoide** | Levotiroxina, Propiltiouracil, Metimazol |
| **Broncodilatadores/corticoides inalatórios** | Salbutamol, Formoterol, Salmeterol, Tiotrópio, Ipratrópio, Budesonida, Fluticasona, Beclometasona |
| **Antidepressivos** | Sertralina, Fluoxetina, Escitalopram, Citalopram, Venlafaxina, Mirtazapina, Bupropiona |
| **Benzodiazepínicos** | Diazepam, Clonazepam, Alprazolam, Lorazepam |
| **Antipsicóticos** | Quetiapina, Risperidona, Olanzapina, Haloperidol |
| **Anti-Alzheimer** | Donepezila, Rivastigmina, Memantina |
| **Antiparkinsonianos** | Levodopa+Carbidopa, Pramipexol |
| **IBP / Refluxo** | Omeprazol, Pantoprazol, Esomeprazol |
| **Analgésicos / AINE** | Paracetamol, Dipirona, Ibuprofeno, Diclofenaco, Naproxeno |
| **Antibióticos** | Levofloxacina, Amoxicilina, Ciprofloxacina, Azitromicina |
| **Anti-histamínicos** | Cetirizina, Loratadina |
| **Corticoide oral** | Prednisona |
| **Bifosfonato** | Alendronato |
| **Suplementos** | Cálcio + Vitamina D |

### O que vocês validam

1. **Match patterns suficientes?** Paciente pode escrever de jeitos diferentes:
   - "puran t4" / "synthroid" / "euthyrox" / "levotiroxina" — todos casam Levotiroxina? ✅ (confiramos)
   - "AAS 100" / "aspirina infantil" / "ácido acetilsalicilico" — todos casam AAS? ✅
   - "metformina" / "glifage" / "glucoformin" — todos casam Metformina? ✅
2. **Classes terapêuticas corretas e padronizadas?**
   - Algumas classes estão como abreviação (`BRA`, `IECA`, `BB`, `BCC`, `SGLT2`, `DPP4`, `GLP1`, `IBP`, `AINE`). Coordenadora valida se esses são os termos que ela usaria.
3. **Faltou algum medicamento muito comum em geriatria?**
   - Sugestões clínicas vindas de vocês entram como entries novas
4. **Classes ambíguas?** Ex: AAS está como `antiagregante` E `AINE` (porque é os dois). Concorda?

### Caso especial: AAS (`acido acetilsalicilico`)
Está marcado como `antiagregante` E `AINE` ao mesmo tempo. Razão clínica: 100mg = antiagregante, 500mg = AINE/analgésico. A cross-validation usa essa duplicidade — paciente com **DAC** declarado mas tomando AAS 100mg → match em `antiagregante` → ok. Validar se essa abordagem funciona.

### Como agir na UI
- Filtrar por `Status: Rascunho` ou por `Classe terapêutica` (ex: filtrar só os BRAs)
- Edição inline permite ajustar match patterns / classes / indicações
- Se faltou um medicamento importante: por enquanto criar via SQL ou avisar (o PR 2 vai trazer botão "Adicionar novo")

---

## Base 3 — Cross-validation (8 regras baseline)

### O que faz
Dada uma condição declarada pelo paciente, dispara um **soft prompt** se nenhum medicamento da classe esperada estiver listado. Soft = não bloqueia salvar; só pede pro paciente confirmar o motivo.

### As 8 regras iniciais (ordem por severidade clinical)

| # | Condição | CID | Severidade | Classes esperadas |
|---|---|---|---|---|
| 1 | **Fibrilação Atrial (FA)** | I48 | **🔴 CRITICAL** | anticoagulante (Varfarina, DOAC) |
| 2 | **Diabetes Mellitus (DM)** | E11.9 | 🟠 HIGH | hipoglicemiante (Metformina, sulfonilureia, insulina, SGLT2, DPP4, GLP1) |
| 3 | **Insuficiência Cardíaca (IC)** | I50.9 | 🟠 HIGH | IECA/BRA + BB + Espironolactona |
| 4 | **Hipotireoidismo** | E03 | 🟠 HIGH | Levotiroxina |
| 5 | **DAC (coronariana)** | I25 | 🟠 HIGH | AAS + Estatina + BB |
| 6 | **Hipertensão Arterial (HAS)** | I10 | 🟡 MEDIUM | qualquer anti-hipertensivo (IECA/BRA/BB/BCC/diurético) |
| 7 | **DPOC** | J44.9 | 🟡 MEDIUM | broncodilatador (LABA/LAMA/corticoide inalatório) |
| 8 | **Asma** | J45 | 🟡 MEDIUM | broncodilatador + corticoide inalatório |

### Por que **FA = critical**
FA sem anticoagulação tem risco anual de AVC isquêmico de **5-7%** em paciente CHA2DS2-VASc ≥ 2 (idoso ≥ 65 quase sempre é). É a inconsistência mais grave em geriatria. Outras condições importantes mas não tão críticas — daí HAS é só `medium` (sem tratamento o paciente vai mal, mas não é evento agudo iminente).

### O que vocês validam
1. **As 8 condições estão certas pra começar?** Vocês mencionaram que adicionariam mais com o tempo. Quais sugestões pro próximo lote?
   - Sugestões minhas pra v2: hipotensão postural, anemia, refluxo (DRGE) sem IBP, osteoporose sem bifosfonato/cálcio
2. **Severidades fazem sentido?** Discordâncias bem-vindas — discussão sobre por que FA é critical e DM é high é exatamente o tipo de calibração que precisamos
3. **Classes esperadas cobrem o tratamento real?** Ex: HAS — só listei classes farmacológicas, não tratamento não-medicamentoso. O fluxo do wizard deixa o paciente responder "Em tratamento não-medicamentoso (dieta/atividade)" sem fricção
4. **Mensagem ao paciente** (`prompt_message`) — tom amigável vs assertivo. Cada uma vocês podem editar:
   - Atual exemplo HAS: *"Você marcou Hipertensão Arterial (HAS) mas não listou nenhum medicamento anti-hipertensivo. Está em tratamento sem medicamento, ou esqueceu de listar?"*
   - Validar se isso soa bem na voz do paciente

### Casos pra discussão clínica entre vocês

**FA + paciente jovem assintomático "esqueceu" anticoagulante** → o soft prompt funciona ou precisa virar HARD prompt (bloqueio)?

**HAS + Anlodipino (BCC)** → ok pra cross-validation (anti_hipertensivo cobre BCC). Mas e se paciente listou só `Hidroclorotiazida 25mg` em monoterapia em idoso? Tecnicamente cobre HAS leve, mas guideline brasileira (SBC) sugere combinação. Vocês querem que a regra ELEVE severidade quando vê `monoterapia + hidroclorotiazida` em idoso? Provavelmente tá fora do escopo MVP.

**DAC sem AAS mas com Clopidogrel** → ambos são `antiagregante` então a regra fica feliz. ✅

**Hipotireoidismo + paciente diz "tomo levo de manhã"** → casa por substring `levotiroxina`? Não, casaria só se patterns incluísse `levo`. Posso adicionar? Validar.

### Como agir na UI
- Cada regra tem botão **"Aprovar"** (verde) ou **"Editar"** (lápis)
- No editor: pode trocar severidade, mensagem, classes esperadas, match patterns
- Pode marcar **"Em revisão"** se quer voltar depois
- Toggle `active` desabilita a regra sem deletar (preserva histórico de versão)

---

## Como vocês vão trabalhar na plataforma

### Acesso
1. Login na plataforma com seu user
2. Sidebar → **Governança Clínica → Revisão · Bases Curadas**
3. 3 abas no topo: **CID-10** | **Medicamentos** | **Cross-validation**

### Stats no topo da página
3 cards mostram pra cada base: total / draft / em revisão / aprovado, com barra de progresso.

### Fluxo recomendado pra revisão (sugestão Claude)

**Sessão 1 — alinhamento (vocês 2 juntos por ~1h):**
- Henrique aprova rapidamente os CIDs óbvios (HAS, DM, AVC, etc.) — ~30 entries em 15min
- Coordenadora começa pelos medicamentos da especialidade dela
- Discutem as 8 cross-validation rules juntos (validam severidades)

**Sessão 2 — depth (assíncrono ao longo da semana):**
- Cada um pega ~20 entries por dia
- Marca `under_review` qualquer entry que tem dúvida
- Adiciona reviewer_notes pra contexto

**Sessão 3 — fechamento (~30min):**
- Revisam juntos os `under_review`
- Consolidam decisões
- Aprovam tudo

### Tempo estimado total
- CIDs (150): ~1h pra Henrique sozinho (aprovar) + 30min com Coordenadora (revisar layman)
- Medicamentos (80+): ~1.5h Coordenadora + 30min Henrique
- Cross-validation (8): ~30min vocês 2 juntos
- **Total: ~4 horas** distribuídas em 1 semana

---

## O que acontece após a aprovação

Quando vocês marcam tudo como `approved`:
- A próxima migration de seed em prod habilita os endpoints (`/api/cid10/search` e `/api/registration/validate` já filtram só `approved`)
- O wizard de cadastro do paciente (PR 2 que tá vindo) usa apenas as entries aprovadas
- Edições subsequentes bumpam version (audit completo)

Se vocês discordarem de algo no futuro, basta editar — toda mudança fica registrada (quem, quando, com qual nota). Sem hard delete: tudo é versionado.

---

## Suporte

- Dúvidas técnicas: comigo (Alexandre)
- Dúvidas clínicas entre vocês 2: discussão livre — eu não preciso estar
- Bug ou comportamento estranho da UI: me avisar pra fix rápido

Boa revisão!
