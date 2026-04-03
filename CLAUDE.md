# Congress Trades Pipeline

## Project Overview

A Congressional financial disclosure scraper and analyzer that beats Capitol Trades. Scrapes House Clerk and Senate EFD filings, parses PDFs with AI, enriches trades with market data and committee context, scores anomalies, and serves everything via a dashboard with real-time alerts.

## Agentic Team

This project is built by 4 specialized Claude Code agent roles. Each agent has a CLAUDE.md in `.claude/agents/` defining its domain. Run an agent with:

```bash
claude --agent-file .claude/agents/<role>.md
```

| Role | File | Domain |
|------|------|--------|
| **Architect** | `.claude/agents/architect.md` | Project skeleton, DB schema, Pydantic contracts, integration |
| **Scraper** | `.claude/agents/scraper.md` | House Clerk + Senate EFD scrapers, PDF parsing, scheduling |
| **Analyst** | `.claude/agents/analyst.md` | Ticker resolution, committee mapping, price tracking, anomaly scoring |
| **Fullstack** | `.claude/agents/fullstack.md` | FastAPI API, React dashboard, Telegram alerts |

### Build Sequence

```
Phase 1: Architect -> skeleton, DB schema, Pydantic schemas, config
Phase 2: Scraper + Fullstack in parallel (both depend on Phase 1)
Phase 3: Analyst (depends on scraper output format)
Phase 4: Fullstack builds dashboard (depends on working API)
Phase 5: Alerts + scheduling
Phase 6: Architect integration review
```

## Tech Stack

- **Language:** Python 3.12+
- **Deps:** `uv` (never pip)
- **Database:** SQLite via SQLAlchemy 2.0 ORM (designed for Postgres migration)
- **Validation:** Pydantic v2
- **HTTP:** httpx (async)
- **API:** FastAPI
- **Frontend:** React + Tailwind CSS (dark theme)
- **PDF Parsing:** pdfplumber (structured) + Claude API vision (scanned/handwritten)
- **Market Data:** yfinance
- **Scheduling:** APScheduler
- **Alerts:** Telegram Bot API
- **Testing:** pytest

## Coding Standards

- Type hints on all function signatures
- Absolute imports from `congress_trades` (e.g., `from congress_trades.db.models import Trade`)
- Google Python style guide
- All config via environment variables loaded through `pydantic-settings`
- Every module exposes public API via `__init__.py` re-exports
- Tests in `tests/` mirroring `src/` structure, fixtures in `tests/fixtures/`
- No raw SQL -- use SQLAlchemy ORM exclusively
- Async where possible (httpx, FastAPI, aiosqlite)

## Key Data Sources

| Source | URL | Method |
|--------|-----|--------|
| House Clerk | `disclosures-clerk.house.gov/FinancialDisclosure` | POST form search |
| Senate EFD | `efdsearch.senate.gov` | Session + CSRF + agreement cookie |
| SEC EDGAR | `efts.sec.gov/LATEST/search-index` | Free API for ticker resolution |
| Congress.gov | `api.congress.gov` | Free API for bills, members, committees |
| USAspending.gov | `api.usaspending.gov` | Free API for federal contracts |
| Yahoo Finance | via `yfinance` | Price data |
| unitedstates/congress | GitHub repo | Member metadata, committee assignments |

## Database Schema (Core Tables)

- `members` -- bioguide_id, name, chamber, state, district, party, committees (JSON)
- `filings` -- filing_id, member_id FK, filing_date, disclosure_date, filing_url, filing_type, raw_pdf_path, parsed_at
- `trades` -- trade_id, filing_id FK, member_id FK, asset_description, ticker, trade_type, trade_date, owner, amount_min, amount_max, amount_range, asset_type, capital_gains_over_200, comment
- `enriched_trades` -- trade_id FK, resolved_ticker, sector, industry, price_at_trade, price_current, return_1d, return_7d, return_30d, return_90d, committee_relevance_score, anomaly_score, flags (JSON), scored_at
- `alerts` -- alert_id, trade_id FK, alert_type, channel, message, sent_at
