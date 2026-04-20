# Requests for Comments (RFCs)

Documentos de **propostas em aberto** para decisões significativas que precisam
alinhamento de stakeholders antes de virarem ADRs imutáveis.

## RFC vs ADR (distinção crítica)

| | RFC | ADR |
|---|-----|-----|
| Timing | **Antes** da decisão | **Depois** da decisão |
| Status default | `Proposed` / `Draft` / `Under Review` | `Accepted` |
| Mutabilidade | Iterativo — muda durante review | **Imutável** (nova decisão = ADR novo) |
| Propósito | Buscar feedback + decisão | Registrar para posteridade |
| Audiência | Stakeholders atuais | Futuros engenheiros/investidores/auditores |

## Fluxo de vida

```
Ideia → RFC (Proposed) → Discussão → RFC (Accepted) → ADR correspondente
                                 ↓
                            RFC (Rejected) → lições capturadas
```

## Índice

| # | Título | Status | Driver | Data |
|---|--------|--------|--------|------|
| [001](001-estrategia-ecossistema-agentico.md) | Estratégia de Ecossistema Agêntico | Accepted | Alexandre | 2026-04-20 |

## Convenção

- Nome: `NNN-kebab-case-title.md`
- Zero-padded 3 dígitos
- Seguir template MADR do skill `.claude/skills/create-rfc/`
- **Nunca editar** um RFC `Accepted` — mudanças substanciais viram RFC novo
- Decisões aceitas devem gerar ADR correspondente em `docs/adr/`
