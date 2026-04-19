#!/usr/bin/env bash
# Quickstart — sobe tudo em 1 comando (requer Docker + API keys no .env)

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/.."

if [ ! -f "backend/.env" ]; then
    echo "❌ backend/.env não existe. Copie de backend/.env.example e preencha as chaves."
    echo "   cp backend/.env.example backend/.env && nano backend/.env"
    exit 1
fi

echo "==> Subindo containers..."
docker compose up -d --build

echo "==> Aguardando Postgres ficar saudável..."
for i in {1..30}; do
    if docker compose exec -T postgres pg_isready -U postgres >/dev/null 2>&1; then
        break
    fi
    sleep 2
done

echo "==> Rodando migrations (se ainda não rodadas)..."
docker compose exec -T postgres psql -U postgres -d connectaiacare -c "SELECT 1 FROM aia_health_patients LIMIT 1;" >/dev/null 2>&1 || {
    docker compose exec -T postgres psql -U postgres -d connectaiacare < backend/migrations/001_initial_schema.sql
    docker compose exec -T postgres psql -U postgres -d connectaiacare < backend/migrations/002_mock_patients.sql
    docker compose exec -T postgres psql -U postgres -d connectaiacare < backend/migrations/003_voice_biometrics.sql
}

echo "==> Testando API..."
sleep 3
if curl -fsS http://localhost:5055/health | grep -q "ok"; then
    echo "  ✅ Backend OK em http://localhost:5055"
else
    echo "  ⚠️  Backend não respondeu. Verificar: docker compose logs api"
fi

echo ""
echo "======================================"
echo "  ConnectaIACare rodando!"
echo "======================================"
echo "  Backend:  http://localhost:5055"
echo "  Frontend: http://localhost:3030"
echo "  Postgres: localhost:5433"
echo "  Redis:    localhost:6380"
echo ""
echo "  Logs ao vivo:  docker compose logs -f api"
echo "  Parar tudo:    docker compose down"
echo "======================================"
