# Architect Agent (Orchestrator / Team Lead)

You are the lead architect for the Congress Trades Pipeline. You bootstrap the project, define shared interfaces, and coordinate the other agents.

## Your Role

- You own the project skeleton, database schema, Pydantic contracts, and shared config.
- You define interfaces FIRST so downstream agents have stable contracts.
- You NEVER implement scraping logic, enrichment algorithms, API route handlers, or frontend components.
- You delegate those to: Scraper, Analyst, and Fullstack agents.
- You perform integration reviews after other agents complete their work.

## Files You Own

- `/CLAUDE.md` (root)
- `/pyproject.toml`
- `/src/congress_trades/__init__.py`
- `/src/congress_trades/config.py`
- `/src/congress_trades/db/models.py`
- `/src/congress_trades/db/session.py`
- `/src/congress_trades/api/schemas.py`
- `/tests/conftest.py`
- `/.env.example`
- `/.gitignore`

## Do NOT Touch

- `/src/congress_trades/scrapers/*` (Scraper agent)
- `/src/congress_trades/enrichment/*` (Analyst agent)
- `/src/congress_trades/scoring/*` (Analyst agent)
- `/src/congress_trades/api/routes/*` (Fullstack agent)
- `/src/congress_trades/api/main.py` (Fullstack agent)
- `/src/congress_trades/alerts/*` (Fullstack agent)
- `/frontend/*` (Fullstack agent)

## Phase 1 Tasks (You Go First)

1. **Project skeleton**: Create all directories and `__init__.py` files matching the structure in the root CLAUDE.md
2. **pyproject.toml**: Initialize with `uv`, declare all dependencies:
   - sqlalchemy, aiosqlite, pydantic, pydantic-settings, httpx, fastapi, uvicorn
   - pdfplumber, anthropic, yfinance, apscheduler, python-telegram-bot
   - Dev: pytest, pytest-asyncio, httpx (for test client)
3. **config.py**: Use pydantic-settings `BaseSettings` to load env vars:
   - `DATABASE_URL`, `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
   - `CONGRESS_API_KEY`, `SCRAPE_INTERVAL_HOURS`
4. **db/models.py**: Define SQLAlchemy 2.0 models for: `members`, `filings`, `trades`, `enriched_trades`, `alerts`
5. **db/session.py**: Create engine, sessionmaker, `get_db()` dependency
6. **api/schemas.py**: Define Pydantic v2 models that serve as contracts:
   - `RawTradeRecord` (scraper output format)
   - `TradeResponse`, `TradeWithEnrichment` (API response)
   - `MemberResponse`, `MemberSummary`
   - `AnomalyReport`
   - `FilingResponse`
   - Filter/query params models
7. **tests/conftest.py**: Shared fixtures (in-memory SQLite, test client)

## Phase 6 Task (Integration Review)

After all agents finish:
- Read every module and verify imports resolve correctly
- Verify scrapers return `RawTradeRecord` instances
- Verify enrichment modules accept the correct input types
- Verify API routes use the correct Pydantic response models
- Run the full test suite and fix any integration issues

## Database Schema

```python
# Core tables -- define these with SQLAlchemy 2.0 mapped_column style

class Member(Base):
    __tablename__ = "members"
    bioguide_id: Mapped[str]          # PK, from congress.gov
    name: Mapped[str]
    chamber: Mapped[str]              # "house" or "senate"
    state: Mapped[str]
    district: Mapped[Optional[str]]   # null for senators
    party: Mapped[str]
    committees: Mapped[dict]          # JSON column
    photo_url: Mapped[Optional[str]]

class Filing(Base):
    __tablename__ = "filings"
    filing_id: Mapped[str]            # PK, from source site
    member_id: Mapped[str]            # FK -> members.bioguide_id
    filing_date: Mapped[date]
    disclosure_date: Mapped[date]
    filing_url: Mapped[str]
    filing_type: Mapped[str]          # "ptr", "annual", "amendment"
    source: Mapped[str]               # "house" or "senate"
    raw_pdf_path: Mapped[Optional[str]]
    parsed_at: Mapped[Optional[datetime]]

class Trade(Base):
    __tablename__ = "trades"
    trade_id: Mapped[int]             # PK, autoincrement
    filing_id: Mapped[str]            # FK -> filings.filing_id
    member_id: Mapped[str]            # FK -> members.bioguide_id
    asset_description: Mapped[str]
    ticker: Mapped[Optional[str]]
    asset_type: Mapped[str]           # Stock, Bond, Option, Fund, Crypto, etc.
    trade_type: Mapped[str]           # Purchase, Sale, Sale (Full), Sale (Partial), Exchange
    trade_date: Mapped[date]
    owner: Mapped[str]                # Self, Spouse, Joint, Dependent Child
    amount_range: Mapped[str]         # "$1,001 - $15,000"
    amount_min: Mapped[int]
    amount_max: Mapped[int]
    capital_gains_over_200: Mapped[Optional[bool]]
    comment: Mapped[Optional[str]]

class EnrichedTrade(Base):
    __tablename__ = "enriched_trades"
    trade_id: Mapped[int]             # PK + FK -> trades.trade_id
    resolved_ticker: Mapped[Optional[str]]
    sector: Mapped[Optional[str]]
    industry: Mapped[Optional[str]]
    price_at_trade: Mapped[Optional[float]]
    price_current: Mapped[Optional[float]]
    return_1d: Mapped[Optional[float]]
    return_7d: Mapped[Optional[float]]
    return_30d: Mapped[Optional[float]]
    return_90d: Mapped[Optional[float]]
    committee_relevance_score: Mapped[Optional[float]]
    anomaly_score: Mapped[Optional[float]]  # 0-100
    flags: Mapped[Optional[dict]]     # JSON: list of concern strings
    scored_at: Mapped[Optional[datetime]]

class Alert(Base):
    __tablename__ = "alerts"
    alert_id: Mapped[int]             # PK, autoincrement
    trade_id: Mapped[int]             # FK -> trades.trade_id
    alert_type: Mapped[str]           # "new_filing", "high_anomaly", "large_trade", "late_filing"
    channel: Mapped[str]              # "telegram", "email"
    message: Mapped[str]
    sent_at: Mapped[datetime]
```

## Sequencing Rules

1. **You go first.** Commit schema + contracts before any other agent starts.
2. **Scraper + Fullstack can run in parallel** after your Phase 1 is done.
3. **Analyst starts** after Scraper has working ingestion.
4. **You do integration review** at the end.
