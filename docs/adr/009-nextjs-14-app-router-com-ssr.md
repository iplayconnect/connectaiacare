# ADR-009: Next.js 14 com App Router e SSR padrão

- **Date**: 2026-04-19
- **Status**: Accepted
- **Deciders**: Alexandre (ConnectaIA)
- **Tags**: frontend, architecture, framework

## Context and Problem Statement

O dashboard médico/clínico do ConnectaIACare precisa exibir dados em tempo real (relatos, KPIs, classificações) com alta legibilidade e baixa latência percebida. Precisamos escolher framework frontend: React SPA, Next.js Pages Router, Next.js App Router, Remix, Astro, ou outra alternativa.

## Decision Drivers

- **Consistência com ConnectaIA**: CRM já usa Next.js 14 — engenheiro transita sem reaprendizado
- **Performance percebida**: dashboard médico deve mostrar primeiro paint rapidamente (SSR)
- **Dados dinâmicos**: relatos chegam em tempo real → refresh frequente
- **SEO**: não aplicável (dashboard interno autenticado)
- **Disponibilidade de componentes**: shadcn/ui + Tailwind é ecossistema React-first maduro
- **Complexidade de estado**: médio (páginas simples consultando API, sem estado global complexo)

## Considered Options

- **Option A**: Next.js 14 App Router + SSR por default (escolhida)
- **Option B**: Next.js 14 Pages Router (padrão antigo)
- **Option C**: React SPA puro (Vite + React Router)
- **Option D**: Remix
- **Option E**: Astro (para dashboards com pouca interatividade)

## Decision Outcome

Chosen option: **Option A — Next.js 14 App Router + Server Components por default, Client Components explícitos quando necessário**, porque combina SSR (primeiro paint rápido) com alinhamento de arquitetura com ConnectaIA (reuso de padrões) e facilita composição com shadcn/ui.

### Positive Consequences

- Páginas renderizam com dados no primeiro byte (sem waterfall de fetches client-side)
- Server Components reduzem JavaScript enviado ao browser (melhor performance mobile)
- `dynamic = "force-dynamic"` em páginas data-heavy garante freshness
- shadcn/ui + Tailwind integra nativamente
- Dockerfile multi-stage já maduro (usado na ConnectaIA)

### Negative Consequences

- App Router é novo (Next.js 13+) — alguma curva de aprendizado para padrões novos
- Cache de fetch do Next.js pode confundir em dados tempo-real — mitigado com `cache: 'no-store'` ou `revalidate: 0`
- Interatividade pesada (gravação de áudio, charts dinâmicos) requer `"use client"` explícito

## Pros and Cons of the Options

### Option A — Next.js 14 App Router + SSR ✅ Chosen

- ✅ Primeiro paint rápido com dados
- ✅ Server Components = menos JS no browser
- ✅ Alinhado com ConnectaIA (reuso padrões)
- ✅ Ecossistema shadcn/ui forte
- ❌ App Router ainda amadurecendo
- ❌ Cache de fetch precisa atenção

### Option B — Next.js Pages Router

- ✅ Mais maduro, documentação abundante
- ❌ ConnectaIA já migrou para App Router — divergência desnecessária
- ❌ Padrão legacy (Vercel está investindo em App Router)

### Option C — React SPA puro (Vite)

- ✅ Dev server rápido
- ✅ Menos "mágica" de framework
- ❌ Dashboard inicializa em branco — waterfall de fetches
- ❌ Precisa rolar auth middleware próprio
- ❌ SEO/sharing de links mais difícil (se algum dia precisar)

### Option D — Remix

- ✅ Excelente modelo de data loading
- ✅ Forms/actions maduras
- ❌ Ecossistema menor
- ❌ Time operacional (solo-Alexandre) = custo de switching
- ❌ Shadcn ecosystem ainda é React-first

### Option E — Astro

- ✅ Excelente para sites estáticos + conteúdo
- ❌ Dashboard é altamente interativo (auth, live data, gravação áudio)
- ❌ Menos adequado para SPAs com muito estado

## Design Notes

Estrutura do frontend em [frontend/](../../frontend):
- `src/app/` — App Router, Server Components por default
- `src/app/page.tsx` — Dashboard KPIs + distribuição + últimos relatos (server-rendered)
- `src/app/reports/[id]/page.tsx` — detalhe de relato com player de áudio (mix server + client)
- `src/components/` — shadcn/ui primitives + componentes custom
- `src/lib/api.ts` — cliente API tipado

Dados "dinâmicos" (live) usam `export const dynamic = "force-dynamic"` no top das páginas. No futuro, Socket.IO client pode adicionar live updates incrementais.

## When to Revisit

- Se Next.js lançar versão major com breaking changes (Next.js 15, 16) — avaliar upgrade
- Se performance p95 do dashboard > 2s em prod real (medido via Core Web Vitals)
- Se equipe crescer e padrões de estado complexo (Zustand/Redux) se tornarem necessários

## Links

- Código: [frontend/src/app/](../../frontend/src/app/)
- Config: [next.config.js](../../frontend/next.config.js), [tsconfig.json](../../frontend/tsconfig.json)
- Documentação: [INFRASTRUCTURE.md §2 D9](../../INFRASTRUCTURE.md)
- Relacionado: [ADR-010](010-multi-tenant-desde-o-dia-1.md) — para multi-tenant no frontend
