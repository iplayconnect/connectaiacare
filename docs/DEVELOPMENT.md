# ConnectaIACare — Guia de Desenvolvimento

## Visão geral
Stack isolada da ConnectaIA produção. Backend Python Flask + Frontend Next.js 14.

## Requisitos

- Python 3.12
- Node.js 20+
- PostgreSQL 16 (com extensões `pgcrypto`, `uuid-ossp`, `pg_trgm`)
- Redis 7
- Docker + Docker Compose (para subir tudo junto)
- Chaves API:
  - Anthropic (Claude)
  - Deepgram (STT)
  - Evolution API (WhatsApp) — **já temos a V6 configurada**
  - Sofia Voice API (microsserviço existente)

---

## Setup local rápido (recomendado — Docker Compose)

```bash
cd "/Users/macnovo/Library/Mobile Documents/com~apple~CloudDocs/Python/ConnectaIACare"

# 1. Configurar .env
cp backend/.env.example backend/.env
# Editar backend/.env e preencher ANTHROPIC_API_KEY, DEEPGRAM_API_KEY

# 2. Subir todos os containers
docker compose up -d

# 3. Rodar migrations + seed (dentro do container)
docker compose exec -T postgres psql -U postgres -d connectaiacare \
    < backend/migrations/001_initial_schema.sql
docker compose exec -T postgres psql -U postgres -d connectaiacare \
    < backend/migrations/002_mock_patients.sql

# 4. Verificar
curl http://localhost:5055/health
# { "status": "ok", "service": "connectaiacare-api" }

# 5. Frontend
open http://localhost:3030
```

---

## Setup local sem Docker (desenvolvimento)

### Backend
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Assumindo postgres+redis já rodando localmente ou via Docker externo
./scripts/init_db.sh   # roda migrations + seed

# Rodar API em modo dev
python app.py    # serve em http://localhost:5055
```

### Frontend
```bash
cd frontend
npm install
npm run dev     # serve em http://localhost:3000
```

---

## Expor webhook para Evolution API

Para Evolution API conseguir chamar o webhook, precisamos de uma URL pública.

**Em produção** (VPS com Traefik): `https://demo.connectaia.com.br/webhook/whatsapp`

**Em dev local**: usar ngrok ou cloudflared
```bash
# Opção 1 — ngrok
ngrok http 5055
# Copiar a URL https://xxxx.ngrok.io e configurar no Evolution

# Opção 2 — cloudflared
cloudflared tunnel --url http://localhost:5055
```

## Configurar webhook da V6 no Evolution

```bash
curl -X PUT https://evolution.connectaia.com.br/webhook/set/v6 \
  -H "apikey: 5C979F27-8AF5-4546-86E5-55197FF72F1D" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://demo.connectaia.com.br/webhook/whatsapp",
    "enabled": true,
    "events": ["MESSAGES_UPSERT"]
  }'
```

Para reverter (voltar pra ConnectaIA produção):
```bash
curl -X PUT https://evolution.connectaia.com.br/webhook/set/v6 \
  -H "apikey: ..." \
  -d '{"url": "https://app.connectaia.com.br/webhook", "enabled": true}'
```

---

## Estrutura do código

```
backend/
  app.py                    # Flask app entry
  config/settings.py        # Carrega env vars
  migrations/
    001_initial_schema.sql  # Tables aia_health_*
    002_mock_patients.sql   # 8 pacientes + cuidadora
  src/
    handlers/
      pipeline.py           # Orquestra o fluxo end-to-end
      routes.py             # HTTP routes (webhook + API)
    services/
      evolution.py          # Wrapper WhatsApp
      transcription.py      # Deepgram STT
      llm.py                # Anthropic Claude
      patient_service.py    # Busca + matching fuzzy
      report_service.py     # CRUD de relatos
      analysis_service.py   # Motor de análise clínica
      session_manager.py    # Estado de conversa
      sofia_voice_client.py # Cliente Sofia Voz (HTTP API)
      postgres.py           # Pool de conexões
    prompts/
      patient_extraction.py # Prompt extração entidades
      clinical_analysis.py  # Prompt análise clínica + classificação

frontend/
  src/
    app/
      page.tsx              # Dashboard principal
      reports/
        page.tsx            # Lista de relatos
        [id]/page.tsx       # Detalhe de relato
      patients/
        page.tsx            # Lista de pacientes
        [id]/page.tsx       # Detalhe de paciente
    components/             # Header, ClassificationBadge
    lib/
      api.ts                # Client API tipado
      utils.ts              # Helpers (idade, timeAgo, etc.)
```

