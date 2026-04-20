# ConnectaIACare — Design Brief

> **Propósito deste documento**: ponto de entrada único para designers (humanos ou agentes Claude Design) contribuírem com o projeto. Lê este brief + o código já existente em `frontend/src/` e o design system em `frontend/tailwind.config.ts` + `frontend/src/app/globals.css`, e já tem o suficiente pra produzir designs alinhados.

## 1. O produto em 3 parágrafos

**ConnectaIACare** é uma plataforma de cuidado integrado com IA para **idosos e pacientes crônicos**. O foco inicial é **geriatria em SPAs / ILPIs / residências**. O fluxo central é o cuidador gravar um áudio no WhatsApp contando sobre o idoso; a IA transcreve, identifica o paciente, cruza com o histórico clínico e medicações, classifica em 4 níveis de urgência (ROTINA, ATENÇÃO, URGENTE, CRÍTICO) e aciona quem precisa ser acionado — equipe de enfermagem via painel, familiar via ligação de voz natural se for crítico.

É uma parceria de 4 players: **ConnectaIA** (camada de IA), **Tecnosenior** (IoT ambiente + SPAs), **MedMonitor** (dispositivos clínicos homologados) e **Amparo** (atenção primária digital). O posicionamento é **"copiloto de saúde para o médico"** — IA apoia, médico decide (postura CFM 2.314/2022). A visão 18 meses é de **ecossistema em 4 camadas**: RELATO (MVP) → MONITOR (IoT + sinais vitais) → TELEMED (consulta vídeo com insights live + prescrição digital) → INTEGRA (FHIR hospitalar).

O produto é **multi-tenant desde o dia 1** (ADR-010) e **locale-aware desde o dia 1** (ADR-011) — começando em pt-BR, previsto para es-LATAM e Europa. Uma política crítica: **compliance CFM + LGPD + ANVISA** já embutidas no design. Dados médicos são sensíveis (Art. 11 LGPD) — a UI reflete isso (sem reciclagem casual de patterns de SaaS comercial).

## 2. Identidade visual estabelecida

Ver `frontend/tailwind.config.ts` e `frontend/src/app/globals.css`. Resumo:

**Nome do sistema**: "Modern Glass Health 2026" (herdado do design system "Modern Glass SaaS 2026" da ConnectaIA, adaptado para saúde — cyan→teal em vez de cyan→purple, mais vida/cuidado e menos CRM agressivo).

**Cor primária**: cyan elétrico `#31e1ff` (ação, links, KPIs em destaque)
**Cor secundária**: teal `#14b8a6` (cuidado, vida, acentos de saúde)
**Gradiente principal**: `linear-gradient(135deg, #31e1ff 0%, #14b8a6 100%)` — usar em logo, headlines principais, botões primários
**Background**: deep space fixed — radial cyan/teal subtle + linear gradient de `#050b1f` a `#081018`
**Dark mode por default**: `<html class="dark">` no layout raiz; tema light existe mas não é priorizado

**Paleta semântica de classificação** (crítica para alertas clínicos):
| Classificação | Cor | Tratamento visual |
|---------------|-----|-------------------|
| `routine` | Verde emerald `#34d399` | Dot + border suave |
| `attention` | Âmbar `#fbbf24` | Dot + border visível |
| `urgent` | Laranja `#fb923c` | Glow discreto |
| `critical` | Vermelho `#ef4444` | **Pulse-glow animado contínuo** |

**Componentes do design system** (já implementados como utility CSS):
- `.glass-card` — backdrop-blur 20px + cyan border hover (cards principais, KPIs)
- `.solid-card` — sem blur, para listas longas (performance)
- `.glass-header` — header sticky translúcido
- `.badge-classification` com variantes `.badge-{routine,attention,urgent,critical}`
- `.status-dot-{active,success,warning,danger}` — dots coloridos com glow
- `.accent-gradient-text` — headline em gradiente cyan→teal
- `.gradient-divider` — separador sutil com fade cyan
- `.shimmer` — loading state

**Tipografia**: Inter padrão + `font-mono` (JetBrains Mono) em valores técnicos (IDs, CID-10, telefone). **Tabular-nums em KPIs** para alinhamento.

**Icon set**: Lucide. Ícones comuns no produto: `HeartPulse`, `Stethoscope`, `Pill`, `Bot`, `Sparkles`, `AlertOctagon` (critical), `ShieldAlert` (urgent), `AlertTriangle` (attention), `CheckCircle2` (routine), `Mic`, `Users`.

