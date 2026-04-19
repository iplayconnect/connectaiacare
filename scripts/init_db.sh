#!/usr/bin/env bash
# Inicializa database ConnectaIACare + roda migrations + seed de mock data

set -euo pipefail

DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-postgres}"
DB_NAME="${DB_NAME:-connectaiacare}"
DB_PASSWORD="${DB_PASSWORD:-postgres}"

export PGPASSWORD="$DB_PASSWORD"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="$SCRIPT_DIR/../backend"

echo "==> Criando database '$DB_NAME' se não existir..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -tc \
    "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" \
    | grep -q 1 || psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres \
    -c "CREATE DATABASE $DB_NAME;"

echo "==> Rodando migration 001 (schema inicial)..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
    -f "$BACKEND_DIR/migrations/001_initial_schema.sql"

echo "==> Carregando mock data (8 pacientes)..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
    -f "$BACKEND_DIR/migrations/002_mock_patients.sql"

echo "==> Rodando migration 003 (voice biometrics + pgvector)..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
    -f "$BACKEND_DIR/migrations/003_voice_biometrics.sql"

echo "==> Verificando..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c \
    "SELECT full_name, nickname, care_unit, room_number FROM aia_health_patients ORDER BY full_name;"

echo "==> OK! Database pronta."
