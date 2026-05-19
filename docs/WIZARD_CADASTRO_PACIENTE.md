# Wizard de Cadastro Completo do Paciente

**Para:** Henrique Bordin + Coordenadora PUC (Farmácia/Geriatria)
**Contexto:** Reunião 2026-05-11 · 10:30
**Status:** UI entregue, conectada à base curada que vocês estão revisando

---

## O que é

O cadastro completo é o **ponto de entrada clínico** de um paciente na ConnectaIACare. Substitui a planilha que o cuidador/familiar hoje preenche manualmente e que depois ninguém valida.

Funciona como um wizard de **5 passos curtos** dentro da plataforma:

| # | Passo | O que captura |
|---|---|---|
| 1 | Quem está informando | Origem do dado (paciente, familiar, gestor, enfermeiro, médico, procurador) + termo LGPD |
| 2 | Identificação | Nome, CPF, nascimento, gênero, acomodação |
| 3 | Condições de saúde | Lista com **autocomplete CID-10** da base curada de vocês |
| 4 | Medicamentos em uso | Lista com **classificação automática** em classe terapêutica |
| 5 | Revisão | Alergias, responsável familiar e **cruzamento clínico** condição × medicamento |

Cada passo salva incrementalmente — o usuário pode fechar a aba e voltar depois sem perder nada.

---

## Por que vocês são parte essencial do processo

Os passos 3, 4 e 5 **não funcionam sem a base curada**:

- Passo 3 puxa CIDs da `aia_health_cid10_curated` (que vocês estão revisando)
- Passo 4 classifica medicamento via `aia_health_medication_class_dictionary` (idem)
- Passo 5 dispara alertas usando `aia_health_disease_medication_expectations` (regras de cruzamento)

Se vocês marcam uma regra como `under_review`, ela **não aparece** pro usuário no passo 5. Se marcam como `approved`, vira regra ativa. Vocês controlam o nível de assertividade do sistema.

---

## Provenance — o conceito-chave

Cada item (condição/medicamento/alergia) no cadastro carrega **de onde veio**:

```
{
  "name": "Hipertensão arterial",
  "cid10_code": "I10",
  "source": "family_declared",           // declarado pelo familiar
  "declared_at": "2026-05-11T14:32:00Z",
  "declared_by_user_id": "uuid-da-filha",
  "verified_by_clinician_at": null,      // ainda não validado
  "verified_by_user_id": null
}
```

Quando o(a) enfermeiro(a) ou médico(a) **valida** uma seção, os campos `verified_by_clinician_at` e `verified_by_user_id` são preenchidos. A UI mostra um selo verde "Validado por clínico" — vocês conseguem distinguir num relance o que é palpite da família vs. confirmação profissional.

### Por que isso importa pra prática

- **Para a Coordenadora:** num projeto de extensão, ela e os alunos vão saber **o que** revisar prioritariamente — itens sem `verified_by_clinician_at` ou com fonte conflitante (família declarou diabetes mas médico ainda não confirmou).
- **Para Henrique:** quando você roda uma análise farmacêutica, pode filtrar por `source = clinician_validated` se quer trabalhar só com dados auditados, ou incluir `self_declared` se quer ver o panorama bruto pra detectar gaps.

---

## Passo a passo

### Passo 1 — Quem está informando

Tela com 6 opções de **papel sob o qual o cadastro está sendo feito**:

- **Paciente (auto-declarado)** — idoso solo, fluxo B2C. Sofia trata em primeira pessoa.
- **Familiar responsável** — filho(a)/cônjuge/neto(a) preenchendo pelo idoso.
- **Procurador legal** — fluxo formal cartorial (em implementação).
- **Gestor da unidade** — coordenador(a) de ILPI / lar de idosos / Senior Living.
- **Enfermeiro(a)** — preenchendo durante admissão.
- **Médico(a)** — itens já entram com `source = clinician_validated`.

Se o papel é `paciente_b2c` ou `familiar_responsavel`, aparece um checkbox de **termo LGPD obrigatório** com captura de timestamp + IP do dispositivo. Auditável.

Esse papel fica **congelado na sessão** — uma vez iniciado, mudar de quem informa exigiria abrir uma nova sessão.

### Passo 2 — Identificação

Campos padrão: nome, "como é chamado(a)", CPF (com validação de dígitos verificadores), data de nascimento, gênero, forma de tratamento que a Sofia vai usar, "paciente reporta sobre si mesmo" (idoso solo), e dados de acomodação (unidade, quarto, nível de cuidado I-IV).

CPF é o gancho pra integrações externas (parceiro integrador).

### Passo 3 — Condições de saúde

Campo de busca com **autocomplete em tempo real** sobre a base CID-10 que vocês curam. Digita "hipert" → vê:

```
I10 — Hipertensão essencial (primária)
I11 — Doença hipertensiva do coração
I12 — Doença renal hipertensiva
```

Clicou → adiciona com o código preservado.

Pra cada item adicionado, dá pra marcar:
- **Severidade:** leve / moderada / severa
- **Controle:** controlada / descontrolada
- **Notas:** texto livre

Se a busca não encontra (ex: condição muito específica fora da base curada), aceita texto livre — entra sem `cid10_code` mas com um sinal pro próximo curador adicionar ao dicionário.

### Passo 4 — Medicamentos em uso

