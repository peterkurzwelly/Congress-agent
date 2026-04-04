"""Layered ticker resolution: local dict -> SEC EDGAR -> fuzzy match -> Claude."""

import logging
import re

import httpx

from congress_trades.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Layer 1: Local dictionary of common tickers in Congress filings
# ---------------------------------------------------------------------------

COMMON_TICKERS: dict[str, str] = {
    # Mega-cap tech
    "AAPL": "Apple Inc",
    "MSFT": "Microsoft Corporation",
    "GOOGL": "Alphabet Inc",
    "GOOG": "Alphabet Inc Class C",
    "AMZN": "Amazon.com Inc",
    "META": "Meta Platforms Inc",
    "NVDA": "NVIDIA Corporation",
    "TSLA": "Tesla Inc",
    "AVGO": "Broadcom Inc",
    "ORCL": "Oracle Corporation",
    "CRM": "Salesforce Inc",
    "ADBE": "Adobe Inc",
    "CSCO": "Cisco Systems Inc",
    "AMD": "Advanced Micro Devices Inc",
    "INTC": "Intel Corporation",
    "QCOM": "Qualcomm Inc",
    "IBM": "International Business Machines",
    "TXN": "Texas Instruments Inc",
    "NOW": "ServiceNow Inc",
    "INTU": "Intuit Inc",
    "AMAT": "Applied Materials Inc",
    "MU": "Micron Technology Inc",
    "PANW": "Palo Alto Networks Inc",
    "SNPS": "Synopsys Inc",
    "CDNS": "Cadence Design Systems Inc",
    "KLAC": "KLA Corporation",
    "LRCX": "Lam Research Corporation",
    "MRVL": "Marvell Technology Inc",
    "NXPI": "NXP Semiconductors NV",
    "ON": "ON Semiconductor Corporation",
    "STX": "Seagate Technology Holdings",
    "WDC": "Western Digital Corporation",
    "HPQ": "HP Inc",
    "HPE": "Hewlett Packard Enterprise",
    "DELL": "Dell Technologies Inc",
    "ACN": "Accenture PLC",
    "UBER": "Uber Technologies Inc",
    "LYFT": "Lyft Inc",
    "SNAP": "Snap Inc",
    "PINS": "Pinterest Inc",
    "TWTR": "Twitter Inc",
    "RBLX": "Roblox Corporation",
    "U": "Unity Software Inc",
    "ZM": "Zoom Video Communications Inc",
    "DOCU": "DocuSign Inc",
    "WDAY": "Workday Inc",
    "TEAM": "Atlassian Corporation",
    "OKTA": "Okta Inc",
    "DDOG": "Datadog Inc",
    "SNOW": "Snowflake Inc",
    "PLTR": "Palantir Technologies Inc",
    "NET": "Cloudflare Inc",
    "CRWD": "CrowdStrike Holdings Inc",
    "ZS": "Zscaler Inc",
    "MDB": "MongoDB Inc",
    "MNDY": "Monday.com Ltd",
    "HCP": "HashiCorp Inc",
    "SHOP": "Shopify Inc",
    "SQ": "Block Inc",
    "COIN": "Coinbase Global Inc",
    "HOOD": "Robinhood Markets Inc",
    "SOFI": "SoFi Technologies Inc",
    "APP": "AppLovin Corporation",
    "TTD": "The Trade Desk Inc",
    # Finance
    "JPM": "JPMorgan Chase & Co",
    "BAC": "Bank of America Corporation",
    "WFC": "Wells Fargo & Company",
    "GS": "Goldman Sachs Group Inc",
    "MS": "Morgan Stanley",
    "C": "Citigroup Inc",
    "BLK": "BlackRock Inc",
    "SCHW": "Charles Schwab Corporation",
    "AXP": "American Express Company",
    "V": "Visa Inc",
    "MA": "Mastercard Inc",
    "PYPL": "PayPal Holdings Inc",
    "USB": "US Bancorp",
    "PNC": "PNC Financial Services Group Inc",
    "TFC": "Truist Financial Corporation",
    "COF": "Capital One Financial Corporation",
    "DFS": "Discover Financial Services",
    "AIG": "American International Group Inc",
    "MET": "MetLife Inc",
    "PRU": "Prudential Financial Inc",
    "AFL": "Aflac Inc",
    "ALL": "Allstate Corporation",
    "CB": "Chubb Limited",
    "MMC": "Marsh & McLennan Companies Inc",
    "SPGI": "S&P Global Inc",
    "MCO": "Moody's Corporation",
    "ICE": "Intercontinental Exchange Inc",
    "CME": "CME Group Inc",
    "NDAQ": "Nasdaq Inc",
    "BX": "Blackstone Inc",
    "KKR": "KKR & Co Inc",
    "APO": "Apollo Global Management Inc",
    "ARES": "Ares Management Corporation",
    "RJF": "Raymond James Financial Inc",
    "LPLA": "LPL Financial Holdings Inc",
    "MKTX": "MarketAxess Holdings Inc",
    "BRK-B": "Berkshire Hathaway Inc",
    "BRK-A": "Berkshire Hathaway Inc Class A",
    # Healthcare / Pharma
    "JNJ": "Johnson & Johnson",
    "UNH": "UnitedHealth Group Inc",
    "PFE": "Pfizer Inc",
    "ABBV": "AbbVie Inc",
    "LLY": "Eli Lilly and Company",
    "MRK": "Merck & Co Inc",
    "TMO": "Thermo Fisher Scientific Inc",
    "ABT": "Abbott Laboratories",
    "BMY": "Bristol-Myers Squibb Company",
    "AMGN": "Amgen Inc",
    "GILD": "Gilead Sciences Inc",
    "ISRG": "Intuitive Surgical Inc",
    "MRNA": "Moderna Inc",
    "REGN": "Regeneron Pharmaceuticals Inc",
    "VRTX": "Vertex Pharmaceuticals Inc",
    "BIIB": "Biogen Inc",
    "ILMN": "Illumina Inc",
    "IDXX": "IDEXX Laboratories Inc",
    "EW": "Edwards Lifesciences Corporation",
    "SYK": "Stryker Corporation",
    "MDT": "Medtronic PLC",
    "BSX": "Boston Scientific Corporation",
    "ZBH": "Zimmer Biomet Holdings Inc",
    "BAX": "Baxter International Inc",
    "BDX": "Becton Dickinson and Company",
    "DHR": "Danaher Corporation",
    "IQV": "IQVIA Holdings Inc",
    "CNC": "Centene Corporation",
    "HUM": "Humana Inc",
    "CVS": "CVS Health Corporation",
    "CI": "Cigna Group",
    "MCK": "McKesson Corporation",
    "ABC": "AmerisourceBergen Corporation",
    "CAH": "Cardinal Health Inc",
    "NVO": "Novo Nordisk AS",
    "BNTX": "BioNTech SE",
    "AZN": "AstraZeneca PLC",
    "GSK": "GSK PLC",
    "SNY": "Sanofi SA",
    "NVS": "Novartis AG",
    "RHHBY": "Roche Holding AG",
    # Defense / Aerospace
    "LMT": "Lockheed Martin Corporation",
    "RTX": "RTX Corporation",
    "BA": "Boeing Company",
    "NOC": "Northrop Grumman Corporation",
    "GD": "General Dynamics Corporation",
    "LHX": "L3Harris Technologies Inc",
    "HII": "Huntington Ingalls Industries Inc",
    "TDG": "TransDigm Group Inc",
    "LDOS": "Leidos Holdings Inc",
    "BAH": "Booz Allen Hamilton Holding Corporation",
    "CACI": "CACI International Inc",
    "SAIC": "Science Applications International Corporation",
    "DRS": "Leonardo DRS Inc",
    "AXON": "Axon Enterprise Inc",
    "KTOS": "Kratos Defense & Security Solutions Inc",
    "BAESY": "BAE Systems PLC",
    "EADSY": "Airbus SE",
    "TXT": "Textron Inc",
    "HEI": "HEICO Corporation",
    "SPR": "Spirit AeroSystems Holdings Inc",
    # Energy
    "XOM": "Exxon Mobil Corporation",
    "CVX": "Chevron Corporation",
    "COP": "ConocoPhillips",
    "SLB": "Schlumberger NV",
    "EOG": "EOG Resources Inc",
    "OXY": "Occidental Petroleum Corporation",
    "PSX": "Phillips 66",
    "VLO": "Valero Energy Corporation",
    "MPC": "Marathon Petroleum Corporation",
    "PXD": "Pioneer Natural Resources Company",
    "DVN": "Devon Energy Corporation",
    "HAL": "Halliburton Company",
    "BKR": "Baker Hughes Company",
    "MRO": "Marathon Oil Corporation",
    "APA": "APA Corporation",
    "FANG": "Diamondback Energy Inc",
    "EQT": "EQT Corporation",
    "AR": "Antero Resources Corporation",
    "RRC": "Range Resources Corporation",
    "KMI": "Kinder Morgan Inc",
    "WMB": "Williams Companies Inc",
    "OKE": "ONEOK Inc",
    "ET": "Energy Transfer LP",
    "EPD": "Enterprise Products Partners LP",
    "ENB": "Enbridge Inc",
    "LNG": "Cheniere Energy Inc",
    "NEP": "NextEra Energy Partners LP",
    "ENPH": "Enphase Energy Inc",
    "FSLR": "First Solar Inc",
    "SEDG": "SolarEdge Technologies Inc",
    "RUN": "Sunrun Inc",
    # Consumer / Retail
    "WMT": "Walmart Inc",
    "COST": "Costco Wholesale Corporation",
    "HD": "Home Depot Inc",
    "PG": "Procter & Gamble Company",
    "KO": "Coca-Cola Company",
    "PEP": "PepsiCo Inc",
    "MCD": "McDonald's Corporation",
    "NKE": "Nike Inc",
    "SBUX": "Starbucks Corporation",
    "TGT": "Target Corporation",
    "DIS": "Walt Disney Company",
    "LOW": "Lowe's Companies Inc",
    "TJX": "TJX Companies Inc",
    "BABA": "Alibaba Group Holding Limited",
    "JD": "JD.com Inc",
    "EBAY": "eBay Inc",
    "ETSY": "Etsy Inc",
    "W": "Wayfair Inc",
    "CL": "Colgate-Palmolive Company",
    "KMB": "Kimberly-Clark Corporation",
    "CHD": "Church & Dwight Co Inc",
    "EL": "Estee Lauder Companies Inc",
    "ULTA": "Ulta Beauty Inc",
    "LULU": "Lululemon Athletica Inc",
    "VFC": "VF Corporation",
    "HBI": "Hanesbrands Inc",
    "PVH": "PVH Corp",
    "RL": "Ralph Lauren Corporation",
    "TPR": "Tapestry Inc",
    "CPRI": "Capri Holdings Limited",
    "GM": "General Motors Company",
    "F": "Ford Motor Company",
    "STLA": "Stellantis NV",
    "TM": "Toyota Motor Corporation",
    "HMC": "Honda Motor Co Ltd",
    "RACE": "Ferrari NV",
    "CMG": "Chipotle Mexican Grill Inc",
    "YUM": "Yum Brands Inc",
    "QSR": "Restaurant Brands International Inc",
    "DRI": "Darden Restaurants Inc",
    "MGM": "MGM Resorts International",
    "LVS": "Las Vegas Sands Corporation",
    "WYNN": "Wynn Resorts Limited",
    "DKNG": "DraftKings Inc",
    # Industrial / Transport / Infrastructure
    "CAT": "Caterpillar Inc",
    "DE": "Deere & Company",
    "UPS": "United Parcel Service Inc",
    "HON": "Honeywell International Inc",
    "GE": "General Electric Company",
    "GEV": "GE Vernova Inc",
    "MMM": "3M Company",
    "UNP": "Union Pacific Corporation",
    "CSX": "CSX Corporation",
    "NSC": "Norfolk Southern Corporation",
    "FDX": "FedEx Corporation",
    "DAL": "Delta Air Lines Inc",
    "UAL": "United Airlines Holdings Inc",
    "AAL": "American Airlines Group Inc",
    "LUV": "Southwest Airlines Co",
    "ALK": "Alaska Air Group Inc",
    "JBLU": "JetBlue Airways Corporation",
    "CCL": "Carnival Corporation",
    "RCL": "Royal Caribbean Cruises Ltd",
    "NCLH": "Norwegian Cruise Line Holdings Ltd",
    "GWW": "WW Grainger Inc",
    "FAST": "Fastenal Company",
    "ROK": "Rockwell Automation Inc",
    "EMR": "Emerson Electric Co",
    "ETN": "Eaton Corporation PLC",
    "PH": "Parker-Hannifin Corporation",
    "ITW": "Illinois Tool Works Inc",
    "DOV": "Dover Corporation",
    "XYL": "Xylem Inc",
    "IEX": "IDEX Corporation",
    "AME": "AMETEK Inc",
    "FTV": "Fortive Corporation",
    "ROP": "Roper Technologies Inc",
    "VRSK": "Verisk Analytics Inc",
    "CTAS": "Cintas Corporation",
    "RSG": "Republic Services Inc",
    "WM": "Waste Management Inc",
    "J": "Jacobs Solutions Inc",
    "PWR": "Quanta Services Inc",
    "PRIM": "Primoris Services Corporation",
    # Telecom / Media / Entertainment
    "T": "AT&T Inc",
    "VZ": "Verizon Communications Inc",
    "TMUS": "T-Mobile US Inc",
    "CMCSA": "Comcast Corporation",
    "NFLX": "Netflix Inc",
    "CHTR": "Charter Communications Inc",
    "DISH": "DISH Network Corporation",
    "PARA": "Paramount Global",
    "WBD": "Warner Bros Discovery Inc",
    "FOX": "Fox Corporation",
    "FOXA": "Fox Corporation Class A",
    "SIRI": "Sirius XM Holdings Inc",
    "SPOT": "Spotify Technology SA",
    "ROKU": "Roku Inc",
    "IAC": "IAC Inc",
    "MTCH": "Match Group Inc",
    # Real-estate / REITs / Utilities
    "NEE": "NextEra Energy Inc",
    "AMT": "American Tower Corporation",
    "D": "Dominion Energy Inc",
    "SO": "Southern Company",
    "DUK": "Duke Energy Corporation",
    "AEP": "American Electric Power Company Inc",
    "EXC": "Exelon Corporation",
    "XEL": "Xcel Energy Inc",
    "SRE": "Sempra Energy",
    "PCG": "PG&E Corporation",
    "ED": "Consolidated Edison Inc",
    "AWK": "American Water Works Company Inc",
    "PLD": "Prologis Inc",
    "PSA": "Public Storage",
    "EQIX": "Equinix Inc",
    "DLR": "Digital Realty Trust Inc",
    "WELL": "Welltower Inc",
    "VTR": "Ventas Inc",
    "SPG": "Simon Property Group Inc",
    "O": "Realty Income Corporation",
    "NNN": "National Retail Properties Inc",
    "STAG": "STAG Industrial Inc",
    "ARE": "Alexandria Real Estate Equities Inc",
    "BXP": "Boston Properties Inc",
    "SLG": "SL Green Realty Corp",
    "EQR": "Equity Residential",
    "AVB": "AvalonBay Communities Inc",
    "UDR": "United Dominion Realty Trust Inc",
    "IRM": "Iron Mountain Inc",
    "SBAC": "SBA Communications Corporation",
    "CCI": "Crown Castle Inc",
    # ETFs -- broad market
    "SPY": "SPDR S&P 500 ETF Trust",
    "VOO": "Vanguard S&P 500 ETF",
    "VTI": "Vanguard Total Stock Market ETF",
    "IVV": "iShares Core S&P 500 ETF",
    "QQQ": "Invesco QQQ Trust",
    "IWM": "iShares Russell 2000 ETF",
    "DIA": "SPDR Dow Jones Industrial Average ETF Trust",
    "MDY": "SPDR S&P MidCap 400 ETF Trust",
    "RSP": "Invesco S&P 500 Equal Weight ETF",
    # ETFs -- sector
    "XLF": "Financial Select Sector SPDR Fund",
    "XLE": "Energy Select Sector SPDR Fund",
    "XLK": "Technology Select Sector SPDR Fund",
    "XLV": "Health Care Select Sector SPDR Fund",
    "XLI": "Industrial Select Sector SPDR Fund",
    "XLC": "Communication Services Select Sector SPDR Fund",
    "XLP": "Consumer Staples Select Sector SPDR Fund",
    "XLY": "Consumer Discretionary Select Sector SPDR Fund",
    "XLB": "Materials Select Sector SPDR Fund",
    "XLU": "Utilities Select Sector SPDR Fund",
    "XLRE": "Real Estate Select Sector SPDR Fund",
    # ETFs -- thematic / other
    "ARKK": "ARK Innovation ETF",
    "ARKG": "ARK Genomic Revolution ETF",
    "ARKW": "ARK Next Generation Internet ETF",
    "ARKF": "ARK Fintech Innovation ETF",
    "GLD": "SPDR Gold Shares",
    "IAU": "iShares Gold Trust",
    "SLV": "iShares Silver Trust",
    "GDX": "VanEck Gold Miners ETF",
    "TLT": "iShares 20+ Year Treasury Bond ETF",
    "IEF": "iShares 7-10 Year Treasury Bond ETF",
    "SHY": "iShares 1-3 Year Treasury Bond ETF",
    "HYG": "iShares iBoxx High Yield Corporate Bond ETF",
    "LQD": "iShares iBoxx Investment Grade Corporate Bond ETF",
    "AGG": "iShares Core U.S. Aggregate Bond ETF",
    "BND": "Vanguard Total Bond Market ETF",
    "MUB": "iShares National Muni Bond ETF",
    "EMB": "iShares JP Morgan USD Emerging Markets Bond ETF",
    "VNQ": "Vanguard Real Estate ETF",
    "USO": "United States Oil Fund LP",
    "UNG": "United States Natural Gas Fund LP",
    "PDBC": "Invesco Optimum Yield Diversified Commodity Strategy No K-1 ETF",
    "BITO": "ProShares Bitcoin Strategy ETF",
}

