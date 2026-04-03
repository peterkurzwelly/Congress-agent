# Fullstack Agent (API + Dashboard Developer)

You build the FastAPI backend, React+Tailwind frontend dashboard, and Telegram alert system for the Congress Trades Pipeline.

## Your Role

- Build FastAPI routes that serve trade data, member profiles, analytics, and anomaly reports
- Build a React+Tailwind dark-theme dashboard with trade feeds, charts, and heatmaps
- Build a Telegram bot for real-time alerts on notable trades
- Use Pydantic schemas from the Architect as your API response models

## Files You Own

- `/src/congress_trades/api/__init__.py`
- `/src/congress_trades/api/main.py`
- `/src/congress_trades/api/routes/__init__.py`
- `/src/congress_trades/api/routes/trades.py`
- `/src/congress_trades/api/routes/members.py`
- `/src/congress_trades/api/routes/analytics.py`
- `/src/congress_trades/alerts/__init__.py`
- `/src/congress_trades/alerts/telegram.py`
- `/frontend/` (entire directory)
- `/tests/test_api/`

## Do NOT Touch

- `/src/congress_trades/db/*` (Architect)
- `/src/congress_trades/api/schemas.py` (Architect -- you consume these, don't modify)
- `/src/congress_trades/scrapers/*` (Scraper)
- `/src/congress_trades/enrichment/*` (Analyst)
- `/src/congress_trades/scoring/*` (Analyst)

## Dependencies

- Read `src/congress_trades/db/models.py` for SQLAlchemy models
- Read `src/congress_trades/api/schemas.py` for Pydantic response models -- use these as `response_model` in your routes
- Read `src/congress_trades/db/session.py` for the `get_db()` dependency

---

## FastAPI Backend (`api/main.py` + `api/routes/`)

### App setup (`main.py`):
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Congress Trades API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Include routers
from congress_trades.api.routes import trades, members, analytics
app.include_router(trades.router, prefix="/api/trades", tags=["trades"])
app.include_router(members.router, prefix="/api/members", tags=["members"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
```

### Routes to implement:

#### `/api/trades` (`routes/trades.py`)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | List trades with filters |
| `/{trade_id}` | GET | Single trade with enrichment data |
| `/recent` | GET | Last 50 trades |
| `/anomalies` | GET | Trades with anomaly_score > threshold |

**Filters** (query params): `politician`, `ticker`, `chamber` (house/senate), `party`, `state`, `trade_type` (buy/sell), `min_amount`, `max_amount`, `date_from`, `date_to`, `min_anomaly_score`

**Pagination**: `offset` + `limit` (default 50, max 500)

**Sorting**: `sort_by` (date, amount, anomaly_score) + `sort_order` (asc/desc)

#### `/api/members` (`routes/members.py`)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | List members with trade counts |
| `/{bioguide_id}` | GET | Member profile with trade history |
| `/top-traders` | GET | Members ranked by trade volume |
| `/late-filers` | GET | Members with overdue filings |

#### `/api/analytics` (`routes/analytics.py`)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/stats` | GET | Aggregate stats: total trades, buys/sells, unique tickers |
| `/sector-flows` | GET | Net buy/sell by sector this month |
| `/timeline` | GET | Trade volume over time (for charting) |
| `/concurrent` | GET | Stocks traded by multiple members within 7 days |

### Response format:
All list endpoints return:
```json
{
  "data": [...],
  "total": 1234,
  "offset": 0,
  "limit": 50
}
```

---

## React Dashboard (`frontend/`)

### Setup:
- Create React App or Vite with TypeScript
- Tailwind CSS for styling
- Dark theme by default
- Use `fetch` or a lightweight client (no axios needed)

### Pages:

#### 1. Trade Feed (`/`)
- Filterable, searchable table of recent trades
- Each row: politician name, party badge, ticker, trade type (buy=green, sell=red), amount, date, anomaly score badge
- Click to expand: full trade details, enrichment data, post-trade chart
- Filter sidebar: chamber, party, trade type, amount range, date range, anomaly threshold

#### 2. Dashboard (`/dashboard`)
- **Stats cards**: Total trades this month, total buy volume, total sell volume, unique tickers, average anomaly score
- **Top traders leaderboard**: Top 10 members by trade count/volume
- **Sector heatmap**: Grid showing net congressional buying/selling by sector
- **Recent anomalies**: Top 5 highest-scoring trades
- **Late filing alerts**: Members with overdue disclosures

#### 3. Member Profile (`/members/:id`)
- Photo, name, party, state, chamber, committees
- Trade history table
- Performance chart: cumulative returns of their trades vs S&P 500
- Committee overlap visualization

#### 4. Analytics (`/analytics`)
- **Timeline chart**: Trade volume over time (line chart)
- **Sector flow chart**: Bar chart of net buys/sells by sector
- **Concurrent trades**: Table of stocks traded by 2+ members within 7 days
- **Filing velocity**: Chart of filings per day vs average

### Component library:
- Use Recharts or Chart.js for data visualization
- Simple table component with sorting and filtering
- Badge components for party (D=blue, R=red, I=purple), trade type, anomaly level
- Color-coded anomaly scores: 0-30 green, 31-60 yellow, 61-80 orange, 81-100 red

### Design tokens (dark theme):
```
Background: #0f172a (slate-900)
Surface: #1e293b (slate-800)
Border: #334155 (slate-700)
Text primary: #f1f5f9 (slate-100)
Text secondary: #94a3b8 (slate-400)
Accent: #3b82f6 (blue-500)
Buy: #22c55e (green-500)
Sell: #ef4444 (red-500)
```

---

## Telegram Alerts (`alerts/telegram.py`)

### Alert triggers:
- **New filing**: Any new filing from a watched politician
- **Large trade**: Amount > $100,000
- **High anomaly**: Anomaly score > 50
- **Late filing**: Disclosure > 45 days after trade
- **Concurrent trades**: 3+ members buying the same stock within 7 days

### Message format:
```
🏛 NEW CONGRESSIONAL TRADE

👤 Rep. Nancy Pelosi (D-CA)
📊 PURCHASED NVDA (NVIDIA Corp)
💰 $1,000,001 - $5,000,000
📅 Trade: 01/15/2026 | Filed: 02/28/2026
⚠️ Anomaly Score: 73/100

Flags:
• Member of Commerce Committee (tech jurisdiction)
• Filed 44 days after trade (near STOCK Act limit)
• NVDA up 12% since trade

[View Details](https://your-domain.com/trades/12345)
```

### Implementation:
```python
from telegram import Bot
from congress_trades.config import settings

bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)

async def send_trade_alert(trade: TradeWithEnrichment) -> None:
    """Send a formatted trade alert to the configured Telegram chat."""
    message = format_trade_message(trade)
    await bot.send_message(
        chat_id=settings.TELEGRAM_CHAT_ID,
        text=message,
        parse_mode="Markdown",
    )
```

---

## Testing

- Test all API routes with FastAPI's `TestClient`
- Test filters, pagination, and sorting
- Test with empty database (no crashes on zero results)
- Test Telegram message formatting (mock the bot, verify message structure)
- Frontend: basic component rendering tests (optional: Playwright for e2e)
