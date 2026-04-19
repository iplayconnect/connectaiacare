# ConnectaIACare — Infraestrutura

Atualizado: 2026-04-19

---

## 1. Topologia em produção

```
                          ┌──────────────────────────┐
                          │   Cloudflare (DNS/CDN)   │
                          │  connectaiacare.com      │
                          └────────────┬─────────────┘
                                       │  TLS 1.3
                                       ▼
                          ┌──────────────────────────┐
                          │   Traefik (shared)       │
                          │   Let's Encrypt auto     │
                          │   72.60.242.245          │
                          └────────┬───────┬─────────┘
                                   │       │
              ┌────────────────────┘       └────────────────────┐
              ▼                                                 ▼
   ┌─────────────────────────┐                   ┌─────────────────────────┐
   │ demo.connectaiacare.com │                   │ app.connectaiacare.com  │
   │ → connectaiacare-api    │                   │ → connectaiacare-front  │
   │   :5055 (Flask/Gunicorn)│                   │   :3000 (Next.js)       │
   └───────────┬─────────────┘                   └────────────┬────────────┘
               │                                              │
               │      ┌──────────────────────────────────────┘
               │      │  REST: /api/*
               ▼      ▼
       ┌────────────────────────────────────────────────────────┐
       │           Rede Docker: connectaiacare_net              │
       │                                                        │
       │   ┌───────────────┐   ┌──────────────────┐            │
       │   │  postgres     │   │    redis         │            │
       │   │  pgvector:pg16│   │    redis:7       │            │
       │   │  :5433 (host) │   │    :6380 (host)  │            │
       │   └───────────────┘   └──────────────────┘            │
       └────────────────────────────────────────────────────────┘
                                   │
                                   │  (HTTPS externa)
             ┌─────────────────────┼─────────────────────┐
             ▼                     ▼                     ▼
     ┌──────────────┐      ┌──────────────┐     ┌──────────────┐
     │  Anthropic   │      │  Deepgram    │     │ Evolution    │
     │  Claude API  │      │  STT API     │     │ (shared com  │
     │              │      │              │     │  ConnectaIA) │
     └──────────────┘      └──────────────┘     └──────────────┘
                                                       │
             ┌─────────────────────────────────────────┘
             ▼ (network interna Docker, cross-project)
     ┌──────────────────────┐
     │ sofia-service:5030   │
     │ (Sofia Voz / Grok)   │
     │ roda no ConnectaIA   │
     └──────────────────────┘
```

---

## 2. Decisões arquiteturais

### D1. Stack isolada da ConnectaIA produção
**Por quê**: dados médicos são sensíveis, o CRM tem clientes pagantes, qualquer bug em um não pode afetar o outro.
**Como**: repo separado (`iplayconnect/connectaiacare`), container próprio, database separado, rede Docker própria, containers prefixados `connectaiacare-*`.
**Trade-off**: duplicação de código (aceito — copiar padrão, não importar). Manutenção paralela. Custo operacional baixo vs. benefício de isolamento.

### D2. Mesmo nó Hostinger + Traefik compartilhado
**Por quê**: 5 containers a mais num nó que já roda 15. Não justifica VPS separada no MVP. Traefik já gerencia certs Let's Encrypt.
**Trade-off**: falha hardware derruba ambos os produtos (risco aceito para MVP; VPS dedicada depois que houver 100+ pacientes reais).

### D3. Postgres compartilhado (mesmo Docker Engine, database separado)
**Por quê**: economia operacional. Não é mesmo cluster, é mesmo host.
Implementação: `connectaiacare-postgres` container próprio em `connectaiacare_net`. Database `connectaiacare`. Zero acoplamento de dados com `bbmd`.
**Trade-off**: backup e restore independente por container. Upgrade de pg major version requer upgrade dos dois.

### D4. pgvector em vez de vector DB dedicado
**Por quê**: evita adicionar complexidade (Qdrant/Weaviate/Pinecone). pgvector com IVFFlat ou HNSW escala até milhões de embeddings. Para ~1k cuidadores, é overkill usar serviço externo.
**Quando trocar**: > 100k embeddings ativos + latência p99 > 100ms.

### D5. Resemblyzer (em vez de pyannote.audio)
**Por quê**: Resemblyzer é leve (CPU-only, 256-dim), mature, fácil deploy. pyannote é SOTA mas requer GPU em produção para latência aceitável.
**Quando trocar**: >10k cuidadores OU taxa de falso-positivo medida > 2% em produção OU necessidade de diarização multi-falante.

