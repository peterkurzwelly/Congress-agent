"""Tests for the House Clerk scraper module."""

from datetime import date

from congress_trades.scrapers.house_clerk import (
    _generate_filing_id,
    _parse_date,
    _parse_search_results,
)


SAMPLE_HTML_3_ROWS = """
<html>
<body>
<table class="library-table">
  <tr>
    <th>Name</th><th>Office</th><th>Filing Year</th><th>Filing</th><th>Filing Date</th>
  </tr>
  <tr>
    <td><a href="/public_disc/ptr-pdfs/2026/20012345.pdf">Pelosi, Nancy</a></td>
    <td>CA11</td>
    <td>2026</td>
    <td>Periodic Transaction Report</td>
    <td>01/15/2026</td>
  </tr>
  <tr>
    <td><a href="/public_disc/ptr-pdfs/2026/20012346.pdf">Tuberville, Tommy</a></td>
    <td>AL</td>
    <td>2026</td>
    <td>Periodic Transaction Report</td>
    <td>02/20/2026</td>
  </tr>
  <tr>
    <td><a href="/public_disc/ptr-pdfs/2025/20099999.pdf">Crenshaw, Dan</a></td>
    <td>TX02</td>
    <td>2025</td>
    <td>Annual Report</td>
    <td>03/10/2025</td>
  </tr>
</table>
</body>
</html>
"""


def test_parse_search_results() -> None:
    """HTML table with 3 rows produces 3 filing dicts with correct fields."""
    results = _parse_search_results(SAMPLE_HTML_3_ROWS)

    assert len(results) == 3

    # First row
    assert results[0]["name"] == "Pelosi, Nancy"
    assert results[0]["office"] == "CA11"
    assert results[0]["year"] == 2026
    assert results[0]["filing_type"] == "Periodic Transaction Report"
    assert results[0]["pdf_url"].endswith("/public_disc/ptr-pdfs/2026/20012345.pdf")
    assert results[0]["filing_date"] == date(2026, 1, 15)

    # Second row
    assert results[1]["name"] == "Tuberville, Tommy"
    assert results[1]["office"] == "AL"
    assert results[1]["year"] == 2026
    assert results[1]["filing_date"] == date(2026, 2, 20)

    # Third row
    assert results[2]["name"] == "Crenshaw, Dan"
    assert results[2]["office"] == "TX02"
    assert results[2]["year"] == 2025
    assert results[2]["filing_type"] == "Annual Report"
    assert results[2]["filing_date"] == date(2025, 3, 10)

    # All results should have source == "house"
    for r in results:
        assert r["source"] == "house"
        assert r["filing_id"].startswith("house-")


def test_parse_search_results_empty() -> None:
    """Empty HTML (no table) returns an empty list."""
    assert _parse_search_results("") == []
    assert _parse_search_results("<html><body></body></html>") == []
    assert _parse_search_results("<html><body><table></table></body></html>") == []


def test_generate_filing_id() -> None:
    """Filing ID is deterministic and prefixed with 'house-'."""
    url = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2026/20012345.pdf"
    id1 = _generate_filing_id(url)
    id2 = _generate_filing_id(url)

    assert id1 == id2  # deterministic
    assert id1.startswith("house-")
    assert len(id1) == len("house-") + 16  # 16 hex chars

    # Different URL produces different ID
    url2 = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2026/99999999.pdf"
    assert _generate_filing_id(url2) != id1


def test_parse_date() -> None:
    """Various date formats are parsed correctly."""
    assert _parse_date("01/15/2026") == date(2026, 1, 15)
    assert _parse_date("12/31/24") == date(2024, 12, 31)
    assert _parse_date("2025-03-10") == date(2025, 3, 10)
    assert _parse_date("Jan 15, 2026") == date(2026, 1, 15)
