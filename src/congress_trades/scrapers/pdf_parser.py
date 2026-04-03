"""Two-tier PDF parser for congressional financial disclosure forms.

Tier 1: pdfplumber for machine-readable PDFs (fast, free)
Tier 2: Claude API with vision for scanned/handwritten PDFs (accurate, costs tokens)

The parse_filing() entry point tries pdfplumber first and falls back to Claude
if the structured extraction returns None (low confidence).
"""

import base64
import logging
import re
from datetime import date, datetime
from pathlib import Path

import pdfplumber

from congress_trades.api.schemas import RawTradeRecord
from congress_trades.config import settings

logger = logging.getLogger(__name__)

# Amount range mapping
AMOUNT_RANGES: dict[str, tuple[int, int]] = {
    "$1,001 - $15,000": (1_001, 15_000),
    "$15,001 - $50,000": (15_001, 50_000),
    "$50,001 - $100,000": (50_001, 100_000),
    "$100,001 - $250,000": (100_001, 250_000),
    "$250,001 - $500,000": (250_001, 500_000),
    "$500,001 - $1,000,000": (500_001, 1_000_000),
    "$1,000,001 - $5,000,000": (1_000_001, 5_000_000),
    "$5,000,001 - $25,000,000": (5_000_001, 25_000_000),
    "$25,000,001 - $50,000,000": (25_000_001, 50_000_000),
    "Over $50,000,000": (50_000_001, 100_000_000),
}

# Common transaction type aliases
TX_TYPE_MAP: dict[str, str] = {
    "P": "Purchase",
    "S": "Sale",
    "S (Full)": "Sale (Full)",
    "S (Partial)": "Sale (Partial)",
    "E": "Exchange",
    "purchase": "Purchase",
    "sale": "Sale",
    "sale (full)": "Sale (Full)",
    "sale (partial)": "Sale (Partial)",
    "exchange": "Exchange",
}

# Owner abbreviation mapping (House PTR format)
OWNER_MAP: dict[str, str] = {
    "SP": "Spouse",
    "JT": "Joint",
    "DC": "Dependent Child",
    "Self": "Self",
    "": "Self",
}

# Asset type abbreviation mapping (House PTR bracket codes)
ASSET_TYPE_MAP: dict[str, str] = {
    "ST": "Stock",
    "OP": "Option",
    "EF": "Fund",
    "MF": "Fund",
    "BN": "Bond",
    "GS": "Bond",  # Government Securities
    "OT": "Other",
    "CR": "Crypto",
    "RE": "Real Estate",
}

CLAUDE_EXTRACTION_PROMPT = """\
You are an expert at extracting structured data from US Congressional financial \
disclosure forms (STOCK Act periodic transaction reports).

Analyze the provided PDF image(s) and extract EVERY transaction into the following \
JSON format. Return ONLY a JSON array (no markdown, no explanation).

Each transaction object must have these fields:
{
  "transaction_date": "YYYY-MM-DD",
  "owner": "Self" | "Spouse" | "Joint" | "Dependent Child",
  "asset_description": "Full description of the asset",
  "ticker": "AAPL" or null,
  "asset_type": "Stock" | "Bond" | "Option" | "Fund" | "Crypto" | "Real Estate" | "Other",
  "tx_type": "Purchase" | "Sale" | "Sale (Full)" | "Sale (Partial)" | "Exchange",
  "amount_range": "$1,001 - $15,000",
  "amount_min": 1001,
  "amount_max": 15000,
  "capital_gains_over_200": true | false | null,
  "comment": "any comments or notes" or null
}

Important:
- Extract ALL transactions, even if partially legible
- For tickers, extract the stock symbol if visible (e.g., "AAPL", "MSFT")
- If a ticker is not clear, set it to null
- Use standard amount ranges from the STOCK Act form
- Dates should be in YYYY-MM-DD format
- Owner defaults to "Self" if not specified
- Be precise with transaction types: "Purchase", "Sale", "Sale (Full)", "Sale (Partial)", "Exchange"
- For handwritten forms, do your best to interpret the writing
"""


