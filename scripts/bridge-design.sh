#!/usr/bin/env bash
#
# bridge-design.sh — Sincronização Design ↔ Coder via main
#
# O ambiente do Opus Design escreve arquivos mas não faz git push.
# Este script:
#   1. Copia arquivos do worktree do Design pro worktree principal
#   2. Commita + pusha pra origin/main
#   3. Design faz git pull e vê os artefatos do Coder
#
# Uso:
#   # Define o path do Design uma vez (~/.bashrc ou ~/.zshrc):
#   export DESIGN_WORKTREE="$HOME/caminho-do-design"
#
#   # Depois, toda vez que Design publicar:
#   bash scripts/bridge-design.sh
#
#   # Ou com path explícito:
#   bash scripts/bridge-design.sh ~/design-sandbox
#
# O que o script copia (ambas direções):
#   - exploracoes/html/*.html
#   - exploracoes/html/*.handoff.md
#   - exploracoes/mocks/*.ts
#
# Observação: script é idempotente — se nada mudou, nada é commitado.

set -euo pipefail

# ═══════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════

CODER_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESIGN_WORKTREE="${1:-${DESIGN_WORKTREE:-}}"

if [ -z "$DESIGN_WORKTREE" ]; then
    cat <<'ERR' >&2
❌ DESIGN_WORKTREE não configurado.

Passa como argumento:
    bash scripts/bridge-design.sh /caminho/pro/worktree/do/design

Ou define env var:
    export DESIGN_WORKTREE=/caminho/pro/worktree/do/design
    bash scripts/bridge-design.sh
ERR
    exit 1
fi

if [ ! -d "$DESIGN_WORKTREE" ]; then
    echo "❌ Worktree do Design não existe: $DESIGN_WORKTREE" >&2
    exit 1
fi

# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

log() {
    printf "\033[0;36m[bridge]\033[0m %s\n" "$*"
}

sync_dir() {
    local from="$1"
    local to="$2"
    local pattern="$3"
    local label="$4"

    mkdir -p "$to"
    local changed=0

    shopt -s nullglob
    for file in "$from"/$pattern; do
        local basename
        basename="$(basename "$file")"
        local dest="$to/$basename"
        if [ ! -f "$dest" ] || ! cmp -s "$file" "$dest"; then
            cp "$file" "$dest"
            log "  📝 $label/$basename"
            changed=$((changed + 1))
        fi
    done
    shopt -u nullglob

    return $changed
}

# ═══════════════════════════════════════════════════════════════════
# 1. Design → Coder (pull artefatos do Design)
# ═══════════════════════════════════════════════════════════════════

log "🎨 Design → Coder (lendo artefatos do Design em $DESIGN_WORKTREE)"

cd "$CODER_REPO"

changed_total=0

set +e
sync_dir \
    "$DESIGN_WORKTREE/exploracoes/html" \
    "$CODER_REPO/exploracoes/html" \
    "*.html" \
    "html"
changed_total=$((changed_total + $?))

sync_dir \
    "$DESIGN_WORKTREE/exploracoes/html" \
    "$CODER_REPO/exploracoes/html" \
    "*.handoff.md" \
    "handoff"
changed_total=$((changed_total + $?))

# Se Design criar tokens/CSS novos
sync_dir \
    "$DESIGN_WORKTREE/exploracoes/css" \
    "$CODER_REPO/exploracoes/css" \
    "*.css" \
    "css"
changed_total=$((changed_total + $?))
set -e

if [ "$changed_total" -eq 0 ]; then
    log "  ✓ Nada novo do Design."
else
    log "  ✓ $changed_total arquivo(s) copiado(s)."
fi

# ═══════════════════════════════════════════════════════════════════
# 2. Commit + push (se houver mudança)
# ═══════════════════════════════════════════════════════════════════

if ! git diff --quiet exploracoes/ 2>/dev/null || \
   [ -n "$(git ls-files --others --exclude-standard exploracoes/)" ]; then

    log "📦 Commitando + pushing..."
    git add exploracoes/

    # Detecta quais arquivos foram afetados pra montar mensagem útil
    changed_files=$(git diff --cached --name-only | grep "^exploracoes/" | head -5)

    git commit -m "handoff(design→coder): sync artefatos do worktree do Design

Arquivos afetados:
$changed_files

Sync automatizado via scripts/bridge-design.sh.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"

    git push origin main
    log "  ✓ Commit + push feitos."
else
    log "  ✓ Sem mudanças a commitar."
fi

# ═══════════════════════════════════════════════════════════════════
# 3. Coder → Design (copia docs + mocks pro Design ler)
# ═══════════════════════════════════════════════════════════════════

log "💻 Coder → Design (disponibilizando docs + mocks)"

mkdir -p "$DESIGN_WORKTREE/docs" "$DESIGN_WORKTREE/exploracoes/mocks"

# Docs relevantes pro Design
docs_to_sync=(
    "docs/PITCH_TECH_SLIDES.md"
    "docs/PITCH_TECH_READINESS.md"
    "docs/PITCH_DECK.md"
    "docs/DESIGN_BRIEF.md"
    "docs/ONE_PAGER.md"
    "docs/adr/027-memoria-safety-canais-sofia.md"
)

for doc in "${docs_to_sync[@]}"; do
    if [ -f "$CODER_REPO/$doc" ]; then
        mkdir -p "$(dirname "$DESIGN_WORKTREE/$doc")"
        cp "$CODER_REPO/$doc" "$DESIGN_WORKTREE/$doc"
        log "  📄 $doc"
    fi
done

# Mocks canônicos
if [ -f "$CODER_REPO/exploracoes/mocks/patients.ts" ]; then
    cp "$CODER_REPO/exploracoes/mocks/patients.ts" \
       "$DESIGN_WORKTREE/exploracoes/mocks/patients.ts"
    log "  📦 exploracoes/mocks/patients.ts"
fi

log "✅ Bridge sync completo."
log ""
log "Próximos passos:"
log "  No worktree do Design: git pull (se for git worktree) ou apenas ler files."
log "  No worktree do Coder: já commitado + pushado."
