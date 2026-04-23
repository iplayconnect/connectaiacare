# exploracoes/ — handoff Design ↔ Coder

> Pasta de trabalho entre **Claude Design** (prototipagem visual) e
> **Claude Coder** (integração ao frontend de produção).
> Tudo aqui é **descartável** — não vai pra produção direto.

## Estrutura

```
exploracoes/
├── README.md                   # este arquivo
├── mocks/
│   └── patients.ts             # fixtures canônicas (schema 1:1 com backend)
└── html/
    ├── alerts-panel.html       # protótipo Alertas (Design publica aqui)
    ├── onboarding-live.html    # protótipo Onboarding Live
    ├── prontuario-360.html     # protótipo Prontuário 360°
    └── pitch-landing.html      # protótipo Pitch
```

## Fluxo de trabalho

### 1. Design publica HTML
Claude Design cria `.html` standalone em `exploracoes/html/`. O HTML:
- Usa design tokens existentes (`frontend/src/app/globals.css`, `tailwind.config.ts`)
- Pode importar `mocks/patients.ts` como inspiração (copiar dados pra HTML)
- Inclui **todos os estados** (empty, loading, error, com dados)
- É revisável: Alexandre + Murilo abrem no navegador e comentam

### 2. Aprovação
Alexandre aprova ou pede iteração. HTML final é a **referência visual canônica**.

### 3. Coder traduz pra TSX
Claude Coder lê o HTML aprovado e gera componente TSX em `frontend/src/`:
- Usa componentes existentes quando possível (`classification-badge.tsx`,
  `glass-card`, `accent-gradient`, etc.)
- Substitui dados mock → hooks reais (`usePatient(id)`, `useAlerts()`)
- Adiciona tipos TypeScript derivados do mock
- Marca `// TODO:` onde backend ainda não expõe a API

### 4. Deploy
Commit → push → `bash scripts/deploy.sh` na VPS.

## Convenções

**Dados mock**: sempre schema idêntico ao backend. Se Design precisar de um
campo que não existe, abre issue em vez de inventar.

**Nomes de arquivo HTML**: `kebab-case` match com rota destino
(ex: `prontuario-360.html` → `frontend/src/app/patients/[id]/page.tsx`).

**Quando iterar vs. quando traduzir**:
- Iterar em HTML até a forma estar congelada
- Traduzir pra TSX só quando o protótipo estiver aprovado
- Re-traduzir se HTML mudar (TSX é **gerado**, HTML é **fonte**)

## Mocks disponíveis

Ver `mocks/patients.ts`:
- **Maria Santos, 78** — hipertensão + diabetes, 30d timeline rica
- **Antônio Ferreira, 82** — Parkinson inicial, queda recente
- **Lúcia Oliveira, 75** — Alzheimer moderado, demanda alta da família

Todos com schema 1:1 de `aia_health_patients`, `aia_health_reports`,
`aia_health_care_events`, `aia_health_vital_signs`, `aia_health_medication_events`.

## Gitignore

Esta pasta **VAI** pro git (versionamos protótipos aprovados).
O `node_modules/` interno (se existir pra testar HTML) NÃO vai — já coberto
pelo `.gitignore` global.
