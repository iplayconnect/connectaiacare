# ConnectaIACare — Fluxo de Deploy

> **Regra de ouro**: Local → git commit → git push → VPS git pull → rebuild.
> **NUNCA editar arquivo direto na VPS.** Quebra o git como fonte canônica.

---

## Fluxo completo

```
┌─────────────┐  git commit   ┌──────────┐   git pull   ┌───────────┐
│  Local (seu │ ────────────▶ │ GitHub   │ ───────────▶ │  VPS      │
│  Mac)       │    + push     │ (main)   │   + rebuild  │ Hostinger │
└─────────────┘               └──────────┘              └───────────┘
     fonte                    fonte canônica            fonte de
   de edição                     do código            estado (runtime)
```

**Regras:**
1. Toda alteração começa no Local.
2. Toda alteração passa pelo GitHub (commit + push).
3. VPS aplica via `git pull` + `docker compose ... up -d --build`.
4. Proibido: rsync Local→VPS, scp, sed na VPS, vi na VPS.

---

## Setup inicial (uma vez só, por VPS)

### Na VPS (Hostinger 72.60.242.245 ou outra)

1. Garantir que a VPS tem:
   - Docker + Docker Compose
   - Traefik rodando com network `web` (ou equivalente) — já existe na Hostinger para ConnectaIA
   - Chave SSH para acesso ao repo GitHub privado (`iplayconnect/connectaiacare`)
     - Opção A: usar a mesma key que acessa `iplayconnect/connectaia`
     - Opção B: gerar nova deploy key específica e adicionar como Deploy Key no repo

2. Clonar:
   ```bash
   cd /root
   git clone -b main git@github.com:iplayconnect/connectaiacare.git
   cd connectaiacare
   ```

3. Configurar `.env`:
   ```bash
   cp backend/.env.example backend/.env
   nano backend/.env
   # Preencher ANTHROPIC_API_KEY, DEEPGRAM_API_KEY, SOFIA_VOICE_API_URL, etc.
   ```

4. Primeira subida:
   ```bash
   bash scripts/setup-vps.sh
   ```
   Isso sobe containers, roda migrations, valida health.

5. DNS (Cloudflare no domínio `connectaia.com.br`):
   - `A` record: `demo.connectaia.com.br` → `72.60.242.245` (Proxy ativo)
   - `A` record: `care.connectaia.com.br` → `72.60.242.245` (Proxy ativo)

6. Traefik (labels já estão no `docker-compose.yml`) cuida de SSL via Let's Encrypt automaticamente.

7. Criar instância dedicada `connectaiacare` no Evolution e conectar chip (ver seção "Instância Evolution API — referência rápida" abaixo).

8. Validar end-to-end: enviar áudio pelo WhatsApp para **+55 51 99454-8043**.

---

## Deploy incremental (dia-a-dia)

### No Local (seu Mac)

```bash
cd "/Users/macnovo/.../Python/ConnectaIACare"
# Fazer alterações, testar local (docker compose up), etc.
git add <arquivos>
git commit -m "feat/fix: descrição clara"
git push origin main
```

### Na VPS

```bash
cd /root/connectaiacare && bash scripts/deploy.sh
```

O script `deploy.sh`:
1. Faz `git fetch` + verifica se há commits novos
2. Detecta o que mudou (backend? frontend? migrations?)
3. Roda migrations novas automaticamente
4. Rebuilda só o container do serviço afetado (otimiza tempo)
5. **Sempre que `api` é rebuilded, `sofia-inbound-worker` e `delivery-worker` também são** (compartilham build context — ver "Pegadinha: workers" abaixo)
6. Valida health

Para rebuild manual de um serviço só:
```bash
bash scripts/deploy.sh api          # api + workers (sempre juntos)
bash scripts/deploy.sh workers      # só os workers (sofia-inbound + delivery)
bash scripts/deploy.sh frontend
bash scripts/deploy.sh sofia        # sofia-service
```

### ⚠️ Pegadinha histórica: workers compartilham imagem com `api`

Os serviços `sofia-inbound-worker` e `delivery-worker` no `docker-compose.yml`
buildam a partir do **mesmo `./backend/Dockerfile`** que o `api`. Mas no Docker
Compose, `--build api` rebuilda **só a imagem do serviço `api`** — workers
ficam com a tag antiga.

**Bug histórico (2026-05-02)**: depois do merge do PR #85 (Phase C v2 — CSM
+ memory layers), `deploy.sh` rebuildou só o `api`. Os 2 workers ficaram
21h com código pre-CSM enquanto `api` já tinha código novo. Resultado: o
fluxo WhatsApp continuava rodando o pipeline antigo (sem CSM, sem
capabilities whitelist, sem prompt caching) sem ninguém perceber.