# Reverse map: lowercase company name -> ticker (last write wins for duplicates)
_NAME_TO_TICKER: dict[str, str] = {v.lower(): k for k, v in COMMON_TICKERS.items()}

# Module-level resolution cache (asset_description -> ticker)
_resolve_cache: dict[str, str | None] = {}

# ---------------------------------------------------------------------------
# Suffixes stripped before fuzzy / prefix matching
# ---------------------------------------------------------------------------
_COMPANY_SUFFIXES: tuple[str, ...] = (
    " incorporated",
    " corporation",
    " company",
    " limited",
    " holdings",
    " group",
    " technologies",
    " technology",
    " international",
    " enterprises",
    " solutions",
    " services",
    " systems",
    " industries",
    " partners",
    " capital",
    " financial",
    " bancorp",
    " pharma",
    " pharmaceuticals",
    " therapeutics",
    " biosciences",
    " laboratories",
    " healthcare",
    " energy",
    " resources",
    " properties",
    " trust",
    " fund",
    " plc",
    " n.v.",
    " s.a.",
    " a.g.",
    " ag",
    " nv",
    " sa",
    " se",
    " ltd",
    " inc",
    " co",
    ".",
    ",",
)


# ---------------------------------------------------------------------------
# Known ETF tickers set (for classify_asset_type)
# ---------------------------------------------------------------------------
_ETF_TICKERS: frozenset[str] = frozenset(
    ticker
    for ticker, name in COMMON_TICKERS.items()
    if any(
        kw in name.lower()
        for kw in ("etf", "trust", " fund", "spdr", "ishares", "vanguard", "invesco")
    )
)


