# Notification log — 2026-05-01

> Audit log manual (até a tabela `aia_health_notifications_log` da
> Fase 1 do framework Sofia institucional ser implementada).

## Disparo #001 — corpus_review_invitation

- **Timestamp**: 2026-05-01 (UTC-3)
- **Sub-agente conceitual**: clínico-corpus
- **Event code**: `corpus_review_invitation`
- **Disparo**: manual via SSH + `docker exec` no `connectaiacare-api`
- **Provedor**: Evolution API (`get_evolution().send_text`)

### Primary recipient

- **User ID**: `d2ee7cad-d261-4708-9f5d-5d57c3e7b5c4`
- **Nome**: Henrique Bordin
- **Role**: admin_tenant
- **Phone E.164**: `5551984928518`

### CC recipients

- **User ID**: `8065448a-ad70-4d63-9b0e-e9c70a49a8f2`
- **Nome**: Alexandre
- **Role**: super_admin
- **Phone E.164**: `5551996161700`
- **Motivo CC**: Henrique não é membro do corpo societário; sócio
  responsável (super_admin) recebe cópia conforme política
  hierárquica documentada em `docs/PLANNING_SUPER_ADMIN_PANEL.md`.

### Mensagem enviada ao Henrique

```
[Revisão Clínica · ConnectaIACare]

Olá, Henrique. Aqui é a Sofia.

O Alexandre te indicou como referência clínica do classificador
da plataforma. Esse classificador decide, a cada relato que um
cuidador me manda, em qual das 8 categorias clínicas o caso se
enquadra (intercorrência, sintoma novo, medicação, sinal vital,
etc.) — e isso governa se eu escalo pro médico, disparo alerta
crítico, ou registro em silêncio.

Antes da gente subir pra produção no piloto, *um clínico precisa
fixar o critério* dos casos de fronteira. São relatos do tipo
"tomou o remédio mas reclamou que ficou enjoado" — medicação?
sintoma novo? Os dois? — onde a sua resposta vira o gold-standard
contra o qual eu vou ser medida.

A página de revisão está pronta:
https://care.connectaia.com.br/admin/corpus-review

Acesso com o seu user atual (admin_tenant). Mostra um caso por
vez, 8 botões de categoria (já vem pré-selecionada a minha
sugestão — você só confirma ou corrige), campo opcional pra
justificativa, e um "Passar" pra quando você não quiser decidir
agora. Mobile-friendly. Toma 30-45 min se for de uma sentada,
mas pode parar e voltar — guarda onde você estava.

Briefing detalhado com dicas práticas de cada categoria:
https://github.com/iplayconnect/connectaiacare/blob/main/docs/CARTA_HENRIQUE_CORPUS.md

Qualquer dúvida técnica, fala comigo aqui mesmo. Pra qualquer
outra coisa, o Alexandre está em CC dessa mensagem.

— Sofia · ConnectaIACare
```

### Mensagem enviada ao Alexandre (CC)

```
[CC · Revisão Clínica]

Alexandre, registro: convidei o Henrique pra revisar o corpus de
classificação event_type. Mensagem dele segue abaixo.

Status:
• Destinatário: Henrique Bordin (51984928518)
• Evento: corpus_review_invitation
• URL: https://care.connectaia.com.br/admin/corpus-review
• Cases pendentes: 24

Mensagem enviada:
═══════════════════════════════════════════════════════════════
[Revisão Clínica · ConnectaIACare]

Olá, Henrique. Aqui é a Sofia.

[texto completo da mensagem dele acima]

— Sofia · ConnectaIACare
═══════════════════════════════════════════════════════════════

— Sofia · ConnectaIACare
```

### Resultado do disparo

| Destinatário | Phone | Evolution status | Message ID | Timestamp |
|---|---|---|---|---|
| Henrique Bordin | 5551984928518 | 201 PENDING | `3EB0F2F4778FE3E04FEC64` | 2026-05-01 17:47:56 |
| Alexandre (CC) | 5551996161700 | 201 PENDING | `3EB0DD9272156A1E9D98E2` | 2026-05-01 17:47:57 |

Comando executado:
```
docker exec -w /app -e PYTHONPATH=/app connectaiacare-api \
    python /tmp/dispatch_corpus_invite.py
```

Provider: `EvolutionClient.send_text` via `aia_health_evolution`
instance `9099a4cb-c10e-43e5-a168-34480d9461e6`.

Status final entrega depende de ACK do WhatsApp do destinatário —
PENDING é o estado inicial após Evolution aceitar o request.