### D6. WhatsApp Evolution compartilhado, instância V6 dedicada
**Por quê**: Evolution API é caro de subir novo container (hardware e setup). A instância V6 já está conectada e pode ser direcionada via webhook.
**Implementação**: mesma API Evolution, webhook da V6 aponta para `demo.connectaiacare.com/webhook/whatsapp`. Outras instâncias (V5, etc.) continuam no CRM.
**Trade-off**: se Evolution cair, os dois produtos caem. Aceito para MVP; futuramente Evolution dedicado ou EvoManager.

### D7. Sofia Voz via API (não clone de código)
**Por quê**: clonar o `sofia-service` em 4 dias é muito trabalho. A Sofia Voz já está containerizada e tem API HTTP. Tratamos como microsserviço externo — fronteira limpa, como faríamos com Google Speech ou qualquer provider.
**Trade-off**: acoplamento de runtime entre ConnectaIA e ConnectaIACare. Quando ConnectaIACare virar JV independente, migramos a cópia.

### D8. Hash-chain + OpenTimestamps em vez de blockchain pleno
**Por quê**: LGPD Art. 18 (eliminação) conflita com blockchain imutável. Hash-chain + âncora em blockchain pública dá prova de inviolabilidade sem as dores. Custo: centavos/dia. Ver SECURITY.md §3.3.

### D9. Next.js com SSR (app dir)
**Por quê**: páginas do dashboard médico são estáticas em comportamento, dinâmicas em dado. Pro SSR trazer dados no primeiro byte, sem waterfall de fetches.
**Exception**: páginas interativas (gravação de áudio, formulários) são client components.

### D10. Multi-tenant desde o dia 1, mesmo com 1 tenant
**Por quê**: baratíssimo incluir `tenant_id` em toda tabela/query. Caríssimo adicionar depois. Prepara para Amparo + Grupo Vita + outros SPAs sem refactor.
**Tenant inicial**: `connectaiacare_demo`.

---

## 3. Serviços rodando — detalhamento

### connectaiacare-api (Flask + Gunicorn)
- **Imagem**: build local (`backend/Dockerfile`)
- **Base**: `python:3.12-slim` + `ffmpeg` + `libpq-dev`
- **Workers**: 2 sync workers + 4 threads (`--workers 2 --threads 4`)
- **Memória**: ~500MB base + ~400MB quando Resemblyzer carrega
- **CPU**: 1-2 cores em uso médio, picos em análise IA
- **Porta interna**: 5055
- **Exposta externamente**: via Traefik em `demo.connectaiacare.com`
- **Healthcheck**: `GET /health` a cada 30s
- **Reinício**: `unless-stopped`

### connectaiacare-frontend (Next.js)
- **Imagem**: multi-stage build (`frontend/Dockerfile`)
- **Base runtime**: `node:20-alpine`, rodando como user `nextjs` (UID 1001)
- **Memória**: ~200MB
- **Porta interna**: 3000
- **Exposta externamente**: via Traefik em `app.connectaiacare.com`

### connectaiacare-postgres (pgvector/pgvector:pg16)
- **Porta exposta host**: 5433 (para desenvolvimento/debug; em produção tirar do host)
- **Volume**: `connectaiacare_pg_data`
- **Extensões habilitadas**: `pgcrypto`, `uuid-ossp`, `pg_trgm`, `vector`
- **Configuração**: defaults do pg16 — para produção ajustar `shared_buffers`, `work_mem`, `effective_cache_size` conforme RAM disponível

### connectaiacare-redis (redis:7-alpine)
- **Porta exposta host**: 6380
- **Volume**: `connectaiacare_redis_data`
- **Persistência**: AOF (append-only file) habilitado
- **Uso atual**: cache de sessões (via `session_manager` → Postgres, mas Redis é fallback futuro)
- **Uso futuro**: rate limiting, pub/sub para Socket.IO, cache de embeddings

---

## 4. DNS e certificados

### Cloudflare Records (a configurar)
| Tipo | Nome | Destino | Proxy |
|------|------|---------|-------|
| A | `connectaiacare.com` | 72.60.242.245 | ✅ Cloudflare |
| A | `app.connectaiacare.com` | 72.60.242.245 | ✅ |
| A | `demo.connectaiacare.com` | 72.60.242.245 | ✅ |
| CNAME | `www.connectaiacare.com` | `connectaiacare.com` | ✅ |

### TLS
- Traefik gera via Let's Encrypt (já usado para ConnectaIA)
- Renovação automática a cada 60-90 dias
- TLS 1.3 apenas; TLS 1.2 só se Cloudflare exigir
- HSTS: `max-age=63072000; includeSubDomains; preload` (configurar no header middleware do Traefik)

---

## 5. Dependências externas (pago)