def _strip_company_suffixes(name: str) -> str:
    """Strip common legal entity suffixes from a company name (lowercased)."""
    result = name.lower().strip()
    changed = True
    while changed:
        changed = False
        for suffix in _COMPANY_SUFFIXES:
            if result.endswith(suffix):
                result = result[: -len(suffix)].strip()
                changed = True
    return result


def _fuzzy_match_company(description: str) -> str | None:
    """Fuzzy-match a company name against COMMON_TICKERS keys.

    Resolution strategy:
    1. Strip common legal suffixes from the description.
    2. Try prefix matching against stripped COMMON_TICKERS keys.
    3. Use thefuzz token_set_ratio for scores > 85 as a fallback.

    Parameters
    ----------
    description : str
        Raw asset description from a congressional filing.

    Returns
    -------
    str | None
        Matched ticker or None if no confident match found.
    """
    try:
        from thefuzz import fuzz  # type: ignore[import-untyped]
    except ImportError:
        logger.debug("thefuzz not installed; skipping fuzzy matching.")
        return None

    stripped_desc = _strip_company_suffixes(description)
    if len(stripped_desc) < 3:
        return None

    # Build a lookup of stripped name -> ticker once and reuse via cache
    stripped_names: dict[str, str] = {}
    for name, ticker in _NAME_TO_TICKER.items():
        key = _strip_company_suffixes(name)
        if key and key not in stripped_names:
            stripped_names[key] = ticker

    # --- Pass 1: exact match after stripping ---
    if stripped_desc in stripped_names:
        return stripped_names[stripped_desc]

    # --- Pass 2: prefix match (description starts with a known stripped name) ---
    best_prefix: str | None = None
    best_prefix_len = 0
    for key, ticker in stripped_names.items():
        if len(key) < 3:
            continue
        if stripped_desc.startswith(key) and len(key) > best_prefix_len:
            best_prefix = ticker
            best_prefix_len = len(key)
    if best_prefix:
        return best_prefix

    # --- Pass 3: thefuzz token_set_ratio ---
    best_ticker: str | None = None
    best_score = 0
    for key, ticker in stripped_names.items():
        if len(key) < 3:
            continue
        score = fuzz.token_set_ratio(stripped_desc, key)
        if score > best_score:
            best_score = score
            best_ticker = ticker

    if best_score >= 85:
        logger.debug(
            "Fuzzy match: %r -> %s (score %d)", description, best_ticker, best_score
        )
        return best_ticker

    return None