**Animações** (em `globals.css`):
- `animate-fade-up` (entrada de páginas, 0.3s)
- `animate-pulse-glow` (critical badges, 2s loop)
- `animate-pulse-soft` (alerta flutuante quando há crítico pendente)
- Respeitar `prefers-reduced-motion` (já configurado)

## 3. Personas + contextos de uso

### Persona 1 — Médico / Enfermeiro chefe
- **Quem**: responsável técnico da unidade (SPA, ILPI, clínica). 30-55 anos.
- **Dispositivo**: desktop ou iPad no plantão.
- **Contexto**: abre o dashboard 3-10 vezes ao dia. Quer ver **o que mudou** e **o que precisa de atenção** imediatamente.
- **Necessidades**: triagem por classificação, histórico do paciente, áudio + transcrição originais, análise IA como contexto (não como ordem).
- **Anti-padrão**: não decidir pela IA; não esconder a fonte (transcrição crua deve ser fácil de acessar).

### Persona 2 — Cuidador profissional (no plantão)
- **Quem**: 20-50 anos, técnico ou enfermagem. Usa o produto **apenas via WhatsApp** — não abre dashboard.
- **Dispositivo**: celular compartilhado do plantão.
- **Contexto**: grava áudio sobre cada idoso a cada turno (ou quando há intercorrência).
- **Design implication**: toda a UX do cuidador acontece no **WhatsApp** (mensagens de texto, foto, confirmação, resposta estruturada). Só existe UI web para **onboarding** (enrollment de biometria de voz, aceite LGPD).

### Persona 3 — Familiar responsável
- **Quem**: filho/filha do idoso, 40-65 anos, fora da unidade.
- **Dispositivo**: celular (WhatsApp) primariamente; email secundário.
- **Contexto**: recebe notificações importantes + eventual ligação proativa de voz em crítico.
- **Design implication**: portal web futuro (não MVP) — acesso read-only ao estado do idoso. Nunca a detalhes clínicos sensíveis sem consentimento explícito.

### Persona 4 — Administrador (operador SPA/clínica)
- **Quem**: gestor da unidade, não clínico.
- **Contexto**: configura cuidadores, unidades, gerencia consentimentos LGPD, exporta relatórios.
- **Design implication**: área admin separada com UX mais tabelar/funcional.

## 4. Telas existentes (código vivo em `frontend/src/app/`)

| Rota | Arquivo | Persona | Status |
|------|---------|---------|--------|
| `/` | `app/page.tsx` | Médico/Enfermeiro | **Dashboard com KPIs, distribuição de classificações, relatos recentes, alerta flutuante em crítico** |
| `/patients` | `app/patients/page.tsx` | Médico/Enfermeiro | Grid de cuidados com 8 pacientes mock |
| `/patients/[id]` | `app/patients/[id]/page.tsx` | Médico/Enfermeiro | Detalhe: header, condições, medicações, alergias, responsável, timeline de relatos |
| `/reports` | `app/reports/page.tsx` | Médico/Enfermeiro | Lista de relatos com badge de classificação |
| `/reports/[id]` | `app/reports/[id]/page.tsx` | Médico/Enfermeiro | Detalhe: áudio + transcrição + análise IA estruturada (alertas, recomendações, tags) |

**Componentes reutilizáveis** em `frontend/src/components/`:
- `header.tsx` — logo gradient + navegação + status dot "Sistema ativo"
- `classification-badge.tsx` — badge com ícone, cor e animação por nível

## 5. Telas prioritárias pendentes (oportunidade para Claude Design)

### P1 — imediatas (primeiras 2 semanas pós-demo sexta 24/04)

1. **Login / Auth** — JWT via Authorization header (não cookie auth por enquanto). Acessível em `/login`. Postura de saúde: logo centralizado, sem gimmicks de marketing, input email + senha (futuramente 2FA obrigatório).
2. **Onboarding de Cuidador** — Wizard em 3-5 passos:
   - Aceite de termos LGPD específicos para dados de saúde
   - Gravação das 3 amostras de voz (biometria, ver `backend/src/services/voice_biometrics_service.py` para thresholds)
   - Confirmação + link pro WhatsApp dedicado