def _parse_amount(text: str) -> tuple[str, int, int]:
    """Parse amount range text into (display, min, max)."""
    text = text.strip()

    # Check known ranges
    if text in AMOUNT_RANGES:
        low, high = AMOUNT_RANGES[text]
        return text, low, high

    # Try generic pattern
    match = re.match(r"\$?([\d,]+)\s*[-–]\s*\$?([\d,]+)", text)
    if match:
        low = int(match.group(1).replace(",", ""))
        high = int(match.group(2).replace(",", ""))
        return text, low, high

    # Over pattern
    match = re.match(r"[Oo]ver\s*\$?([\d,]+)", text)
    if match:
        low = int(match.group(1).replace(",", ""))
        return text, low, low * 2

    # Try to find any dollar amounts
    amounts = re.findall(r"\$?([\d,]+)", text)
    if len(amounts) >= 2:
        low = int(amounts[0].replace(",", ""))
        high = int(amounts[1].replace(",", ""))
        return text, low, high
    elif len(amounts) == 1:
        val = int(amounts[0].replace(",", ""))
        return text, val, val

    return text, 0, 0


def _parse_date_safe(text: str) -> date:
    """Attempt to parse a date string, falling back to today."""
    text = text.strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%b %d, %Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    # Regex fallback
    match = re.search(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})", text)
    if match:
        m, d, y = match.groups()
        y_int = int(y) if len(y) == 4 else 2000 + int(y)
        return date(y_int, int(m), int(d))
    return date.today()


def _normalize_tx_type(raw: str) -> str:
    """Normalize transaction type text."""
    stripped = raw.strip()
    return TX_TYPE_MAP.get(stripped, TX_TYPE_MAP.get(stripped.lower(), stripped))


def _normalize_owner(raw: str) -> str:
    """Normalize owner abbreviation to full name."""
    stripped = raw.strip()
    return OWNER_MAP.get(stripped, stripped if stripped else "Self")


def _extract_ticker(asset_text: str) -> str | None:
    """Extract ticker symbol from asset description like 'NVIDIA Corp (NVDA) [ST]'."""
    match = re.search(r"\(([A-Z]{1,5})\)", asset_text)
    if match:
        return match.group(1)
    return None


def _extract_asset_type_from_brackets(asset_text: str) -> str:
    """Extract asset type from bracket code like '[ST]', '[OP]', '[GS]'."""
    match = re.search(r"\[([A-Z]{2})\]", asset_text)
    if match:
        code = match.group(1)
        return ASSET_TYPE_MAP.get(code, "Other")
    return "Stock"