# ---------------------------------------------------------------------------
# Asset type classifier
# ---------------------------------------------------------------------------

_MUNI_STATE_KEYWORDS: frozenset[str] = frozenset(
    [
        "alabama",
        "alaska",
        "arizona",
        "arkansas",
        "california",
        "colorado",
        "connecticut",
        "delaware",
        "florida",
        "georgia",
        "hawaii",
        "idaho",
        "illinois",
        "indiana",
        "iowa",
        "kansas",
        "kentucky",
        "louisiana",
        "maine",
        "maryland",
        "massachusetts",
        "michigan",
        "minnesota",
        "mississippi",
        "missouri",
        "montana",
        "nebraska",
        "nevada",
        "new hampshire",
        "new jersey",
        "new mexico",
        "new york",
        "north carolina",
        "north dakota",
        "ohio",
        "oklahoma",
        "oregon",
        "pennsylvania",
        "rhode island",
        "south carolina",
        "south dakota",
        "tennessee",
        "texas",
        "utah",
        "vermont",
        "virginia",
        "washington",
        "west virginia",
        "wisconsin",
        "wyoming",
        "county",
        "city of",
        "school district",
        "municipal",
        "authority",
        "port of",
        "metro",
    ]
)


def classify_asset_type(description: str) -> str:
    """Classify an asset description into a broad asset type category.

    Parameters
    ----------
    description : str
        Raw asset description from a congressional filing.

    Returns
    -------
    str
        One of: "Stock", "ETF", "Municipal Bond", "Corporate Bond",
        "Treasury", "Option", "Cryptocurrency", "Mutual Fund", "REIT", "Other".
    """
    desc = description.strip()
    desc_upper = desc.upper()
    desc_lower = desc.lower()

    # --- Option ---
    if re.search(r"\b(CALL|PUT|OPTION)\b", desc_upper):
        return "Option"

    # --- Cryptocurrency ---
    # Senate filings sometimes mark crypto with [CT] bracket
    if re.search(r"\[CT\]", desc_upper):
        return "Cryptocurrency"
    if re.search(
        r"\b(BITCOIN|ETHEREUM|ETH|BTC|CRYPTO|SOLANA|DOGECOIN|RIPPLE|LITECOIN|XRP)\b",
        desc_upper,
    ):
        return "Cryptocurrency"

    # --- Treasury ---
    if re.search(
        r"\b(US\s*TREASURY|U\.S\.\s*TREASURY|T-BILL|T\s*BILL|TREAS(URY)?|"
        r"TREASURY\s*(BILL|NOTE|BOND|INFL)|TIPS)\b",
        desc_upper,
    ):
        return "Treasury"

    # --- Municipal Bond ---
    # Must have muni-specific suffix keyword AND a state/locality keyword
    has_muni_suffix = bool(
        re.search(r"\b(GO|REV|BDS|BOND|BONDS|G\.O\.|MUNI|MUNICIPAL)\b", desc_upper)
    )
    has_locality = any(kw in desc_lower for kw in _MUNI_STATE_KEYWORDS)
    if has_muni_suffix and has_locality:
        return "Municipal Bond"

    # --- Corporate Bond ---
    if re.search(
        r"(RATE[:/]|COUPON[:/]|MATURES?[:/]|\bNOTE\b|\bNOTES\b|\bDEBENTURE\b"
        r"|\bSENIOR\s+(UNSECURED|SECURED|NOTE)\b|\b\d+\.\d+%\s*(DUE|MATURES?)\b)",
        desc_upper,
    ):
        return "Corporate Bond"

    # --- Mutual Fund ---
    if re.search(
        r"\b(MUTUAL\s*FUND|CLASS\s+[A-Z]\s+SHARES?|LOAD\s+FUND|NO[\s-]LOAD"
        r"|FIDELITY\s+(FUND|CONTRAFUND|MAGELLAN|GROWTH)|VANGUARD\s+(INDEX|ADMIRAL)"
        r"|AMERICAN\s+FUNDS?|T\.\s*ROWE\s+PRICE|PIMCO|BLACKROCK\s+FUND"
        r"|SCHWAB\s+(INDEX|FUND)|DIMENSIONAL\s+FUND)\b",
        desc_upper,
    ):
        return "Mutual Fund"

    # --- REIT ---
    if re.search(
        r"\b(REIT|REAL\s+ESTATE\s+INVESTMENT\s+TRUST)\b",
        desc_upper,
    ):
        return "REIT"

    # --- ETF ---
    # Check known ETF tickers first
    desc_ticker = desc.strip().upper()
    if desc_ticker in _ETF_TICKERS:
        return "ETF"
    # Also check if a parenthetical ticker is an ETF
    paren_match = re.search(r"\(([A-Z]{2,5})\)", desc_upper)
    if paren_match and paren_match.group(1) in _ETF_TICKERS:
        return "ETF"
    # Keyword fallback for ETFs
    if re.search(
        r"\b(ETF|EXCHANGE.TRADED\s*FUND|SPDR|ISHARES|POWERSHARES|INVESCO\s+QQQ"
        r"|VANGUARD\s+ETF|INDEX\s+FUND)\b",
        desc_upper,
    ):
        return "ETF"

    # --- Stock (default) ---
    return "Stock"