| Serviço | Uso | Custo esperado (prod) |
|---------|-----|----------------------|
| Anthropic Claude | Análise clínica (Opus) + extração (Haiku) | ~$0,05-0,20 por relato |
| Deepgram | STT pt-BR (~60s áudio) | ~$0,012 por relato |
| Grok Voice (Sofia) | Ligações proativas | ~$0,30-0,80 por ligação |
| Evolution API | WhatsApp (shared) | custo fixo da ConnectaIA |
| Cloudflare | DNS + CDN | free tier inicial |
| Hostinger VPS | Shared com ConnectaIA | custo fixo |
| Backblaze B2 / S3 | Backup (P1) | ~$5/mês inicial |

**Custo estimado MVP (100 relatos/dia)**: ~R$ 150-300/mês.
**Custo estimado escala (10k relatos/dia)**: ~R$ 15k-30k/mês.

---

## 6. Backup e disaster recovery

### Estado atual (P1 — implementar antes de dados reais)
- **Postgres**: snapshot automático do Docker volume NÃO é backup (se container quebrar, dados podem se corromper).
- **Redis**: AOF habilitado, mas sessões são recuperáveis em DB.

### Proposto
```bash
# scripts/backup.sh (a criar)
# Roda diariamente via cron na VPS
docker compose exec -T postgres pg_dump -U postgres -Fc connectaiacare \
  | gpg --batch --yes --passphrase-file /root/.secrets/backup.key -c \
  > /backups/connectaiacare_$(date +%Y%m%d).dump.gpg
rclone copy /backups/ b2:connectaiacare-backups/
find /backups/ -mtime +7 -delete
```

**Retenção**:
- Local (VPS): 7 dias
- Remote (Backblaze B2): 30 dias
- Cold (mensal): 1 ano
- Testar restore MENSALMENTE (backup que nunca foi testado = não é backup)

### Disaster recovery
- RTO (Recovery Time Objective): 4h
- RPO (Recovery Point Objective): 24h (daily backup)
- Procedimento: nova VPS → restore `.dump.gpg` → DNS update → webhook Evolution repointing

---

## 7. Observabilidade

### Estado atual
- Logs: stdout → Docker → journald
- Métricas: nenhuma
- Alertas: nenhum
- Tracing: nenhum

### Roadmap (P1)
- **Logs centralizados**: Grafana Loki (já rodando na ConnectaIA?)
- **Métricas**: Prometheus + Grafana
- **Alertas**: ntfy.sh ou PagerDuty para incidents
- **Uptime externo**: Uptime Kuma ou BetterStack apontando para `/health`

### Métricas essenciais a expor (quando implementar Prometheus)
- `connectaiacare_webhook_requests_total{status="..."}`
- `connectaiacare_pipeline_duration_seconds_bucket`
- `connectaiacare_classification_total{level="..."}`
- `connectaiacare_llm_tokens_total{model="..."}`
- `connectaiacare_voice_biometrics_score_bucket{method="..."}`
- `connectaiacare_db_connections_current`

---

## 8. Ambientes

### Hoje
| Ambiente | Status | URL |
|----------|--------|-----|
| **Local dev** | ✅ quickstart.sh | `http://localhost:5055` + `:3030` |
| **Demo/Prod** | Configurando | `demo.connectaiacare.com` + `app.connectaiacare.com` |

### Roadmap
| Ambiente | Quando | URL |
|----------|--------|-----|
| **Staging** | Pós-MVP | `staging.connectaiacare.com` (VPS Contabo como na ConnectaIA) |
| **CI/CD** | P2 | GitHub Actions rodando testes + deploy auto |

---

## 9. Fluxo de Release

### Versioning
- Semver informal: `v0.1.0-mvp` → `v0.2.0-piloto` → `v1.0.0-ga`
- Tags Git marcam releases significativas

### Branch strategy
- `main` → sempre deployável
- Features em branch próprio → PR → review → merge
- **Não** temos staging branch (muito cedo)

### Changelog
- Ver `docs/CHANGELOG.md` (a criar na primeira release com usuário externo)

---

## 10. Runbook mínimo

### Como iniciar tudo (VPS)
```bash
ssh root@72.60.242.245
cd /root/connectaiacare
docker compose up -d
```

### Como ver o que está rodando
```bash
docker compose ps
docker compose logs --tail 50 api
```

### Como reiniciar só um serviço
```bash
docker compose restart api
# ou com rebuild:
docker compose up -d --build api
```

### Como investigar um relato específico
```bash
docker compose exec postgres psql -U postgres -d connectaiacare
> SELECT * FROM aia_health_reports WHERE id = '<uuid>';
> \x
> SELECT analysis FROM aia_health_reports WHERE id = '<uuid>';
```

### Como ver logs de um evento específico
```bash
docker compose logs api | grep "<phone-number-or-uuid>"
```

### Como parar tudo preservando dados
```bash
docker compose down
# Volumes permanecem. Para apagar tudo:
# docker compose down -v  ← DESTRUTIVO
```
