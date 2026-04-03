# Congress Trades Pipeline

A Congressional financial disclosure scraper and analyzer that beats Capitol Trades. Scrapes House Clerk and Senate EFD filings, parses PDFs with AI, enriches trades with market data and committee context, scores anomalies, and serves everything via a dashboard with real-time alerts.

## Quick Start

```bash
# Clone and install
git clone https://github.com/peterkurzwelly/Congress-agent.git
cd Congress-agent
uv sync

# Seed with sample data
uv run python scripts/seed_db.py

# Start the API
uv run uvicorn congress_trades.api.main:app --reload

# Start the frontend (separate terminal)
cd frontend && npm install && npm run dev
```

## Docker

```bash
# Build and run
docker compose up --build

# With scheduled scraper
docker compose --profile with-scraper up --build

# Seed the database
docker compose exec app uv run python scripts/seed_db.py
```

The app will be available at `http://localhost:8000`.

## Pipeline

```bash
# Full pipeline: scrape + parse + enrich
uv run python -m congress_trades.pipeline

# House only
uv run python -m congress_trades.pipeline --house-only

# Senate only
uv run python -m congress_trades.pipeline --senate-only

# Re-enrich existing trades
uv run python -m congress_trades.pipeline --enrich-only

# Backfill historical data
uv run python scripts/backfill.py --years 2023 2024 2025
uv run python scripts/backfill.py --senate --days 180
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /api/trades/` | List trades (filterable, paginated) |
| `GET /api/trades/recent` | Last 50 trades |
| `GET /api/trades/anomalies` | High anomaly score trades |
| `GET /api/trades/{id}` | Single trade with enrichment |
| `GET /api/members/` | List members with trade counts |
| `GET /api/members/top-traders` | Top traders by volume |
| `GET /api/members/late-filers` | STOCK Act violators |
| `GET /api/members/{id}` | Member profile |
| `GET /api/analytics/stats` | Aggregate statistics |
| `GET /api/analytics/sector-flows` | Net buy/sell by sector |
| `GET /api/analytics/timeline` | Trade volume over time |
| `GET /api/analytics/concurrent` | Concurrent member trades |

### Filters (on `/api/trades/`)

`politician`, `ticker`, `chamber`, `party`, `state`, `trade_type`, `asset_type`, `min_amount`, `max_amount`, `date_from`, `date_to`, `min_anomaly_score`, `sort_by`, `sort_order`, `offset`, `limit`

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  House Clerk │     │  Senate EFD  │     │  Claude API  │
│   Scraper    │     │   Scraper    │     │  (PDF Parse) │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       └────────────┬───────┘────────────────────┘
                    │
              ┌─────▼─────┐
              │  Pipeline  │  scrape → parse → store
              └─────┬──────┘
                    │
         ┌──────────▼──────────┐
         │    Enrichment       │
         │  ticker · prices    │
         │  committees · bills │
         │  contracts · score  │
         └──────────┬──────────┘
                    │
         ┌──────────▼──────────┐     ┌──────────────┐
         │    FastAPI (17      │────▶│   React      │
         │    endpoints)       │     │  Dashboard   │
         └──────────┬──────────┘     └──────────────┘
                    │
         ┌──────────▼──────────┐
         │   Telegram Alerts   │
         └─────────────────────┘
```

## Anomaly Scoring (0-100)

Each trade is scored on 7 weighted factors:

| Factor | Weight | Description |
|--------|--------|-------------|
| Committee overlap | 25% | Member's committee jurisdiction overlaps with traded company's sector |
| Disclosure delay | 20% | Days between trade and disclosure (>45 = STOCK Act violation) |
| Trade size | 15% | Larger trades are more notable |
| Price movement | 15% | Unusual post-trade price movement |
| Bill timing | 10% | Trade near sponsored/cosponsored legislation |
| Concurrent trades | 10% | Multiple members trading same stock within 7 days |
| Historical pattern | 5% | Deviation from member's typical trading |

## Agentic Team

This project was built by 4 specialized Claude Code agent roles:

```bash
claude --agent-file .claude/agents/architect.md   # DB schema, contracts, integration
claude --agent-file .claude/agents/scraper.md     # Scrapers, PDF parsing, scheduling
claude --agent-file .claude/agents/analyst.md     # Enrichment, scoring, analysis
claude --agent-file .claude/agents/fullstack.md   # API, dashboard, alerts
```

## Configuration

Copy `.env.example` to `.env` and set:

```bash
ANTHROPIC_API_KEY=sk-ant-...    # For PDF parsing (Claude vision)
CONGRESS_API_KEY=...            # Free at api.congress.gov
TELEGRAM_BOT_TOKEN=...         # For alerts
TELEGRAM_CHAT_ID=...           # Target chat for alerts
```

## Testing

```bash
uv run pytest tests/ -v
```

## Data Sources

| Source | URL | Purpose |
|--------|-----|---------|
| House Clerk | disclosures-clerk.house.gov | House financial disclosures |
| Senate EFD | efdsearch.senate.gov | Senate financial disclosures |
| SEC EDGAR | sec.gov | Ticker resolution |
| Congress.gov | api.congress.gov | Bills, members, committees |
| USAspending.gov | api.usaspending.gov | Federal contracts |
| Yahoo Finance | via yfinance | Price data |

## License

MIT
