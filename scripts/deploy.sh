#!/usr/bin/env bash
# Deploy incremental (git pull + rebuild + migrations)
# Executar NA VPS após um push no GitHub.
#
# Usage na VPS:
#   cd /root/connectaiacare && bash scripts/deploy.sh [service]
#
# Sem argumento: rebuild api + frontend
# Com argumento: rebuild só o serviço especificado (api | frontend | postgres | redis)

set -euo pipefail

SERVICE="${1:-all}"
PROJECT_DIR="${PROJECT_DIR:-/root/connectaiacare}"
BRANCH="${BRANCH:-main}"

cd "$PROJECT_DIR"

echo "==> Deploy ConnectaIACare $(date +'%Y-%m-%d %H:%M:%S')"
echo "    Service: $SERVICE"

# 1. Pull latest code
echo "==> git pull origin $BRANCH"
git fetch origin
CURRENT_COMMIT=$(git rev-parse HEAD)
git checkout "$BRANCH"
git pull origin "$BRANCH"
NEW_COMMIT=$(git rev-parse HEAD)

if [ "$CURRENT_COMMIT" = "$NEW_COMMIT" ]; then
    echo "==> Nenhum commit novo. Saindo."
    exit 0
fi

echo "==> Commits aplicados:"
git log --oneline "$CURRENT_COMMIT..$NEW_COMMIT"

# 2. Detectar se requirements.txt ou Dockerfile mudou → rebuild obrigatório
FILES_CHANGED=$(git diff --name-only "$CURRENT_COMMIT..$NEW_COMMIT")
REBUILD_API=false
REBUILD_FRONTEND=false
RUN_MIGRATIONS=false

if echo "$FILES_CHANGED" | grep -qE '^backend/(requirements\.txt|Dockerfile|\.env)'; then REBUILD_API=true; fi
if echo "$FILES_CHANGED" | grep -qE '^backend/'; then REBUILD_API=true; fi
if echo "$FILES_CHANGED" | grep -qE '^frontend/(package|Dockerfile)'; then REBUILD_FRONTEND=true; fi
if echo "$FILES_CHANGED" | grep -qE '^frontend/'; then REBUILD_FRONTEND=true; fi
if echo "$FILES_CHANGED" | grep -qE '^backend/migrations/'; then RUN_MIGRATIONS=true; fi

# Override manual do serviço
case "$SERVICE" in
    api) REBUILD_API=true; REBUILD_FRONTEND=false ;;
    frontend) REBUILD_API=false; REBUILD_FRONTEND=true ;;
    all) ;;
esac

# 3. Migrations (antes do rebuild do api)
if [ "$RUN_MIGRATIONS" = "true" ]; then
    echo "==> Rodando migrations novas..."
    for m in $(echo "$FILES_CHANGED" | grep -E '^backend/migrations/' | sort); do
        echo "    → $m"
        docker compose exec -T postgres psql -U postgres -d connectaiacare < "$m" || echo "⚠️ migration $m falhou (talvez já rodada)"
    done
fi

# 4. Rebuild
if [ "$REBUILD_API" = "true" ]; then
    echo "==> Rebuild api..."
    docker compose up -d --build api
fi

if [ "$REBUILD_FRONTEND" = "true" ]; then
    echo "==> Rebuild frontend..."
    docker compose up -d --build frontend
fi

# 5. Health check
echo "==> Health check..."
sleep 3
if docker compose exec -T api curl -fsS http://localhost:5055/health | grep -q "ok"; then
    echo "✅ API saudável"
else
    echo "⚠️  API não respondeu. Verificar: docker compose logs api"
    exit 1
fi

echo ""
echo "✅ Deploy concluído. Commit atual: $NEW_COMMIT"