**Como o `deploy.sh` corrige isso (post-fix 2026-05-02)**: a flag
`REBUILD_WORKERS` é setada automaticamente sempre que `REBUILD_API=true`.
Ou seja, qualquer mudança em `backend/**` agora rebuilda **api + workers**
juntos, sem opção de esquecer.

**Verificar manualmente após deploy** (sanity check):
```bash
docker images --format 'table {{.Repository}}\t{{.CreatedAt}}\t{{.ID}}' \
  | grep connectaiacare
docker inspect connectaiacare-sofia-inbound-worker-2 --format '{{.Image}}'
docker inspect connectaiacare-api --format '{{.Image}}'
```
Os hashes do `api` e dos workers **devem ser próximos no tempo** (mesmo
deploy). Se divergirem por horas, workers ficaram pra trás — rode
`bash scripts/deploy.sh workers` pra corrigir.

---

## Cheatsheet operacional

### Ver logs em tempo real
```bash
docker compose logs -f api
docker compose logs -f --tail 50 frontend
```

### Entrar no container
```bash
docker compose exec api bash
docker compose exec postgres psql -U postgres -d connectaiacare
```

### Rebuild forçado sem pull
```bash
docker compose up -d --build --force-recreate api
```

### Backup do banco
```bash
docker compose exec -T postgres pg_dump -U postgres connectaiacare \
  | gzip > "backup_$(date +%Y%m%d_%H%M%S).sql.gz"
```

### Restore do banco
```bash
gunzip < backup_YYYYMMDD_HHMMSS.sql.gz | docker compose exec -T postgres psql -U postgres -d connectaiacare
```

### Reverter para commit anterior (se deploy quebrou)
```bash
cd /root/connectaiacare
git log --oneline -5         # pega o hash anterior
git reset --hard <hash>      # volta
docker compose up -d --build # rebuild
```

---

## Problemas comuns

| Sintoma | Causa | Fix |
|---------|-------|-----|
| `git pull` pede senha | Chave SSH não adicionada | `ssh-keygen -t ed25519` + adicionar pubkey no GitHub |
| Container fica restart loop | Erro em .env ou dep quebrada | `docker compose logs api` para investigar |
| Migrations falham | pgvector não instalado | `docker compose pull postgres` e recriar |
| Webhook não chega | URL errada no Evolution | `curl evolution.../webhook/find/v6` |
| Traefik não gera SSL | DNS não propagou ou rede Docker errada | `docker network ls` + verificar `web` network |
| Resemblyzer OOM | Torch puxou CUDA que não existe | `pip install torch --index-url https://download.pytorch.org/whl/cpu` |

---

## GitHub Actions (roadmap)

Para automatizar o deploy sem SSH manual:
```yaml
# .github/workflows/deploy.yml (a criar)
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.VPS_HOST }}
          username: root
          key: ${{ secrets.VPS_SSH_KEY }}
          script: |
            cd /root/connectaiacare && bash scripts/deploy.sh
```

---

## Instância Evolution API — referência rápida

**Decisão arquitetural**: ver `docs/adr/013-instancia-evolution-dedicada.md`.
ConnectaIACare tem **instância dedicada** `connectaiacare` com chip próprio
(`5551994548043`). Não reusamos V6 do CRM — isolamento total.

### Criar a instância (one-time, via painel Evolution ou API)

```bash
# Substitua <API_KEY> pela chave master do Evolution
curl -X POST https://evolution.connectaia.com.br/instance/create \
  -H "apikey: <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "instanceName": "connectaiacare",
    "qrcode": true,
    "integration": "WHATSAPP-BAILEYS",
    "webhook": {
      "url": "https://demo.connectaia.com.br/webhook/whatsapp",
      "enabled": true,
      "events": ["MESSAGES_UPSERT"]
    }
  }'
```

Depois escanear o QR code no WhatsApp do chip `+55 51 99454-8043`.

### Ver config atual da instância

```bash
curl -X GET https://evolution.connectaia.com.br/webhook/find/connectaiacare \
  -H "apikey: <API_KEY>"
```

### Atualizar webhook (se domínio mudar no futuro)

```bash
curl -X PUT https://evolution.connectaia.com.br/webhook/set/connectaiacare \
  -H "apikey: <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://demo.connectaia.com.br/webhook/whatsapp",
    "enabled": true,
    "events": ["MESSAGES_UPSERT"]
  }'
```

### Status da conexão (verificar se o chip está conectado)

```bash
curl -X GET https://evolution.connectaia.com.br/instance/connectionState/connectaiacare \
  -H "apikey: <API_KEY>"
```

### Logout / reconectar (se precisar trocar de chip)

```bash
# Desconectar
curl -X DELETE https://evolution.connectaia.com.br/instance/logout/connectaiacare \
  -H "apikey: <API_KEY>"

# Reconectar (gera QR novo)
curl -X GET https://evolution.connectaia.com.br/instance/connect/connectaiacare \
  -H "apikey: <API_KEY>"
```