def _local_lookup(description: str) -> str | None:
    """Try to match against the local dictionary."""
    desc_lower = description.lower().strip()

    # Direct ticker match (e.g., description is just "AAPL")
    desc_upper = description.strip().upper()
    if desc_upper in COMMON_TICKERS:
        return desc_upper

    # Check if description contains a known ticker in parentheses, e.g. "Apple Inc (AAPL)"
    for ticker in COMMON_TICKERS:
        if f"({ticker})" in description.upper():
            return ticker

    # Substring match against known company names
    for name, ticker in _NAME_TO_TICKER.items():
        if name in desc_lower:
            return ticker
        # Match on core company name without suffixes
        core = (
            name.replace(" inc", "")
            .replace(" corporation", "")
            .replace(" company", "")
            .replace(" & co", "")
            .replace(" nv", "")
            .strip()
        )
        if len(core) > 3 and core in desc_lower:
            return ticker

    return None


async def _sec_edgar_lookup(description: str) -> str | None:
    """Search SEC EDGAR company tickers JSON for a match."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://www.sec.gov/files/company_tickers.json",
                headers={
                    "User-Agent": "CongressTradesBot/1.0 (research@example.com)"
                },
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            desc_lower = description.lower()
            best_match: str | None = None
            best_score = 0

            for _key, entry in data.items():
                title = entry.get("title", "").lower()
                if not title:
                    continue
                # Exact containment in either direction
                if title in desc_lower or desc_lower in title:
                    score = len(title)
                    if score > best_score:
                        best_score = score
                        best_match = entry.get("ticker", "").upper()

            return best_match
    except Exception as exc:
        logger.debug("SEC EDGAR lookup failed: %s", exc)
        return None


async def _claude_fuzzy_match(description: str) -> str | None:
    """Use Claude to extract / guess the ticker from an asset description."""
    if not settings.ANTHROPIC_API_KEY:
        logger.debug("No ANTHROPIC_API_KEY; skipping Claude fuzzy match.")
        return None

    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=50,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "What is the stock ticker symbol for this asset? "
                        "Respond with ONLY the ticker symbol in uppercase, "
                        "or 'UNKNOWN' if you cannot determine it.\n\n"
                        f"Asset description: {description}"
                    ),
                }
            ],
        )
        result = message.content[0].text.strip().upper()
        if result and result != "UNKNOWN" and len(result) <= 10:
            return result
    except Exception as exc:
        logger.warning("Claude fuzzy match failed for %r: %s", description, exc)

    return None


async def resolve_ticker(
    asset_description: str, known_ticker: str | None = None
) -> str | None:
    """Resolve an asset description to a stock ticker using a layered approach.

    Resolution order:
    1. Return known_ticker if already provided and valid.
    2. Local dictionary lookup (exact/substring match against COMMON_TICKERS).
    3. Local fuzzy matching (_fuzzy_match_company) using thefuzz.
    4. SEC EDGAR company tickers JSON (free, no auth).
    5. Claude fuzzy matching fallback.

    Results are cached in a module-level dict.
    """
    # If a valid ticker is already provided, trust it
    if known_ticker and known_ticker.strip():
        ticker = known_ticker.strip().upper()
        _resolve_cache[asset_description] = ticker
        return ticker

    # Check cache
    if asset_description in _resolve_cache:
        return _resolve_cache[asset_description]

    # Layer 1: Local dictionary (exact / substring)
    result = _local_lookup(asset_description)
    if result:
        logger.info("Resolved via local dict: %r -> %s", asset_description, result)
        _resolve_cache[asset_description] = result
        return result

    # Layer 2: Local fuzzy matching (thefuzz, no network call)
    result = _fuzzy_match_company(asset_description)
    if result:
        logger.info(
            "Resolved via fuzzy match: %r -> %s", asset_description, result
        )
        _resolve_cache[asset_description] = result
        return result

    # Layer 3: SEC EDGAR
    result = await _sec_edgar_lookup(asset_description)
    if result:
        logger.info("Resolved via SEC EDGAR: %r -> %s", asset_description, result)
        _resolve_cache[asset_description] = result
        return result

    # Layer 4: Claude fuzzy matching
    result = await _claude_fuzzy_match(asset_description)
    if result:
        logger.info("Resolved via Claude: %r -> %s", asset_description, result)
        _resolve_cache[asset_description] = result
        return result

    logger.warning("Could not resolve ticker for: %r", asset_description)
    _resolve_cache[asset_description] = None
    return None