---

## Fluxo end-to-end do MVP

1. Cuidador grava áudio no WhatsApp → Evolution envia webhook para `/webhook/whatsapp`
2. `pipeline.py::handle_webhook()` recebe e identifica tipo = áudio
3. Evolution API retorna áudio em base64 via `/chat/getBase64FromMediaMessage`
4. Deepgram transcreve (nova-2 pt-BR)
5. Claude Haiku extrai entidades (`patient_name_mentioned`, sintomas, medicações)
6. PostgresService faz fuzzy match contra `aia_health_patients` usando `pg_trgm` + SequenceMatcher
7. WhatsApp envia foto + nome do paciente com botão de confirmação SIM/NÃO
8. SessionManager marca estado `awaiting_patient_confirmation`
9. Quando cuidador responde SIM: pipeline roda análise com Claude Opus
10. Análise usa: transcrição + entidades + ficha do paciente + últimos 5 relatos
11. Resultado classificado (routine/attention/urgent/critical) é salvo em `aia_health_reports`
12. WhatsApp envia resumo formatado
13. Se classification ∈ {urgent, critical}: dispara ligação proativa Sofia Voice
14. Dashboard (Next.js) consulta API periodicamente e renderiza em tempo real

---

## Troubleshooting

| Sintoma | Causa provável | Solução |
|---------|---------------|---------|
| `curl /health` falha | Backend não subiu | `docker compose logs api` |
| Webhook não recebe nada | URL pública errada no Evolution | Verificar `curl evolution.../webhook/find/v6` |
| "Not able to transcribe audio" | Deepgram key inválida | Verificar `.env` |
| Paciente não encontrado | `pg_trgm` não instalado | `CREATE EXTENSION pg_trgm;` |
| Sofia Voice call skipped | `SOFIA_VOICE_API_URL` vazio | Normal em dev local; configurar em prod |
| Frontend não conecta à API | CORS ou `NEXT_PUBLIC_API_URL` errado | Verificar `.env` frontend |

---

## Deploy (VPS Hostinger, compartilhando infra com ConnectaIA)

1. Cloudflare DNS no `connectaia.com.br`: A-records `demo.connectaia.com.br` e `care.connectaia.com.br` → `72.60.242.245` (Proxy ativo).
2. `git clone iplayconnect/connectaiacare` na VPS em `/root/connectaiacare`.
3. `cp backend/.env.example backend/.env` e preencher chaves reais.
4. `docker compose up -d --build` (cria postgres, redis, api, frontend).
5. Traefik (já rodando para ConnectaIA) vai rotear automaticamente pelos labels (`demo.connectaia.com.br` → api, `care.connectaia.com.br` → frontend).
6. Rodar migrations: `docker compose exec -T postgres psql -U postgres -d connectaiacare < backend/migrations/001_initial_schema.sql` e depois `002` e `003`.
7. Criar instância `connectaiacare` no Evolution + conectar chip `+55 51 99454-8043` (ver `docs/DEPLOY.md`).
8. Teste: enviar áudio para `+55 51 99454-8043`.

---

## Custos estimados (sprint 4 dias + demo)

| Serviço | Uso estimado | Custo |
|---------|-------------|-------|
| Claude (Haiku + Sonnet + Opus) | ~50 requests de teste | R$ 15-30 |
| Deepgram | ~30 min de áudio transcrito | R$ 5-10 |
| Sofia Voice (ligações teste) | ~10 ligações curtas | R$ 10-20 |
| **Total** | | **R$ 30-60** |

Produção: ~R$ 0,50 por relato analisado + R$ 0,30 por ligação Sofia Voz. Margem ampla sobre assinatura.
