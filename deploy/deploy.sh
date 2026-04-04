#!/bin/bash
# Congress Trades — one-command production deployment script
# Usage: ./deploy/deploy.sh [--skip-backfill]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.prod.yml"

# ── Colour helpers ─────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
step()    { echo -e "\n${BOLD}▶ $*${RESET}"; }

SKIP_BACKFILL=false
for arg in "$@"; do
    case "$arg" in
        --skip-backfill) SKIP_BACKFILL=true ;;
        --help|-h)
            echo "Usage: $0 [--skip-backfill]"
            echo ""
            echo "  --skip-backfill   Do not run the initial data backfill even if DB is empty"
            exit 0
            ;;
        *)
            error "Unknown argument: $arg"
            exit 1
            ;;
    esac
done

echo -e "${BOLD}"
echo "╔════════════════════════════════════════════╗"
echo "║   Congress Trades — Production Deployment  ║"
echo "╚════════════════════════════════════════════╝"
echo -e "${RESET}"

cd "${REPO_ROOT}"

# ── Step 1: Check prerequisites ────────────────────────────────────────────
step "Checking prerequisites"

if [ ! -f "${REPO_ROOT}/.env" ]; then
    error ".env file not found at ${REPO_ROOT}/.env"
    error "Copy .env.example to .env and fill in your values:"
    error "  cp .env.example .env && nano .env"
    exit 1
fi
success ".env file found"

for cmd in docker docker-compose; do
    if ! command -v "$cmd" &>/dev/null; then
        # docker compose (plugin form) is acceptable as fallback
        if [ "$cmd" = "docker-compose" ] && docker compose version &>/dev/null 2>&1; then
            continue
        fi
        error "Required command not found: $cmd"
        exit 1
    fi
done
success "Docker and docker-compose are available"

# Resolve compose command (standalone vs plugin)
if command -v docker-compose &>/dev/null; then
    COMPOSE_CMD="docker-compose -f ${COMPOSE_FILE}"
else
    COMPOSE_CMD="docker compose -f ${COMPOSE_FILE}"
fi

# ── Step 2: Build Docker images ────────────────────────────────────────────
step "Building Docker images"
info "This may take a few minutes on first run..."
${COMPOSE_CMD} build --pull
success "Images built successfully"

# ── Step 3: Pull any external images (nginx, backup) ──────────────────────
step "Pulling external images"
${COMPOSE_CMD} pull nginx backup --ignore-pull-failures 2>/dev/null || true
success "External images ready"

# ── Step 4: Run database migrations / init ─────────────────────────────────
step "Initialising database"
info "Running init_db to apply schema..."
${COMPOSE_CMD} run --rm \
    -e ENABLE_SCHEDULER=false \
    app \
    uv run python -c "
import asyncio
from congress_trades.db.session import init_db
asyncio.run(init_db())
print('Database initialised.')
"
success "Database schema is up to date"

# ── Step 5: Start services ─────────────────────────────────────────────────
step "Starting services"
${COMPOSE_CMD} up -d app nginx
info "Waiting for app to become healthy..."

MAX_WAIT=60
ELAPSED=0
until ${COMPOSE_CMD} ps app | grep -q "healthy" || [ "$ELAPSED" -ge "$MAX_WAIT" ]; do
    sleep 3
    ELAPSED=$((ELAPSED + 3))
    info "  Waiting... (${ELAPSED}s / ${MAX_WAIT}s)"
done

if [ "$ELAPSED" -ge "$MAX_WAIT" ]; then
    warn "App did not report healthy within ${MAX_WAIT}s — check logs with:"
    warn "  ${COMPOSE_CMD} logs app"
else
    success "App service is healthy"
fi

# ── Step 6: Optional initial backfill ─────────────────────────────────────
if [ "$SKIP_BACKFILL" = false ]; then
    step "Checking whether initial backfill is needed"

    TRADE_COUNT=$(${COMPOSE_CMD} run --rm \
        -e ENABLE_SCHEDULER=false \
        app \
        uv run python -c "
import asyncio, os
os.environ.setdefault('DATABASE_URL', 'sqlite+aiosqlite:////app/data/congress_trades.db')
from congress_trades.db.session import get_session
from congress_trades.db.models import Trade
from sqlalchemy import select, func

async def count():
    async with get_session() as s:
        result = await s.execute(select(func.count()).select_from(Trade))
        print(result.scalar_one())

asyncio.run(count())
" 2>/dev/null | tail -1)

    if [ "${TRADE_COUNT:-0}" -eq 0 ] 2>/dev/null; then
        info "Database is empty — starting initial backfill (this may take a while)..."
        ${COMPOSE_CMD} run --rm \
            --profile backfill \
            -e ENABLE_SCHEDULER=false \
            app \
            uv run python scripts/backfill.py --years 2023 2024 2025 --senate --enrich \
            && success "Initial backfill complete" \
            || warn "Backfill exited with errors — check logs and re-run manually"
    else
        info "Database already contains ${TRADE_COUNT} trades — skipping backfill"
    fi
else
    info "Skipping backfill (--skip-backfill passed)"
fi

# ── Step 7: Status summary ─────────────────────────────────────────────────
step "Deployment status"
${COMPOSE_CMD} ps

echo ""
echo -e "${GREEN}${BOLD}Deployment complete!${RESET}"
echo ""
echo -e "  Dashboard:  ${CYAN}https://your-domain.com${RESET}"
echo -e "  API docs:   ${CYAN}https://your-domain.com/api/docs${RESET}"
echo -e "  Health:     ${CYAN}https://your-domain.com/api/health${RESET}"
echo ""
echo -e "Useful commands:"
echo -e "  Logs:       ${BOLD}${COMPOSE_CMD} logs -f app${RESET}"
echo -e "  Backup:     ${BOLD}${COMPOSE_CMD} --profile maintenance run backup${RESET}"
echo -e "  Stop:       ${BOLD}${COMPOSE_CMD} down${RESET}"
echo ""
