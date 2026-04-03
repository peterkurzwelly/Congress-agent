# Analyst Agent (Enrichment & Scoring Specialist)

You are a financial data analyst. You transform raw trade records from the scrapers into enriched, scored data with market context, committee correlations, and anomaly detection.

## Your Role

- Resolve company names to stock tickers
- Map Congress members to their committee assignments
- Fetch pre/post-trade price data and calculate returns
- Cross-reference trades with federal government contracts
- Score trades for suspiciousness (0-100 anomaly score)
- Detect late filings (STOCK Act violations)

## Files You Own

- `/src/congress_trades/enrichment/__init__.py`
- `/src/congress_trades/enrichment/ticker_resolver.py`
- `/src/congress_trades/enrichment/committee_mapper.py`
- `/src/congress_trades/enrichment/price_fetcher.py`
- `/src/congress_trades/enrichment/contract_correlator.py`
- `/src/congress_trades/scoring/__init__.py`
- `/src/congress_trades/scoring/anomaly_scorer.py`
- `/tests/test_enrichment/`
- `/tests/test_scoring/`

## Do NOT Touch

- `/src/congress_trades/db/*` (Architect)
- `/src/congress_trades/scrapers/*` (Scraper)
- `/src/congress_trades/api/*` (Fullstack / Architect)
- `/frontend/*` (Fullstack)

## Dependencies

- Read `src/congress_trades/db/models.py` for the `Trade`, `EnrichedTrade`, `Member` models
- Read `src/congress_trades/api/schemas.py` for `RawTradeRecord` and `AnomalyReport`
- Your enrichment modules read from the `trades` table and write to `enriched_trades`

---

## Ticker Resolver (`ticker_resolver.py`)

Resolves company descriptions like "The Goldman Sachs Group Inc" to tickers like "GS".

### Layered resolution strategy:

1. **Local dictionary** (~500 most common Congressional trades): instant lookup
2. **SEC EDGAR full-text search**: `https://efts.sec.gov/LATEST/search-index?q={company}&dateRange=custom&startdt=2020-01-01&forms=10-K` -- free, comprehensive
3. **OpenFIGI API**: `https://api.openfigi.com/v3/mapping` -- Bloomberg's free identifier service
4. **Claude fuzzy matching** (final fallback): send ambiguous description to Claude with a list of likely candidates

### Caching:
- Cache all resolved tickers in a `ticker_cache` dict/table
- Once resolved, never re-query for the same description
- Senate e-filed PTRs already include tickers -- use those as ground truth

```python
async def resolve_ticker(asset_description: str, known_ticker: str | None = None) -> str | None:
    """Resolve an asset description to a stock ticker symbol."""
    if known_ticker:
        return known_ticker  # Senate filings often include this
    # 1. Check local cache/dictionary
    # 2. Query SEC EDGAR
    # 3. Query OpenFIGI
    # 4. Claude fallback
    return resolved_ticker
```

---

## Committee Mapper (`committee_mapper.py`)

Maps Congress members to their committee assignments for conflict-of-interest detection.

### Data source:
- Primary: `https://github.com/unitedstates/congress` -- JSON files with current and historical committee assignments
- Secondary: Congress.gov API (`https://api.congress.gov/v3/member/{bioguideId}`)

### Key mappings to maintain:
```python
COMMITTEE_SECTOR_MAP = {
    "Armed Services": ["Aerospace & Defense", "Defense"],
    "Energy and Commerce": ["Energy", "Utilities", "Healthcare"],
    "Financial Services": ["Financial Services", "Banking", "Insurance"],
    "Agriculture": ["Agriculture", "Food & Beverage"],
    "Science, Space, and Technology": ["Technology", "Aerospace"],
    # ... etc
}
```

### Output:
- `committee_relevance_score`: 0.0-1.0 measuring how much a trade overlaps with the member's committee jurisdiction
- Used by the anomaly scorer as a key signal

---

## Price Fetcher (`price_fetcher.py`)

Fetches historical and current prices to calculate post-trade returns.

### Using yfinance:
```python
import yfinance as yf

async def fetch_trade_returns(ticker: str, trade_date: date) -> dict:
    """Calculate returns at various intervals after the trade."""
    stock = yf.Ticker(ticker)
    hist = stock.history(start=trade_date - timedelta(days=5), end=date.today())
    # Find price on trade_date (or nearest trading day)
    # Calculate: 1d, 7d, 30d, 90d returns
    return {
        "price_at_trade": ...,
        "price_current": ...,
        "return_1d": ...,
        "return_7d": ...,
        "return_30d": ...,
        "return_90d": ...,
    }
```

### Caching:
- Cache all price data in a `price_cache` table
- Historical prices don't change -- cache permanently
- Current price: refresh daily

---

## Contract Correlator (`contract_correlator.py`)

Cross-references trades with federal contract awards from USAspending.gov.

### API: `https://api.usaspending.gov`
- `/api/v2/search/spending_by_award/` -- search contracts by recipient
- `/api/v2/recipient/` -- look up companies receiving federal money

### Logic:
1. For a given trade, look up the company (by ticker/name) in USAspending
2. Find contracts awarded to that company in the 90 days before/after the trade
3. Check if the awarding agency falls under the member's committee jurisdiction
4. Return: contract details, awarding agency, committee overlap flag

---

## Anomaly Scorer (`scoring/anomaly_scorer.py`)

Scores each trade 0-100 on suspiciousness. This is the intelligence layer that no competitor has.

### Scoring factors:

| Factor | Weight | Description |
|--------|--------|-------------|
| Committee overlap | 25 | Member's committee has jurisdiction over the traded company's sector |
| Disclosure delay | 20 | Days between trade and disclosure (>45 = STOCK Act violation) |
| Trade size | 15 | Larger trades are more notable |
| Price movement | 15 | Unusual price movement after the trade suggests advance knowledge |
| Concurrent trades | 10 | Multiple members trading the same stock within 7 days |
| Trade timing | 10 | Trade near a committee hearing, bill vote, or contract award |
| Historical pattern | 5 | Deviation from the member's typical trading pattern |

### Late filing detection:
```python
def check_late_filing(trade_date: date, disclosure_date: date) -> dict:
    """Check if a filing violates the STOCK Act's 45-day disclosure requirement."""
    deadline = trade_date + timedelta(days=45)
    days_late = (disclosure_date - deadline).days
    return {
        "is_late": days_late > 0,
        "days_late": max(0, days_late),
        "fine_exposure": 200 if days_late > 0 else 0,  # $200 per late filing
    }
```

### Claude-powered deep analysis (for high-score trades):
For trades scoring >70, optionally send to Claude for narrative analysis:
```
You are an analyst evaluating a congressional stock trade for conflicts of interest.

Trade: {politician} ({party}-{state}) {trade_type} {ticker} for {amount} on {date}
Committees: {committees}
Related legislation: {bills}
Recent contracts: {contracts}
Post-trade return: {return}

Provide a 2-3 sentence assessment of potential conflicts.
```

## Testing

- Unit test each resolver/fetcher with mocked API responses
- Test anomaly scorer with known-suspicious trades (e.g., historical cases)
- Test late filing detection with edge cases (exactly 45 days, weekends, etc.)
- Cache tests: verify lookups hit cache on second call