def _parse_collapsed_row(cell_text: str) -> RawTradeRecord | None:
    """Parse a House PTR row where all columns collapsed into a single cell.

    These rows look like:
    'SP Rollins, Inc. Common Stock (ROL) P 12/12/2024 01/08/2025 $15,001 -\\n[ST] $50,000\\n...'

    The structure is roughly:
    [Owner] <Asset description with (TICKER) [TYPE]> <TxType> <Date> <NotifDate> <Amount>
    followed by optional filing status lines.
    """
    if not cell_text or not cell_text.strip():
        return None

    # Take only the first meaningful line(s) -- strip filing status lines
    # Filing status lines contain null bytes or start with "F" followed by nulls
    lines = cell_text.split("\n")
    # Keep lines until we hit a filing status or subholding line
    data_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Skip lines with null bytes (filing status, subholding info)
        if "\x00" in stripped:
            continue
        data_lines.append(stripped)

    if not data_lines:
        return None

    # Rejoin the data portion
    data_text = " ".join(data_lines)

    # Extract dates (MM/DD/YYYY)
    date_matches = re.findall(r"(\d{1,2}/\d{1,2}/\d{2,4})", data_text)
    if not date_matches:
        return None

    # Extract amount range
    amount_match = re.search(r"(\$[\d,]+)\s*[-–]\s*(\$[\d,]+)", data_text)
    if not amount_match:
        return None

    amount_text = f"{amount_match.group(1)} - {amount_match.group(2)}"
    amount_range, amount_min, amount_max = _parse_amount(amount_text)

    # Extract transaction type (P, S, E, S (Full), S (Partial)) - single letter before a date
    tx_type = "Purchase"
    tx_match = re.search(
        r"\]\s*(P|S\s*\(Full\)|S\s*\(Partial\)|S|E)\s+\d{1,2}/", data_text
    )
    if not tx_match:
        # Try without bracket prefix
        tx_match = re.search(
            r"\b(P|S\s*\(Full\)|S\s*\(Partial\)|S|E)\s+\d{1,2}/", data_text
        )
    if tx_match:
        tx_type = _normalize_tx_type(tx_match.group(1).strip())

    transaction_date = _parse_date_safe(date_matches[0])

    # Extract owner: first token if it's a known abbreviation
    owner = "Self"
    first_token = data_text.split()[0] if data_text.split() else ""
    if first_token in OWNER_MAP:
        owner = OWNER_MAP[first_token]

    # Extract asset description: everything between owner and tx_type
    # Remove the owner prefix, dates, amounts, and tx type to get asset
    asset_desc = data_text
    # Remove owner prefix
    if first_token in OWNER_MAP:
        asset_desc = asset_desc[len(first_token):].strip()
    # Remove everything from the tx_type letter onwards
    if tx_match:
        asset_desc = asset_desc[:asset_desc.find(tx_match.group(0))].strip()

    # Extract ticker and asset type from the asset description
    ticker = _extract_ticker(asset_desc)
    asset_type = _extract_asset_type_from_brackets(asset_desc)

    if not asset_desc:
        asset_desc = "Unknown Asset"

    # Cap gains
    cap_gains: bool | None = None

    return RawTradeRecord(
        transaction_date=transaction_date,
        owner=owner,
        asset_description=asset_desc[:200],
        ticker=ticker,
        asset_type=asset_type,
        tx_type=tx_type,
        amount_range=amount_range,
        amount_min=amount_min,
        amount_max=amount_max,
        capital_gains_over_200=cap_gains,
        comment=None,
    )


