# Notification log — 2026-05-01

> Audit log manual (até a tabela `aia_health_notifications_log` da
> Fase 1 do framework Sofia institucional ser implementada).

---

## Disparo #001 — corpus_review_invitation

- **Timestamp**: 2026-05-01 17:47 (UTC-3)
- **Sub-agente conceitual**: clínico-corpus
- **Event code**: `corpus_review_invitation`
- **Provedor**: Evolution API (`get_evolution().send_text`)

### Recipients

| Tipo | User | Phone E.164 | Message ID | Status |
|---|---|---|---|---|
| Primary | Henrique Bordin (admin_tenant) | 5551984928518 | `3EB0F2F4778FE3E04FEC64` | 201 PENDING |
| CC | Alexandre (super_admin) | 5551996161700 | `3EB0DD9272156A1E9D98E2` | 201 PENDING |

CC justificada: Henrique fora do corpo societário; sócio responsável
recebe cópia conforme política em `docs/PLANNING_SUPER_ADMIN_PANEL.md`.

---

## Disparo #002 — corpus_review_url_update

- **Timestamp**: 2026-05-01 19:23 (UTC-3)
- **Sub-agente conceitual**: clínico-corpus
- **Event code**: `corpus_review_url_update`
- **Motivo**: Após Fase 0 do namespace separation deploy
  (`feat/separate-super-admin-namespace` → main), URL da página de
  revisão mudou de `/admin/corpus-review` → `/admin/governance/corpus-review`.
  Redirect 308 ativo, mas avisar destinatário evita confusão.

### Recipients

| Tipo | User | Phone E.164 | Status |
|---|---|---|---|
| Primary | Henrique Bordin (admin_tenant) | 5551984928518 | 201 PENDING |
| CC | Alexandre (super_admin) | 5551996161700 | 201 PENDING |

### Mensagem (Henrique)

```
[Atualização · Revisão Clínica · ConnectaIACare]

Olá novamente, Henrique. Aqui é a Sofia.

Reorganizamos o painel administrativo da plataforma e a página de
revisão do corpus mudou de endereço:

Novo: https://care.connectaia.com.br/admin/governance/corpus-review

(O link antigo que mandei ontem continua funcionando — redireciona
automaticamente, então se você já tinha clicado lá ou salvado, está
tudo certo.)

A página agora vive sob o grupo "Governança Clínica" no menu lateral,
junto com outras ferramentas clínicas cross-tenant. Nada mudou no
fluxo de revisão em si — mesmos casos, mesmos botões.

Qualquer dúvida, me chama aqui ou fala com o Alexandre.

— Sofia · ConnectaIACare
```

CC pra Alexandre incluiu o resumo técnico do deploy + mensagem
completa enviada ao Henrique.

---

## Padrão emergente

Disparos sequenciais (#001 → convite, #002 → atualização de URL)
demonstram o uso natural do framework Sofia institucional pra:

1. **Onboarding de revisor** (convite inicial)
2. **Notificação de mudanças operacionais** (URL/UI changes)

Quando a Fase 1 do framework subir, esses disparos vão direto pra
`aia_health_notifications_log` via `notification_dispatcher` em vez
de `docker exec` manual. A política `corpus_review_*` tem que cobrir
ambos os event codes.
