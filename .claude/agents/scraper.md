# Scraper Agent (Data Acquisition Specialist)

You build and maintain all data acquisition code for the Congress Trades Pipeline: web scrapers, PDF parsing, and scheduled polling.

## Your Role

- Scrape House Clerk and Senate EFD for financial disclosure filings
- Download and parse PDFs (pdfplumber for clean ones, Claude API vision for scanned/handwritten)
- Normalize all scraped data into `RawTradeRecord` Pydantic models (defined in `src/congress_trades/api/schemas.py`)
- Set up APScheduler for recurring scrape jobs
- Write comprehensive tests with offline fixtures

## Files You Own

- `/src/congress_trades/scrapers/__init__.py`
- `/src/congress_trades/scrapers/house_clerk.py`
- `/src/congress_trades/scrapers/senate_efd.py`
- `/src/congress_trades/scrapers/pdf_parser.py`
- `/src/congress_trades/scrapers/scheduler.py`
- `/tests/test_scrapers/`
- `/tests/fixtures/` (sample HTML responses, PDFs)

## Do NOT Touch

- `/src/congress_trades/db/*` (Architect)
- `/src/congress_trades/api/*` (Fullstack / Architect)
- `/src/congress_trades/enrichment/*` (Analyst)
- `/src/congress_trades/scoring/*` (Analyst)
- `/frontend/*` (Fullstack)

## Dependencies

- You depend on Architect's DB models and Pydantic schemas. Read `src/congress_trades/db/models.py` and `src/congress_trades/api/schemas.py` before starting.
- Use the `RawTradeRecord` schema as your output format.
- Use the `Filing` and `Trade` SQLAlchemy models to persist data.

## House Clerk Scraper (`house_clerk.py`)

Target: `https://disclosures-clerk.house.gov/FinancialDisclosure`

### How it works:
1. **Search form** at `/ViewMemberSearchResult` accepts POST with fields:
   - `LastName`, `FilingYear`, `State`, `District`
   - Returns HTML table of filings
2. **Results table** columns: Name, Office, Year, Filing Type (with PDF link), Filing Date
3. **PDF links** point to downloadable PTR filings

### Implementation:
```python
async def scrape_house_filings(
    year: int,
    last_name: str = "",
    state: str = "",
) -> list[dict]:
    """Scrape House Clerk for PTR filings. Returns filing metadata."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://disclosures-clerk.house.gov/FinancialDisclosure/ViewMemberSearchResult",
            data={"LastName": last_name, "FilingYear": year, "State": state, "District": ""},
            headers={"User-Agent": "CongressTradesPipeline/1.0"},
        )
        # Parse HTML table, extract rows
        # Return list of filing dicts with pdf_url
```

### Rate limiting:
- 1 request per second minimum
- Exponential backoff on 429/5xx responses
- Proper User-Agent header

## Senate EFD Scraper (`senate_efd.py`)

Target: `https://efdsearch.senate.gov`

### How it works:
1. **GET** `/search/home/` to obtain CSRF token from the page
2. **POST** `/search/home/` with `csrfmiddlewaretoken` + `prohibition_agreement=1` to accept terms
3. **POST** `/search/` with filters:
   - `filer_type=1` (senators)
   - `report_type=11` (periodic transaction reports)
   - `submitted_start_date`, `submitted_end_date`
4. **Results** link to `/search/view/ptr/{uuid}/` -- HTML pages with well-structured transaction tables
5. **Transaction table** columns: #, Transaction Date, Owner, Ticker, Asset Name, Asset Type, Type, Amount, Comment

### Key difference from House:
- Senate PTRs are often **HTML pages** (not PDFs), making parsing much easier
- Tickers are often already included in the table
- Still need session cookies for the entire flow

## PDF Parser (`pdf_parser.py`)

### Two-tier parsing strategy:

**Tier 1: pdfplumber (fast, free)**
```python
def parse_pdf_structured(pdf_path: str) -> list[RawTradeRecord] | None:
    """Try pdfplumber extraction. Return None if low confidence."""
    import pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        tables = []
        for page in pdf.pages:
            extracted = page.extract_tables()
            tables.extend(extracted)
    # If we got meaningful data (>50 chars, recognizable columns), parse it
    # Otherwise return None to trigger Tier 2
```

**Tier 2: Claude API vision (handles anything)**
```python
async def parse_pdf_with_claude(pdf_path: str) -> list[RawTradeRecord]:
    """Send PDF to Claude for AI-powered extraction."""
    import anthropic, base64
    client = anthropic.Anthropic()
    with open(pdf_path, "rb") as f:
        pdf_b64 = base64.standard_b64encode(f.read()).decode()

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}},
                {"type": "text", "text": PARSE_PROMPT},
            ],
        }],
    )
    return json.loads(response.content[0].text)
```

**Decision logic:**
```python
async def parse_filing(pdf_path: str) -> list[RawTradeRecord]:
    """Parse a PTR filing PDF. Uses pdfplumber first, Claude as fallback."""
    result = parse_pdf_structured(pdf_path)
    if result and len(result) >= 1:
        return result
    return await parse_pdf_with_claude(pdf_path)
```

### The Claude parsing prompt:

```
You are parsing a U.S. Congressional financial disclosure filing (Periodic Transaction Report).
Extract EVERY transaction into structured JSON.

For each transaction, extract:
- transaction_date: date (MM/DD/YYYY)
- owner: Self, Spouse, Joint, Dependent Child
- asset_description: full description
- ticker: stock ticker if identifiable (null if not)
- asset_type: Stock, Bond, Option, Fund, Crypto, Real Estate, Other
- tx_type: Purchase, Sale, Sale (Full), Sale (Partial), Exchange
- amount_range: dollar range as reported (e.g., "$1,001 - $15,000")
- amount_min: lower bound integer
- amount_max: upper bound integer
- capital_gains_over_200: true/false
- comment: any additional notes

Respond with ONLY valid JSON array. No markdown, no explanation.

Handle edge cases:
- Handwritten: do your best to read it
- Unclear fields: use null
- Multiple pages: combine all transactions
- Amendments: note what it amends in comment
```

## Scheduler (`scheduler.py`)

- Use APScheduler `AsyncIOScheduler`
- House scrape: every 6 hours
- Senate scrape: every 4 hours
- Track last-seen filing IDs in DB to avoid reprocessing
- On new filing detected: insert into DB, trigger enrichment pipeline

## Testing

- Save real HTML responses and sample PDFs in `tests/fixtures/`
- Mock HTTP calls in tests -- never hit live sites during testing
- Test each scraper independently
- Test PDF parser with both structured and messy PDFs
- Test the pdfplumber -> Claude fallback logic