Campo de digitação simples ("losartana", "metformina", "donepezila"). Conforme digita (debounce 300ms), o sistema busca na base de medicamentos e mostra **feedback instantâneo**:

> ✓ Reconhecido como **losartana** · classe **Bloqueador do Receptor da Angiotensina (BRA)** (referências comerciais: Cozaar, Aradois, Corus)

Quando o usuário aceita, a `therapeutic_class` é estampada no item. Isso alimenta o passo 5.

Cada medicamento permite informar dose ("50 mg"), posologia ("1x/dia manhã") e notas.

### Passo 5 — Revisão

Três seções:

**a) Alergias** — campo simples (chips coloridos em vermelho/atenção).

**b) Responsável familiar** — nome, parentesco, telefone WhatsApp (a Sofia usa pra identificar familiar quando ele liga), e-mail opcional.

**c) Cruzamento clínico** — o coração do passo 5. O sistema roda automaticamente:

> Para cada condição declarada, qual classe terapêutica esperada? Está presente nos medicamentos?

Se falta algum, aparece um **prompt colorido por severidade**:

| Severidade | Cor | Exemplo |
|---|---|---|
| Crítico | Vermelho | "FA detectada sem anticoagulante. Risco anual de AVC isquêmico: 5–7%." |
| Importante | Laranja | "DM declarada sem antidiabético oral ou insulina." |
| Atenção | Amarelo | "HAS isolada em idoso — monoterapia pode não atingir alvo pressórico." |
| Sugestão | Azul | "Hipotireoidismo sem reposição hormonal documentada." |

Esses alertas **não bloqueiam** a finalização. São orientativos — a validação clínica formal é uma ação separada, feita por enfermeiro(a) ou médico(a) **depois**.

### Finalizar

Botão "Finalizar cadastro" → marca sessão como completa, atualiza `registration_completeness` do paciente, redireciona pro prontuário 360°. Aparece a porcentagem de completude no header (ex: "78% completo").

---

## O que **não** está no wizard (intencional)

- **Validação clínica formal** — fica em UI separada (enfermeiro/médico abre uma seção, lê o que foi declarado, clica "Validar" → estampa `verified_by_clinician_at`). Vai vir num próximo PR.
- **Sinais vitais** — preenchidos pelo cuidador no dia-a-dia (não fazem parte do cadastro inicial).
- **Plano terapêutico individualizado** — saída do trabalho farmacêutico/médico, não do cadastro.
- **Procurador formal com cartório** — em fila pra implementação (PR 4).
- **Cadastro B2C 100% público (idoso sozinho sem login)** — fluxo separado, próximo do `/registro` (ainda não construído).

---

## Como vocês vão experimentar amanhã

Vou abrir a plataforma e mostrar:

1. **Prontuário de um paciente já importado** da parceiro integrador — vocês veem os dados em formato antigo (string array) sendo lidos corretamente.
2. **Backfill rodado** — esse mesmo paciente agora tem cada item com `source = imported_partner` (sem perder o nome original).
3. **Wizard aberto pelo botão "Cadastro" no prontuário** — começamos do zero pra mostrar os 5 passos.
4. **Autocomplete CID-10** funcionando (limitado ao subset que vocês têm aprovado em `aia_health_cid10_curated`).
5. **Lookup de classe terapêutica** com losartana / metformina / donepezila.
6. **Cross-validation** disparando alertas de FA / DM / HAS conforme cenário.
7. **Painel `/admin/governance/curated-review`** — onde vocês trabalharão a revisão das bases.

A demo dura ≈15 minutos. O resto da reunião podemos usar pra:
- Definir cadência de revisão das bases (Henrique sugeriu 3 sessões de ~1h30)
- Decidir engajamento da Coordenadora no time (proposta separada será apresentada)
- Decidir se vamos adicionar mais classes/CIDs específicos pra geriatria

---

## Limites conhecidos (transparência)

1. **CID-10 PT-BR limitado a 150 entradas curadas hoje** — versão geriátrica focada nos diagnósticos mais frequentes. O dicionário completo do DataSUS tem ~14 mil códigos; conforme vocês validarem, podemos expandir.
2. **Cruzamento condição × medicamento limitado a 8 regras baseline** — todas validadas por vocês. A implementação suporta regras compostas (idade > X + comorbidade Y → severidade Z), mas hoje só usamos heurística simples.
3. **Sem extração automática de prescrição médica** — receita em PDF ainda precisa ser digitada manualmente. Pipeline de OCR + extração estruturada existe mas é outra demanda.
4. **Sem alerta de interação medicamentosa farmacológica direta** (ex: warfarina × AAS = sangramento) — hoje a régua é só "esperado vs. ausente". Adicionar a régua "presente mas perigoso" é evolução natural depois.

---

## Próximas perguntas pra Coordenadora amanhã

- Faz sentido criar uma classe terapêutica adicional para "Inibidores de Acetilcolinesterase" separada (donepezila/rivastigmina/galantamina), em vez de agrupar com "Drogas para demência"?
- Existem condições geriátricas frequentes que vocês acham que **não estão** nos 150 CIDs atuais e deveriam estar?
- Pra fragilidade (frailty), faria sentido adicionar como condição estruturada (vs. ficar só nas notas)? Henrique tinha levantado isso.
- Pra os alertas críticos (FA sem anticoagulante, em particular), faz sentido marcar como "exige decisão registrada" — ou seja, o clínico **precisa** justificar antes de prosseguir, mesmo que não bloqueie?