def parse_pdf_structured(pdf_path: str | Path) -> list[RawTradeRecord] | None:
    """Parse a machine-readable PDF using pdfplumber.

    Returns a list of RawTradeRecord if successful, or None if the PDF
    appears to be scanned/handwritten (low confidence extraction).
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        logger.error("PDF not found: %s", pdf_path)
        return None

    try:
        with pdfplumber.open(pdf_path) as pdf:
            records: list[RawTradeRecord] = []
            total_text = ""

            for page in pdf.pages:
                text = page.extract_text() or ""
                total_text += text

                # Try to extract tables from each page
                tables = page.extract_tables()
                for table in tables:
                    records.extend(_parse_table_rows(table))

            # If we got very little text, this is probably a scanned PDF
            if len(total_text.strip()) < 100:
                logger.info(
                    "PDF appears to be scanned (only %d chars extracted): %s",
                    len(total_text.strip()),
                    pdf_path,
                )
                return None

            # If we found tables but no records, try text-based parsing
            if not records:
                records = _parse_text_based(total_text)

            # Return None if we got nothing useful (fall back to Claude)
            if not records:
                logger.info(
                    "pdfplumber found no transactions in %s, will try Claude",
                    pdf_path,
                )
                return None

            logger.info(
                "pdfplumber extracted %d transactions from %s",
                len(records),
                pdf_path,
            )
            return records

    except Exception as exc:
        logger.warning("pdfplumber failed on %s: %s", pdf_path, exc)
        return None


def _is_house_ptr_header(headers: list[str]) -> bool:
    """Check if the table headers match the House PTR format."""
    header_text = " ".join(headers)
    # House PTR headers: ID, Owner, Asset, Transaction Type, Date, Notification Date, Amount, Cap. Gains
    return ("id" in headers and "owner" in header_text and "asset" in header_text) or (
        "asset" in header_text and "transaction" in header_text and "notification" in header_text
    )


def _is_filing_status_row(row: list[str | None]) -> bool:
    """Check if a row is a filing status / subholding info row (not a transaction)."""
    for cell in row:
        if cell and "\x00" in str(cell):
            return True
    # Rows where all cells after [0] are None and cell[0] has no date/amount
    non_null = [c for c in row if c and str(c).strip()]
    if len(non_null) <= 1 and non_null:
        text = str(non_null[0])
        if not re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", text):
            if not re.search(r"\$[\d,]+", text):
                return True
    return False


def _parse_table_rows(table: list[list[str | None]]) -> list[RawTradeRecord]:
    """Parse a pdfplumber-extracted table into RawTradeRecords.

    Handles two formats:
    1. House PTR tables with columns: ID, Owner, Asset, Transaction Type, Date,
       Notification Date, Amount, Cap. Gains > $200?
    2. Generic tables with various column orderings.

    Also handles "collapsed" rows where pdfplumber puts all data into a single cell.
    """
    if not table or len(table) < 2:
        return []

    records: list[RawTradeRecord] = []

    # Normalize headers: join multiline headers and lowercase
    raw_headers = [str(h or "").replace("\n", " ").lower().strip() for h in table[0]]

    # Detect House PTR format
    is_house_ptr = _is_house_ptr_header(raw_headers)

    col_map: dict[str, int] = {}

    if is_house_ptr:
        # House PTR has fixed column order: ID, Owner, Asset, Transaction Type,
        # Date, Notification Date, Amount, Cap. Gains > $200?
        for idx, h in enumerate(raw_headers):
            if h == "id":
                col_map["id"] = idx
            elif "owner" in h:
                col_map["owner"] = idx
            elif "asset" in h:
                col_map["asset"] = idx
            elif "transaction" in h:
                col_map["tx_type"] = idx
            elif h == "date" and "date" not in col_map:
                col_map["date"] = idx
            elif "notification" in h:
                col_map["notif_date"] = idx
            elif "amount" in h:
                col_map["amount"] = idx
            elif "cap" in h or "gain" in h:
                col_map["cap_gains"] = idx
    else:
        # Generic column detection (original logic, improved)
        for idx, h in enumerate(raw_headers):
            if ("date" in h and "transaction" in h) or (
                "trade" in h and "date" in h
            ):
                col_map["date"] = idx
            elif h in ("date",) and "date" not in col_map:
                col_map["date"] = idx
            elif "owner" in h:
                col_map["owner"] = idx
            elif "ticker" in h or "symbol" in h:
                col_map["ticker"] = idx
            elif "asset" in h:
                col_map["asset"] = idx
            elif "type" in h and "asset" in h:
                col_map["asset_type"] = idx
            elif "type" in h and "transaction" not in h and "asset" not in h:
                col_map["tx_type"] = idx
            elif "transaction" in h and "type" in h:
                col_map["tx_type"] = idx
            elif "amount" in h:
                col_map["amount"] = idx
            elif "capital" in h or "gain" in h:
                col_map["cap_gains"] = idx
            elif "comment" in h or "description" in h:
                col_map["comment"] = idx

    # For House PTR, we need at least asset or can fallback to collapsed row parsing
    # For generic, we need date + asset
    if not is_house_ptr and "date" not in col_map and "asset" not in col_map:
        return []

    for row in table[1:]:
        if not row or all(cell is None or str(cell).strip() == "" for cell in row):
            continue

        # Skip filing status / subholding rows
        if _is_filing_status_row(row):
            continue

        try:
            # Check if this is a collapsed row (all data in first cell, rest are None)
            non_null_cells = [(i, str(c).strip()) for i, c in enumerate(row)
                              if c is not None and str(c).strip()]
            all_in_first = (
                len(non_null_cells) == 1
                and non_null_cells[0][0] == 0
                and re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", non_null_cells[0][1])
            )

            if all_in_first:
                # Collapsed row: parse from single cell text
                record = _parse_collapsed_row(non_null_cells[0][1])
                if record:
                    records.append(record)
                continue

            # Normal structured row -- extract by column mapping
            def _get(key: str, default: str = "") -> str:
                idx = col_map.get(key)
                if idx is not None and idx < len(row):
                    val = row[idx]
                    if val is not None:
                        # Collapse internal newlines
                        return str(val).replace("\n", " ").strip()
                return default

            date_text = _get("date")
            if not date_text:
                continue

            owner_raw = _get("owner", "Self")
            asset_desc = _get("asset", "Unknown Asset")
            tx_type_raw = _get("tx_type", "Purchase")
            amount_text = _get("amount", "$1,001 - $15,000")
            cap_gains_text = _get("cap_gains")
            comment = _get("comment") or None

            # For House PTR, extract ticker and asset type from asset description
            ticker = _get("ticker") or _extract_ticker(asset_desc)
            asset_type = _extract_asset_type_from_brackets(asset_desc)

            # Normalize owner
            owner = _normalize_owner(owner_raw)

            tx_type = _normalize_tx_type(tx_type_raw)
            transaction_date = _parse_date_safe(date_text)
            amount_range, amount_min, amount_max = _parse_amount(amount_text)

            capital_gains: bool | None = None
            if cap_gains_text:
                cap_lower = cap_gains_text.lower()
                if cap_lower in ("yes", "y", "true", "x"):
                    capital_gains = True
                elif cap_lower in ("no", "n", "false", ""):
                    capital_gains = False

            if ticker:
                ticker = ticker.strip().strip("-").strip()
                if not ticker or ticker == "--":
                    ticker = None

            records.append(
                RawTradeRecord(
                    transaction_date=transaction_date,
                    owner=owner or "Self",
                    asset_description=asset_desc,
                    ticker=ticker,
                    asset_type=asset_type or "Stock",
                    tx_type=tx_type,
                    amount_range=amount_range,
                    amount_min=amount_min,
                    amount_max=amount_max,
                    capital_gains_over_200=capital_gains,
                    comment=comment,
                )
            )
        except Exception as exc:
            logger.warning("Failed to parse table row: %s", exc)
            continue

    return records


def _parse_text_based(text: str) -> list[RawTradeRecord]:
    """Attempt to parse transactions from raw text when table extraction fails.

    This is a best-effort heuristic parser for text-based PDFs where
    pdfplumber cannot detect table structure. Handles House PTR text format
    where transaction lines contain owner, asset, tx type, dates, and amounts.
    """
    records: list[RawTradeRecord] = []

    # Clean null bytes from text
    text = text.replace("\x00", "")

    # Look for transaction patterns in the text
    date_pattern = re.compile(r"(\d{1,2}/\d{1,2}/\d{2,4})")
    amount_pattern = re.compile(r"(\$[\d,]+\s*[-–]\s*\$[\d,]+|Over\s*\$[\d,]+)")

    # House PTR line pattern: [Owner] <Asset (TICKER) [TYPE]> <P|S|E> <Date> <Date> <Amount>
    house_ptr_pattern = re.compile(
        r"^(?:(SP|JT|DC|Self)\s+)?"  # optional owner
        r"(.+?)\s+"  # asset description (non-greedy)
        r"(P|S\s*\(Full\)|S\s*\(Partial\)|S|E)\s+"  # transaction type
        r"(\d{1,2}/\d{1,2}/\d{2,4})\s+"  # transaction date
        r"(\d{1,2}/\d{1,2}/\d{2,4})\s+"  # notification date
        r"(\$[\d,]+\s*[-–]\s*\$[\d,]+)",  # amount range
        re.MULTILINE,
    )

    # First try the House PTR pattern on the full text
    for match in house_ptr_pattern.finditer(text):
        try:
            owner_raw = match.group(1) or "Self"
            asset_desc = match.group(2).strip()
            tx_type_raw = match.group(3).strip()
            date_text = match.group(4)
            amount_text = match.group(6)

            owner = _normalize_owner(owner_raw)
            ticker = _extract_ticker(asset_desc)
            asset_type = _extract_asset_type_from_brackets(asset_desc)
            tx_type = _normalize_tx_type(tx_type_raw)
            transaction_date = _parse_date_safe(date_text)
            amount_range, amount_min, amount_max = _parse_amount(amount_text)

            records.append(
                RawTradeRecord(
                    transaction_date=transaction_date,
                    owner=owner,
                    asset_description=asset_desc[:200],
                    ticker=ticker,
                    asset_type=asset_type,
                    tx_type=tx_type,
                    amount_range=amount_range,
                    amount_min=amount_min,
                    amount_max=amount_max,
                )
            )
        except Exception as exc:
            logger.debug("House PTR text parse failed: %s", exc)

    if records:
        return records

    # Fallback: generic line-by-line parsing
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Skip lines with null bytes or that are clearly not transactions
        if not line or len(line) < 10:
            i += 1
            continue

        date_match = date_pattern.search(line)
        amount_match = amount_pattern.search(line)

        # Also check next few lines for amount if not on same line
        if date_match and not amount_match:
            for j in range(1, min(4, len(lines) - i)):
                next_line = lines[i + j].strip()
                amount_match = amount_pattern.search(next_line)
                if amount_match:
                    line = line + " " + " ".join(
                        lines[i + k].strip() for k in range(1, j + 1)
                    )
                    break

        if date_match and amount_match:
            try:
                transaction_date = _parse_date_safe(date_match.group(1))
                amount_range, amount_min, amount_max = _parse_amount(
                    amount_match.group(1)
                )

                # Extract ticker from parentheses (not just any uppercase word)
                ticker = _extract_ticker(line)

                # Extract asset type from brackets
                asset_type = _extract_asset_type_from_brackets(line)

                # Detect owner
                owner = "Self"
                owner_match = re.match(r"^(SP|JT|DC)\s+", line)
                if owner_match:
                    owner = _normalize_owner(owner_match.group(1))

                # Determine transaction type
                tx_type = "Purchase"
                # Look for single-letter tx type before a date
                tx_match = re.search(
                    r"\b(P|S\s*\(Full\)|S\s*\(Partial\)|S|E)\s+\d{1,2}/",
                    line,
                )
                if tx_match:
                    tx_type = _normalize_tx_type(tx_match.group(1).strip())
                else:
                    line_lower = line.lower()
                    if "sale (full)" in line_lower:
                        tx_type = "Sale (Full)"
                    elif "sale (partial)" in line_lower:
                        tx_type = "Sale (Partial)"
                    elif "sale" in line_lower:
                        tx_type = "Sale"
                    elif "exchange" in line_lower:
                        tx_type = "Exchange"

                # Build asset description: remove date, amount, tx type
                asset_desc = line
                asset_desc = date_pattern.sub("", asset_desc)
                asset_desc = amount_pattern.sub("", asset_desc)
                # Remove owner prefix
                if owner_match:
                    asset_desc = asset_desc[len(owner_match.group(0)):]
                # Remove single-letter tx type
                asset_desc = re.sub(r"\s+[PSED]\s+", " ", asset_desc)
                asset_desc = asset_desc.strip().strip("-").strip()
                if not asset_desc:
                    asset_desc = "Unknown Asset"

                records.append(
                    RawTradeRecord(
                        transaction_date=transaction_date,
                        owner=owner,
                        asset_description=asset_desc[:200],
                        ticker=ticker,
                        asset_type=asset_type,
                        tx_type=tx_type,
                        amount_range=amount_range,
                        amount_min=amount_min,
                        amount_max=amount_max,
                    )
                )
            except Exception as exc:
                logger.debug("Text-based parse failed for line: %s — %s", line[:60], exc)

        i += 1

    return records


async def parse_pdf_with_claude(pdf_path: str | Path) -> list[RawTradeRecord]:
    """Parse a PDF using Claude's vision capabilities.

    Converts each page to a base64-encoded image and sends it to Claude
    for structured extraction. This handles scanned and handwritten PDFs.

    Always returns a list (possibly empty) -- does not return None.
    """
    import anthropic

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        logger.error("PDF not found: %s", pdf_path)
        return []

    # Read the PDF as base64 for Claude's document/vision API
    pdf_bytes = pdf_path.read_bytes()
    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    logger.info("Sending PDF to Claude for extraction: %s", pdf_path.name)

    try:
        message = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": CLAUDE_EXTRACTION_PROMPT,
                        },
                    ],
                }
            ],
        )
    except Exception as exc:
        logger.error("Claude API call failed: %s", exc)
        return []

    # Extract the JSON from Claude's response
    response_text = message.content[0].text  # type: ignore[union-attr]
    records = _parse_claude_response(response_text)
    logger.info("Claude extracted %d transactions from %s", len(records), pdf_path.name)
    return records


def _parse_claude_response(response_text: str) -> list[RawTradeRecord]:
    """Parse Claude's JSON response into RawTradeRecords."""
    import json

    # Try to extract JSON array from the response
    # Claude might wrap it in markdown code blocks
    text = response_text.strip()

    # Remove markdown code fences if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to find a JSON array in the response
        match = re.search(r"\[[\s\S]*\]", text)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                logger.error("Could not parse Claude response as JSON")
                return []
        else:
            logger.error("No JSON array found in Claude response")
            return []

    if not isinstance(data, list):
        data = [data]

    records: list[RawTradeRecord] = []
    for item in data:
        try:
            # Parse date
            date_str = item.get("transaction_date", "")
            transaction_date = _parse_date_safe(date_str) if date_str else date.today()

            # Parse amount
            amount_text = item.get("amount_range", "$1,001 - $15,000")
            amount_min = item.get("amount_min")
            amount_max = item.get("amount_max")

            if amount_min is None or amount_max is None:
                _, amount_min_parsed, amount_max_parsed = _parse_amount(amount_text)
                amount_min = amount_min or amount_min_parsed
                amount_max = amount_max or amount_max_parsed

            # Parse capital gains
            cap_gains = item.get("capital_gains_over_200")
            if isinstance(cap_gains, str):
                cap_gains = cap_gains.lower() in ("true", "yes", "y")

            record = RawTradeRecord(
                transaction_date=transaction_date,
                owner=item.get("owner", "Self"),
                asset_description=item.get("asset_description", "Unknown Asset"),
                ticker=item.get("ticker"),
                asset_type=item.get("asset_type", "Stock"),
                tx_type=_normalize_tx_type(item.get("tx_type", "Purchase")),
                amount_range=amount_text,
                amount_min=int(amount_min),
                amount_max=int(amount_max),
                capital_gains_over_200=cap_gains if isinstance(cap_gains, bool) else None,
                comment=item.get("comment"),
            )
            records.append(record)
        except Exception as exc:
            logger.warning("Failed to parse Claude response item: %s — %s", item, exc)
            continue

    return records


async def parse_filing(pdf_path: str | Path) -> list[RawTradeRecord]:
    """Parse a congressional financial disclosure PDF.

    Two-tier approach:
    1. Try pdfplumber for machine-readable PDFs (fast, free)
    2. Fall back to Claude vision for scanned/handwritten PDFs

    Parameters
    ----------
    pdf_path : str | Path
        Path to the PDF file.

    Returns
    -------
    list[RawTradeRecord]
        Extracted transaction records. May be empty if nothing could be parsed.
    """
    pdf_path = Path(pdf_path)
    logger.info("Parsing filing: %s", pdf_path)

    # Tier 1: Try pdfplumber
    structured_result = parse_pdf_structured(pdf_path)
    if structured_result is not None:
        return structured_result

    # Tier 2: Fall back to Claude
    logger.info("Falling back to Claude for %s", pdf_path.name)
    return await parse_pdf_with_claude(pdf_path)
