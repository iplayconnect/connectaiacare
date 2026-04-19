#!/usr/bin/env bash
# Script de verificação do projeto ConnectaIACare
# Roda checks sem side effects: estrutura, arquivos críticos, sintaxe Python.

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$SCRIPT_DIR/.."

cd "$PROJECT_ROOT"

echo "======================================"
echo "  ConnectaIACare — Verify"
echo "======================================"

# Contadores
OK=0
FAIL=0
WARN=0

check() {
    local desc="$1"
    local cmd="$2"
    if eval "$cmd" >/dev/null 2>&1; then
        echo "  ✅ $desc"
        OK=$((OK + 1))
    else
        echo "  ❌ $desc"
        FAIL=$((FAIL + 1))
    fi
}

warn_if() {
    local desc="$1"
    local cmd="$2"
    if eval "$cmd" >/dev/null 2>&1; then
        echo "  ⚠️  $desc"
        WARN=$((WARN + 1))
    else
        echo "  ✅ $desc"
        OK=$((OK + 1))
    fi
}

echo ""
echo "[1/5] Estrutura de diretórios"
for dir in backend frontend docs scripts infra demo-assets \
           backend/src/services backend/src/handlers backend/src/prompts \
           backend/migrations backend/config frontend/src/app frontend/src/components frontend/src/lib; do
    check "dir exists: $dir" "[ -d '$dir' ]"
done

echo ""
echo "[2/5] Arquivos críticos backend"
for f in backend/app.py \
         backend/Dockerfile \
         backend/requirements.txt \
         backend/.env.example \
         backend/config/settings.py \
         backend/migrations/001_initial_schema.sql \
         backend/migrations/002_mock_patients.sql \
         backend/migrations/003_voice_biometrics.sql \
         backend/src/services/voice_biometrics_service.py \
         backend/src/handlers/pipeline.py \
         backend/src/handlers/routes.py \
         backend/src/services/evolution.py \
         backend/src/services/transcription.py \
         backend/src/services/llm.py \
         backend/src/services/patient_service.py \
         backend/src/services/report_service.py \
         backend/src/services/analysis_service.py \
         backend/src/services/session_manager.py \
         backend/src/services/sofia_voice_client.py \
         backend/src/services/postgres.py \
         backend/src/prompts/patient_extraction.py \
         backend/src/prompts/clinical_analysis.py; do
    check "file exists: $f" "[ -f '$f' ]"
done

echo ""
echo "[3/5] Arquivos críticos frontend"
for f in frontend/package.json \
         frontend/tsconfig.json \
         frontend/next.config.js \
         frontend/tailwind.config.ts \
         frontend/Dockerfile \
         frontend/src/app/layout.tsx \
         frontend/src/app/page.tsx \
         frontend/src/app/globals.css \
         frontend/src/app/reports/page.tsx \
         frontend/src/app/reports/\[id\]/page.tsx \
         frontend/src/app/patients/page.tsx \
         frontend/src/app/patients/\[id\]/page.tsx \
         frontend/src/components/header.tsx \
         frontend/src/components/classification-badge.tsx \
         frontend/src/lib/api.ts \
         frontend/src/lib/utils.ts; do
    check "file exists: $f" "[ -f '$f' ]"
done

echo ""
echo "[4/5] Documentação e materiais"
for f in README.md STATUS.md docker-compose.yml .gitignore \
         docs/DEVELOPMENT.md docs/PITCH_DECK.md docs/ONE_PAGER.md docs/DEMO_SCRIPT.md \
         demo-assets/audio_samples/SCRIPTS.md \
         scripts/init_db.sh; do
    check "file exists: $f" "[ -f '$f' ]"
done

echo ""
echo "[5/5] Sintaxe Python"
if command -v python3 >/dev/null 2>&1; then
    for py in backend/app.py backend/config/settings.py \
              backend/src/handlers/pipeline.py backend/src/handlers/routes.py \
              backend/src/services/*.py backend/src/prompts/*.py \
              backend/src/utils/*.py; do
        if [ -f "$py" ]; then
            check "syntax: $py" "python3 -c 'import ast; ast.parse(open(\"$py\").read())'"
        fi
    done
else
    echo "  ⚠️  python3 não disponível, pulando check de sintaxe"
    WARN=$((WARN + 1))
fi

echo ""
echo "======================================"
echo "  Resultado: ✅ $OK   ❌ $FAIL   ⚠️ $WARN"
echo "======================================"

if [ "$FAIL" -eq 0 ]; then
    echo ""
    echo "🎉 Tudo em ordem! Projeto pronto para próxima fase (npm install + docker compose up)."
    exit 0
else
    echo ""
    echo "⚠️  Alguns checks falharam. Revisar antes de prosseguir."
    exit 1
fi
