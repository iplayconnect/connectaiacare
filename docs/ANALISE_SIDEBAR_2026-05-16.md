# Análise funcional da sidebar — v2 (com inventário de código)

**Data:** 2026-05-16 · v2 com análise FUNCIONAL (não só labels)
**Escopo:** 34 itens × 4 grupos + 25 páginas órfãs identificadas

---

## ✅ O que JÁ está aplicado nesta entrega

1. **Tooltip ao hover (`title` attr) em todos os 34 itens** — descreve a função real de cada um, não duplica o label
2. **Renames funcionais aplicados** (baseados no inventário real do código):

| Antes | Depois | Por que |
|---|---|---|
| Dashboard | Dashboard | (mantido) |
| **Alertas** | **Alertas Operacionais** | Distinguir do clínico |
| Alertas Clínicos | Alertas Clínicos | (mantido — agora claro) |
| Relatos | Relatos | (mantido) |
| Pacientes | Pacientes | (mantido) |
| Teleconsulta | Teleconsulta | (mantido) |
| Sofia Chat | Sofia Chat | (mantido) |
| **Comunicação** | **Chamadas · VoIP** | Inventário: 3 tabs de ligação (nova/ativa/histórico) |
| **Equipe** | **Equipe Clínica** | Inventário: NÃO é só cuidador, é multi-role (médicos+enfermeiros+cuidadores+técnicos). Mantém "Equipe" + esclarece. |
| **Usuários** | **Usuários do CRM** | Distinguir de Equipe Clínica — quem TEM CONTA no painel |
| Papéis & Permissões | Papéis & Permissões | (mantido) |
| Biometria de Voz | Biometria de Voz | (mantido) |
| **Plantões** | **Escala de Cuidadores** | Distinguir de "Plantão Técnico P1". Inventário: turnos cuidadores. |
| **Fila de Revisão** | **Fila de Revisão · Safety** | Inventário: é fila do Safety Guardrail (não revisão clínica) |
| **Configurações** | **Padrões & Compliance** | **DESCOBERTA: NÃO é configuração editável!** Inventário: catálogo read-only de padrões (FHIR, CID-10, escalas, evidência) — vitrine compliance B2B. Nome anterior era enganoso. |
| Regras Clínicas (master) | Regras Clínicas (master) | (mantido) |
| **Cascatas** | **Cascatas Farmacológicas** | Nome explícito |
| **Revisão Clínica** | **Revisão · Clínica** | Padroniza prefixo com as outras 2 |
| Revisão · Corpus | Revisão · Corpus | (mantido) |
| Revisão · Bases Curadas | Revisão · Bases Curadas | (mantido) |
| Testes Sintéticos | Testes Sintéticos | (mantido) |
| **Cenários Sofia** | **Cenários da Sofia** | Português correto |
| Versões de Prompts | Versões de Prompts | (mantido) |
| Dashboard cross-tenant | Dashboard cross-tenant | (mantido) |
| Tenants | Tenants | (mantido) |
| Saúde da Plataforma | Saúde da Plataforma | (mantido) |
| **Risk Score** | **Risk Score Agregado** | Esclarece escopo (não é por paciente) |
| **Proactive Caller** | **Sofia Proativa** | Português + entendível pra não-tech |
| Leads · Lista (legado) | Leads · Lista (legado) | (mantido — marcar pra remoção em Fase 2) |
| **Comercial** | **Comercial · Funil** | Aponta pro recurso real (tem Funil, Agenda, Planos como tabs internas) |
| **Handoff · Atendimento Humano** | **Handoff · Fila** | Mais curto e específico |
| Central · ATENT 24/7 | Central · ATENT 24/7 | (mantido) |
| **Plantão · Contatos P1** | **Plantão Técnico · Contatos P1** | Distingue de "Escala de Cuidadores" |
| Conversas · Replay | Conversas · Replay | (mantido) |

---

## 🚨 DESCOBERTAS do inventário que mudaram o entendimento

### 1. **"Equipe" NÃO é só cuidadores**
Minha primeira sugestão foi renomear pra "Cuidadores". **Errada.** Código real (`/equipe`) consome `/api/listCaregivers` mas mostra **tabs por papel**: médicos, enfermeiros, cuidadores, técnicos. É equipe clínica completa. Mantido como "Equipe Clínica".

