#!/usr/bin/env bash
# Setup inicial na VPS (one-time)
# Usage na VPS: bash setup-vps.sh
#
# Pré-requisitos na VPS:
#   - Docker + Docker Compose instalados
#   - Traefik rodando com network 'web' (ou similar) para o roteamento HTTPS
#   - SSH key do deploy configurada para acesso ao repo GitHub privado

set -euo pipefail

REPO_URL="${REPO_URL:-git@github.com:iplayconnect/connectaiacare.git}"
PROJECT_DIR="${PROJECT_DIR:-/root/connectaiacare}"
BRANCH="${BRANCH:-main}"

echo "==> Setup inicial ConnectaIACare VPS"
echo "    Repo:    $REPO_URL"
echo "    Destino: $PROJECT_DIR"
echo "    Branch:  $BRANCH"

if [ -d "$PROJECT_DIR/.git" ]; then
    echo "==> Projeto já existe. Rodando git pull..."
    cd "$PROJECT_DIR"
    git fetch origin
    git checkout "$BRANCH"
    git pull origin "$BRANCH"
else
    echo "==> Clonando repo..."
    git clone -b "$BRANCH" "$REPO_URL" "$PROJECT_DIR"
    cd "$PROJECT_DIR"
fi

# .env — precisa ser preenchido manualmente na VPS antes do primeiro up
if [ ! -f "backend/.env" ]; then
    echo "==> Criando backend/.env a partir do template..."
    cp backend/.env.example backend/.env
    echo ""
    echo "⚠️  IMPORTANTE: edite backend/.env agora e preencha:"
    echo "    - ANTHROPIC_API_KEY"
    echo "    - DEEPGRAM_API_KEY"
    echo "    - EVOLUTION_API_KEY (já temos — da instância v6)"
    echo "    - SOFIA_VOICE_API_URL + SOFIA_VOICE_API_KEY"
    echo ""
    echo "    Depois rode: bash scripts/deploy.sh"
    exit 0
fi

echo "==> .env já configurado. Subindo containers..."
docker compose up -d --build

echo "==> Aguardando Postgres ficar saudável..."
for i in {1..30}; do
    if docker compose exec -T postgres pg_isready -U postgres >/dev/null 2>&1; then
        break
    fi
    sleep 2
done

echo "==> Rodando migrations..."
docker compose exec -T postgres psql -U postgres -d connectaiacare < backend/migrations/001_initial_schema.sql
docker compose exec -T postgres psql -U postgres -d connectaiacare < backend/migrations/002_mock_patients.sql
docker compose exec -T postgres psql -U postgres -d connectaiacare < backend/migrations/003_voice_biometrics.sql

echo "==> Testando health..."
sleep 5
docker compose exec -T api curl -fsS http://localhost:5055/health || echo "⚠️ api não respondeu ainda, verificar logs"

echo ""
echo "======================================"
echo "✅ Setup VPS concluído"
echo "======================================"
echo "  API:       http://localhost:5055 (via Traefik em demo.connectaia.com.br)"
echo "  Frontend:  http://localhost:3030 (via Traefik em care.connectaia.com.br)"
echo ""
echo "  Próximos passos:"
echo "    1. Cloudflare A-records:"
echo "         demo.connectaia.com.br → 72.60.242.245"
echo "         care.connectaia.com.br → 72.60.242.245"
echo "    2. Criar instância connectaiacare no Evolution (chip 5551994548043):"
echo "       curl -X POST \$EVOLUTION_URL/instance/create \\"
echo "         -H 'apikey: \$EVOLUTION_KEY' \\"
echo "         -d '{\"instanceName\":\"connectaiacare\",\"qrcode\":true,\"integration\":\"WHATSAPP-BAILEYS\",\"webhook\":{\"url\":\"https://demo.connectaia.com.br/webhook/whatsapp\",\"enabled\":true,\"events\":[\"MESSAGES_UPSERT\"]}}'"
echo "    3. Escanear QR code no WhatsApp do chip"
echo "    4. Teste end-to-end: enviar áudio para 5551994548043"
echo "======================================"