3. **Painel de Alertas Consolidado** — visão única cronológica por nível, com filtros. Médico abre isso primeiro no plantão.
4. **Detalhe do Paciente — aba "Timeline"** — sequência cronológica: relatos + (futuro) sinais vitais + (futuro) eventos de sensor. Hoje a página só mostra lista de relatos; próximo nível é UI de timeline temporal.

### P2 — Fase MONITOR (Q3 2026)

5. **Mapa do quarto** — visualização SVG do quarto com status dos sensores Tecnosenior em tempo real (movimento, cama, banheiro, gás). Inspiração: security dashboards tipo Home Assistant, simplificado.
6. **Gráficos de sinais vitais** — integração MedMonitor. Séries temporais de pressão, glicemia, SpO₂, peso. Recharts/Visx recomendado.
7. **Timeline integrado** — 3 tracks sincronizados: relatos + sinais vitais + sensores.
8. **Configuração de alertas por paciente** — regras customizadas (ex: "se pressão > 160/100 por 3 medições consecutivas → alerta").

### P3 — Fase TELEMED (ADR-012, a partir de Q4 2026)

9. **Scheduler de tele-consulta** — agendar médico ↔ paciente. Inspiração: Calendly + clínica.
10. **Sala de consulta — vista do paciente** — vídeo grande, controles mínimos, acessível a idoso (botões grandes, contraste alto).
11. **Sala de consulta — vista do médico** — vídeo do paciente + **painel lateral com insights live**:
    - Últimos sinais vitais (MedMonitor streaming)
    - Últimos 10 relatos + classificação
    - Alertas biometria recentes
    - Condições + medicações atuais
    - Análise IA da última interação
12. **Prescrição digital (PrescriptionPad)** — médico preenche durante/depois da consulta, assina via ICP-Brasil, envia para Memed.
13. **Waiting room** — paciente aguardando médico entrar (tela de espera com tranquilidade).
14. **Histórico de consultas** — para médico + paciente.

### P4 — Admin / backoffice

15. **Cadastro de Cuidadores** — CRUD + status do enrollment biométrico.
16. **Cadastro de Pacientes** — CRUD + upload de foto + vínculo com responsável.
17. **Cadastro de SPAs / Unidades** — multi-tenant (ADR-010).
18. **Audit log viewer** — busca + filtro no `aia_health_audit_chain`. Evidência LGPD.
19. **Gestão de consentimentos LGPD** — histórico de consent log por paciente, exportação (Art. 18 direitos do titular).
20. **Dashboard de saúde da plataforma** — métricas operacionais: latência pipeline, custo de IA por tenant, uptime.

## 5.1. Sinais vitais (MedMonitor) — especificação detalhada