### 2. **"Configurações" não é configuração**
`/configuracoes` é um **catálogo READ-ONLY** de 8 grupos de padrões adotados (interop FHIR, codificação CID-10, medicamentos ANVISA, escalas, evidência, compliance, identidade, canais). É **vitrine pra cliente B2B** mostrando que somos compliance-first. **Nome anterior era enganoso pra qualquer admin que abrisse esperando editar setting.** Renomeado pra "Padrões & Compliance".

### 3. **"Alertas" vs "Alertas Clínicos" SÃO diferentes (não dá pra unificar em tabs)**
Inventário confirma:
- `/alertas` consome `/api/alerts` (triagem de care_events)
- `/alertas/clinicos` consome `/api/listClinicalAlerts` + `/api/acknowledgeClinicalAlert` (motor de validação farmacológica)

São backends DIFERENTES. Unificar em tabs internas seria refactoring de produto, não só UI. Por enquanto: renomeei pra "Alertas Operacionais" + "Alertas Clínicos" — distinção clara via tooltip.

### 4. **"Leads · Lista (legado)" — confirmado DEPRECATED**
Inventário marca explicitamente. Substituído por `/admin/system/operations/comercial/funil`. **Fase 2: remover do sidebar.** Por enquanto fica visível com label "(legado)" + tooltip "DEPRECATED".

### 5. **Páginas órfãs identificadas**
25 páginas existem em `frontend/src/app/**` sem entrada na sidebar:
- ✅ **Esperado órfãs:** `/login`, `/forgot-password`, `/reset-password`, `/cadastro`, `/perfil`, `/pitch`, `/planos`, todas dinâmicas `/[id]`
- ⚠️ **DEPRECATED a remover:** `/demo/onboarding` — explicitamente substituído por `/sofia`
- 🤔 **Investigar:** `/meu/[id]` — função pouco clara

---

## 📋 Fase 2 (médio prazo) — consolidações estruturais

### a. "Saúde da Plataforma" + "Risk Score Agregado"
2 itens consecutivos. Risk Score pode virar tab interna em Saúde. **Esforço:** 1h.

### b. Remover "Leads · Lista (legado)"
- Confirmar que ninguém ainda usa
- Migrar histórico pra dentro de Comercial · Funil como tab "Leads antigos"
- Remover entrada da sidebar
**Esforço:** 30min + análise de uso.

### c. Remover `/demo/onboarding` (página órfã DEPRECATED)
Limpar do código + redirect pra `/sofia`. **Esforço:** 15min.

### d. Sub-grupos visuais em "Governança Clínica" (8 itens) e "Sistema · Cross-tenant" (11 itens)
Adicionar separadores tipo `─ Regras ─`, `─ Revisão ─`, `─ Sofia ─` em Governança. E `─ Plataforma ─`, `─ Atendimento Humano ─`, `─ Operações ─` em Sistema. **Esforço:** 1h (requer modificar `Group` component pra aceitar sub-headers).

### e. Investigar `/meu/[id]` — manter ou remover?

---

## 📋 Fase 3 (longa) — refactoring de produto

### Unificar Alertas Operacionais + Clínicos sob um único `/alertas` com tabs

Hoje são páginas + backends separados. Pra unificar:
1. Refactor backend: criar `/api/alerts/unified?type=clinical|operational`
2. Refactor frontend: criar `/alertas` com tabs internas
3. Migrar todos os links/bookmarks/permissions

**Esforço:** 1 semana (não é só UI). Não fazer agora, mas registrar como tech debt.

---

## 🎯 Recomendação imediata

**O que já foi aplicado nesta entrega:**
- Tooltip ao hover (34 itens com descrição funcional)
- 15 renames pra eliminar ambiguidade real
- Diferenciação clara entre overlaps (Plantões vs Plantão P1, Equipe vs Usuários CRM, Configurações vs Padrões)

**Pra mergear e testar:**
- Hard refresh (`Cmd+Shift+R`)
- Hover sobre cada item: tooltip explica
- Validar com Henrique antes da reunião (será mais legível pra ele)

**Próximo passo após esta entrega:** decidir se vai pra Fase 2 (consolidações) ou pular pra próxima feature.
