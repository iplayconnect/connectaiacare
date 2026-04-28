# Resposta ConnectaIACare → Tecnosenior — Integração Care Notes

**De**: Alexandre / ConnectaIACare
**Para**: Matheus / Tecnosenior
**Data**: 2026-04-28
**Referência**: API Care Notes / Addendums (docx enviado por Matheus)
+ conversa WhatsApp 28/04/2026.

---

## 1. Decisão de demo / piloto

Concordamos: **mantém os 2 campos atuais** da CareNote pro piloto:

- `content` — transcrição literal do áudio do cuidador (Deepgram).
- `content_resume` — resumo da Sofia, **incluindo a tipificação como
  texto livre** ("Aferição de PA + Recusa Alimentar — paciente João,
  PA 140/85, recusou metade da janta").

Não precisamos de campo JSON livre nem campo dedicado de tipo
agora. Faz a apresentação fluir e mantém o escopo do piloto enxuto.

---

## 2. Próxima etapa — quando estabilizar

Quando nossa taxonomia de classificação estiver homologada (8
classes top-level + subclasses), te alinhamos pra criar:

- **Campo estruturado** na CareNote (JSON ou colunas próprias) com
  `class`, `subclass`, `extracted_fields`, `confidence`,
  `severity`. Você já mencionou que pode criar o JSON livre — fica
  como caminho de menor atrito.

- **Tabela auxiliar de tipificação** com FK para o ID da nota
  principal, caso o JSON livre cresça demais. Você comentou que já
  existe a tabela auxiliar pra addendums seguindo esse padrão — então
  o caminho está aberto.

Antes de você mexer em qualquer schema do seu lado, eu te mando o
formato exato (campos, valores possíveis, exemplo real) pra batermos
nomenclatura. Não quero que você adicione coluna que depois precise
renomear.

---

## 3. Estrutura proposta do `content_resume` (pra demo)

Pra a apresentação ficar legível, o `content_resume` que vai pelos
nossos POSTs vai seguir um padrão consistente:

```
[CLASSE_PRINCIPAL] · [SUBCLASSE_SE_HOUVER]

Resumo: <descrição curta da Sofia em 1-2 linhas>

Dados extraídos: <campos numéricos quando aplicável>
Severidade: <rotina | atenção | urgente | crítica>
```

Exemplos:

```
AFERIÇÃO · Pressão Arterial

Resumo: Cuidador reportou PA 140x85 mmHg do Sr. João às 14h.
Sem queixas associadas.

Dados extraídos: PA sistólica 140, PA diastólica 85
Severidade: rotina
```

```
EVENTO_AGUDO · Queda

Resumo: Dona Maria caiu no banheiro às 09:20. Lúcida, sangrou
do nariz. Cuidadora aplicou compressa fria e está observando.

Dados extraídos: trauma=nasal, consciência=preservada
Severidade: urgente
```

Formato fixo permite que você (Tecnosenior) faça parsing simples no
front pra destacar visualmente, e quando subirmos pra estruturado
não precisamos mudar nada do conteúdo — só promover os campos a
colunas.

---

## 4. Pontos da nossa arquitetura que NÃO mudam

Confirmando o que conversamos: **a integração é unidirecional
ConnectaIACare → Tecnosenior**. Nosso modelo de dados, fluxo de
classificação, pipeline de áudio e Sofia ficam exatamente como
estão. A API care_notes é um **espelhamento**, não uma fonte de
verdade.

Implicações:

- Mantemos `aia_health_care_events` como hub central do nosso lado.
- O envio pra TotalCare é via fila com retry + idempotência (do
  nosso lado).
- Em caso de erro de rede, a fila reprocessa — não interrompe nosso
  fluxo principal.
- Edição de uma nota CLOSED no painel de vocês NÃO retroage pra
  nosso lado por enquanto (sem webhook reverso ainda — ver §5.4).

---

## 5. Perguntas pendentes pra fechar antes de implementar

Pra a integração ficar robusta em produção (não só no piloto),
preciso fechar 8 pontos com você. Os 3 primeiros são bloqueantes
pra começar o desenvolvimento:

### 5.1 (BLOQUEANTE) Mapeamento UUID ↔ ID numérico

A API de vocês usa `caretaker: int` e `patient: int`. Nossos IDs
são UUID. Sem mapping não consigo enviar nada.

**Pergunta**: existe endpoint do tipo
`GET /agent/patients/?cpf=X` ou
`GET /agent/caretakers/?phone=X` que retorna o ID interno de
vocês? Se sim, eu mantenho lookup automático no nosso lado.

Se não existir, alternativa é trocarmos um arquivo CSV
inicial `(uuid_nosso, id_voces)` por paciente/cuidador. Conforme
pacientes novos forem cadastrados, lookup pelo CPF resolveria.

**Preferência ConnectaIACare**: endpoint de lookup por CPF pra
paciente e por telefone pra cuidador. Evita batch sync.

### 5.2 (BLOQUEANTE) Idempotency key

Cenário: nosso POST chega no servidor de vocês, a CareNote é
criada, mas a resposta com o `id` se perde no caminho (timeout,
flutuação de rede). Na próxima retry, criamos duplicata.

**Pergunta**: vocês aceitam header `Idempotency-Key`? Se sim,
qual TTL? (Stripe usa 24h.)

Se não houver suporte, posso trabalhar no melhor esforço (cache
nosso de "já tentei enviar isso") mas duplicação raríssima ainda
acontece.

**Preferência**: `Idempotency-Key` nativo no servidor de vocês.

### 5.3 (BLOQUEANTE) Authentication

**Pergunta**: como vocês autenticam o agente? API key estática no
header `Authorization: Bearer <key>`? Tem rotação? Política de
expiração?

Eu preciso saber pra cadastrar no nosso secrets manager e
estabelecer rotina de rotação.

### 5.4 Webhook reverso (não-bloqueante)

Se um humano da TotalCare editar/fechar uma CareNote pelo painel
de vocês (ex.: enfermeira anota "alta hospitalar" e fecha
manualmente), nosso espelho fica desatualizado.

**Pergunta**: vocês mandam webhook pra um endpoint nosso quando
isso acontece? Ou ficamos com "fonte da verdade dividida" — vocês
mandam informativos cruciais por outro canal?

**Preferência**: webhook reverso eventualmente, mas não bloqueia
o piloto.

### 5.5 Rate limit (não-bloqueante)

Em pico de plantão noturno em ILPI grande temos rajadas de 30-50
relatos/min do mesmo tenant.

**Pergunta**: qual o limite por API key? Vamos estourar?

Se sim, dá pra fazer batch via `bulk/`? Posso agregar 10
relatos curtos do mesmo paciente em 1 chamada bulk.

### 5.6 `closed_reason` enum vs string livre

Nosso `aia_health_care_events.closed_reason` tem 8 valores enum
(cuidado_iniciado, encaminhado_hospital, transferido, sem_intercorrencia,
falso_alarme, paciente_estavel, expirou_sem_feedback, obito, outro).

**Pergunta**: vocês aceitam string livre no addendum de fechamento
ou tem enum próprio que precisamos mapear?

### 5.7 Anexos (não-bloqueante)

Hoje temos áudios dos cuidadores em `/api/reports/<id>/audio`.
Eventualmente fotos (ex.: úlcera de pressão).

**Pergunta**: a CareNote vai suportar attachment URL no futuro? Se
sim, mandamos URL externa pública assinada (S3 presigned ou nosso
endpoint com token de uso único).

### 5.8 `source` field

Você confirmou que `source` é forçado pra `"AGENT"` no servidor.
Tudo certo. Só registrando.

---

## 6. Roadmap proposto

| Fase | Prazo | O que entra |
|------|-------|-------------|
| Demo | esta semana | content + content_resume com tipificação inline (sem mudança schema) |
| MVP integração | próxima semana | Schema novo nosso (`aia_health_tecnosenior_sync`), service de envio com fila + retry, smoke test em sandbox |
| Produção | 2 semanas | Após respostas de §5.1-5.3, vai pra produção |
| V2 (estruturado) | quando taxonomia estabilizar | Promovemos campos do `content_resume` pra estruturado (JSON ou colunas próprias do lado de vocês) |

---

## 7. Próximo passo

Matheus, me responde:

1. As 3 perguntas bloqueantes (§5.1, §5.2, §5.3).
2. Se tem disponibilidade pra uma call de 30min pra fechar §5.4-5.8.

Se quiser, te mando o nosso doc interno
`docs/integracao_tecnosenior_care_notes.md` que tem o desenho
arquitetural do nosso lado (schema, service, retry, idempotência).
Não precisa, mas se ajudar pra você dimensionar do lado de vocês,
fala.

Abraço,
Alexandre — ConnectaIACare