Requisito adicionado 2026-04-20: o **Prontuário longitudinal** (P1 #4) deve exibir sinais vitais de acordo com a integração com MedMonitor (parceiro técnico que provê dispositivos clínicos homologados).

### Parâmetros suportados

| Parâmetro | Unidade | LOINC | Faixa idoso (routine) | Frequência típica | Origem |
|-----------|---------|-------|----------------------|-------------------|--------|
| **Pressão arterial** (sistólica/diastólica) | mmHg | 85354-9 / 8462-4 | 110-140 / 60-90 | 2-3x/dia | Manual, MedMonitor |
| **Frequência cardíaca** | bpm | 8867-4 | 55-90 (idoso em βblock: 50-70) | Contínua ou pontual | Manual, MedMonitor, wearable |
| **Temperatura** | °C | 8310-5 | 36.0-37.5 (idoso tem baseline ~0.5°C menor) | 1-3x/dia | Manual, MedMonitor |
| **Saturação O₂ (SpO₂)** | % | 59408-5 | 94-100 (DPOC crônico baseline 88-92) | Pontual ou contínua | Oxímetro MedMonitor, wearable |
| **Glicemia capilar** | mg/dL | 2339-0 | 70-180 (diabéticos: alvo mais flex) | 1-4x/dia (diabéticos) | Glicosímetro MedMonitor |
| **Frequência respiratória** | rpm | 9279-1 | 12-20 (>24 sinal IC/pneumonia) | Raro em home care | Manual, wearable |
| **Peso** | kg | 29463-7 | Alerta por delta (>2kg/semana) | 1-2x/semana | Balança MedMonitor, manual |

### Status de cada medição (mesma taxonomia do sistema)

- `routine` — dentro da faixa ideal
- `attention` — borderline, merece observação (ex: PA 145/92)
- `urgent` — fora da faixa clinicamente relevante
- `critical` — valor de emergência (ex: PA >180/110 = crise hipertensiva; SpO₂ <85)

Ranges adaptam-se por paciente: tabela `aia_health_vital_ranges` permite definir thresholds customizados (ex: paciente com DPOC crônico pode ter `routine_min` de SpO₂ em 88% em vez de 94%). Se não há range paciente-específico, usa-se o **range populacional default para idosos** (já populado pela migration 004, baseado em SBH/SBD).

### Design de visualização no Prontuário longitudinal

**Seção "Sinais Vitais" no topo do prontuário**, abaixo do header do paciente:

#### Header cards — Última leitura de cada parâmetro (4-6 cards em linha)

Cada card:
```
┌───────────────────────────┐
│  🩺  PA                    │  ← ícone + label curto
│                            │
│  128 / 82  mmHg           │  ← valor tabular, grande
│                            │
│  ● routine                 │  ← status dot + label
│  hoje · 08:12  ↗ +4        │  ← timestamp + trend vs média 7d
└───────────────────────────┘
```

Estados visuais:
- `routine`: card normal, dot verde
- `attention`: borda âmbar
- `urgent`: borda laranja + glow discreto
- `critical`: borda vermelha + **pulse-glow** (se não acknowledged)

Ícones (Lucide):
- PA: `Activity` ou `HeartPulse`
- FC: `Heart`
- Temperatura: `Thermometer`
- SpO₂: `Wind` ou custom "O₂"
- Glicemia: `Droplet`
- Peso: `Scale`

#### Timeline longitudinal (gráfico) — abaixo dos header cards

Para cada parâmetro, um mini-chart de 7 dias (30/90 selecionáveis):
- Tipo: **sparkline** ou área line
- Cor: escala cyan → teal do nosso design (linha principal)
- Bandas: zona verde (routine), amarelo (attention), laranja/vermelho (urgent/critical) em background semi-transparente
- Interatividade: hover mostra valor + timestamp + status

Biblioteca recomendada: **Recharts** (já disponível via `package.json` se adicionarmos) ou **Visx** se preferir mais controle. Não adicionar ApexCharts (pesado).

#### Detalhe expandido (click no card)

Ao clicar num header card, abrir painel lateral ou modal com:
- Gráfico maior (30/90 dias)
- Tabela de todas as medições do tipo, ordenada por data desc, com flag em linhas out-of-range
- Botão "exportar" (CSV / FHIR Observation JSON) — feature futura
- Notas da enfermagem associadas à medição (campo `notes`)

### Integração com resto do prontuário

Os sinais vitais devem **integrar-se com a timeline de relatos**:
- Se um áudio do cuidador menciona "pressão 160/100", a IA deve poder cruzar com medição MedMonitor mais recente e gerar alerta se divergirem significativamente
- Gráficos de PA e peso ao lado da timeline de relatos ajudam médico a ver correlação temporal ("depois do relato de dispneia no dia 3, pressão subiu dia 4")

### Endpoints backend já disponíveis

- `GET /api/patients/{id}/vitals/summary` — sumário pro header cards (última de cada tipo + trend)
- `GET /api/patients/{id}/vitals?type=blood_pressure_composite&days=7` — série temporal pra gráfico
- `GET /api/patients/{id}/vitals?days=30` — todas medições dos últimos 30 dias

### Mock data disponível para design

A migration 004 já seed 7 dias × 8 pacientes × ~1200 medições totais, com valores realistas por condição clínica do paciente (hipertensão → PA elevada baseline; diabéticos → glicemia varia 70-250; DPOC → SpO₂ 88-94). Claude Design pode usar esses dados pra prototipação real.

---

## 6. Princípios de UX específicos para saúde

1. **Sinal > barulho** — médico vê 50+ pacientes por semana; não sobrecarregar com decoração. Cada elemento na tela ganha seu lugar justificando valor clínico.
2. **Ordem de urgência domina a hierarquia visual** — critical > urgent > attention > routine. Sempre.
3. **Fonte sempre acessível** — transcrição crua nunca escondida atrás de "análise IA". O médico tem direito de ir direto ao áudio original.
4. **Ausência de data é tratada** — "nenhum relato ainda" precisa de mensagem humana, não tabela vazia.
5. **Acessibilidade WCAG 2.1 AA** — dashboard médico tem usuários com daltonismo (5-8% dos homens). Cores de classificação reforçadas com **ícones e texto** (não só cor).
6. **Texto técnico em fonte mono** — IDs, CID-10, dosagens. Deixa o olho pousar onde precisa de precisão.
7. **Evitar termos consumer-y** — nunca "Ops!", "Hey 👋", "Cool!". Saúde pede tom sóbrio sem ser frio.
8. **Responsive: desktop-first** — médico usa desktop/iPad. Paciente usa WhatsApp (não web). Não otimizar a web para celular pequeno.
9. **Dark como default** — plantão noturno é real. Dark reduz fadiga visual em monitores de UTI/SPA com baixa luz.
10. **Animações sutis** — fade-up em entrada, pulse em critical. Nada de "bounce" ou "wobble".

## 7. Referências e inspirações

**Positivas** (absorver):
- **Linear** — hierarquia, type scale, cursor interactions, status badges
- **Vercel dashboards** — glass morphism bem calibrado
- **Epic MyChart** — prontuário médico com clareza
- **Apple Health** — timelines e scores de saúde
- **ConnectaIA** (o projeto irmão) — nosso DNA visual vem de lá

**Negativas** (evitar):
- Ilustrações consumer cartunescas (Freepik-style)
- Emojis 😀 como decoração gratuita
- Cards gigantes com muito padding ("empty space by default")
- Gradientes roxos neon em tudo (vira "CRM genérico")
- Light mode por default (não é consistente com plantão noturno)

## 8. Como entregar designs

Qualquer uma ou combinação:

1. **PR direto no repo** — criar branch `design/<feature>`, modificar `frontend/src/` com componentes React + Tailwind
2. **Figma com anotações técnicas** — especificando tokens (`bg-card/70 border-accent-cyan/20`) para facilitar implementação
3. **Wireframes em Markdown** dentro de `docs/design/<tela>.md` — ASCII / Mermaid / descrição, seguido de screens em anexo
4. **Propostas de refinamento das telas existentes** — "pra melhorar o dashboard, propõe X, Y, Z com justificativas"

**Formato preferido**: PR direto, pequeno (1 tela ou 1 componente por PR). Facilita review e rollback.

## 9. Convenções de código (pra PR ser aceito sem atrito)

- **Server Components por default** (`page.tsx` já é); `"use client"` só quando necessário
- **Tailwind** (nunca CSS-in-JS ou CSS modules)
- **shadcn/ui primitives** já instalados: `@radix-ui/react-*`
- **Lucide icons** (nunca outros icon sets)
- **`date-fns`** para datas (já instalado); horas em pt-BR
- **Nunca `dangerouslySetInnerHTML`** com conteúdo de paciente (SECURITY.md §3.2)
- **`next/image`** sempre (nunca `<img>` raw)
- **Acessibilidade**: labels, contraste, navegação por teclado
- **Testar dark mode** (é o default — light pode estar quebrado)

## 10. Política de comunicação (se o design for aparecer externamente)

Ver `CLAUDE.md §10.2`. Em material externo (site, landing, press), **nunca nomear** Claude/Anthropic/Deepgram/etc. Usar "modelo de raciocínio clínico de última geração", "agente de voz natural", etc. Em UI interna do produto (onde só usuários autenticados veem), pode citar "IA" genericamente mas também evitar nomes de fornecedores.

## 11. O que NÃO fazer sem discussão prévia

- Adicionar novas libs pesadas (chart libs, animation libs) — discutir antes
- Mudar design tokens fundamentais (cores primárias, gradientes) sem justificativa
- Ilustrações grandes / mascotes de marca
- Sound design / audio cues (acessibilidade + contexto clínico pedem silêncio)
- Gamificação (streaks, pontos, níveis) — é sistema de saúde, não Duolingo

## 12. Contatos

- **Projeto**: `iplayconnect/connectaiacare` no GitHub
- **Design Lead**: Alexandre (CEO ConnectaIA)
- **Parceiros clínicos** (não design, mas contexto): Tecnosenior, MedMonitor, Amparo, Grupo Vita
- **Documentação viva** deste brief: abrir PR em `docs/DESIGN_BRIEF.md`

---

**TL;DR para IA/Designer**:
1. Leia este arquivo
2. Leia `CLAUDE.md` (contexto geral)
3. Leia `frontend/tailwind.config.ts` + `frontend/src/app/globals.css` (design tokens)
4. Leia `frontend/src/app/page.tsx` (exemplo de implementação do padrão)
5. Escolha uma tela da seção 5 (P1 recomendado)
6. Produza design + código
