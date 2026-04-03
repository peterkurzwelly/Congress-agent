"""Tests for the bill correlator module."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from congress_trades.enrichment.bill_correlator import (
    SECTOR_KEYWORDS,
    _bill_matches_sector,
    fetch_member_bills,
    find_related_bills,
    score_bill_timing,
)


# ---------------------------------------------------------------------------
# score_bill_timing tests
# ---------------------------------------------------------------------------


class TestScoreBillTiming:
    """Test the pure scoring function with various bill/trade timing combos."""

    def _make_bill(
        self,
        days_from_trade: int,
        relationship: str = "sponsored",
        title: str = "Test Bill",
    ) -> dict:
        return {
            "bill_id": "hr123-118",
            "title": title,
            "type": "HR",
            "introduced_date": "2025-01-15",
            "subjects": [],
            "latest_action": "",
            "relationship": relationship,
            "relevance": "test",
            "days_from_trade": days_from_trade,
        }

    def test_no_bills_returns_zero(self) -> None:
        score = score_bill_timing([], date(2025, 1, 15))
        assert score == 0.0

    def test_bill_1_day_after_trade_scores_high(self) -> None:
        bills = [self._make_bill(days_from_trade=1)]
        score = score_bill_timing(bills, date(2025, 1, 15))
        assert score >= 8.0

    def test_bill_same_day_scores_high(self) -> None:
        bills = [self._make_bill(days_from_trade=0)]
        score = score_bill_timing(bills, date(2025, 1, 15))
        assert score >= 8.0

    def test_bill_7_days_after_scores_moderate(self) -> None:
        bills = [self._make_bill(days_from_trade=7)]
        score = score_bill_timing(bills, date(2025, 1, 15))
        assert 5.0 <= score <= 8.0

    def test_bill_30_days_after_scores_low(self) -> None:
        bills = [self._make_bill(days_from_trade=30)]
        score = score_bill_timing(bills, date(2025, 1, 15))
        assert 1.0 <= score <= 4.0

    def test_bill_before_trade_scores_lower(self) -> None:
        bills = [self._make_bill(days_from_trade=-3)]
        score = score_bill_timing(bills, date(2025, 1, 15))
        assert score <= 5.0

    def test_closer_bills_score_higher_than_distant(self) -> None:
        """Bills within 7 days of trade should score higher than 30 days."""
        close_bills = [self._make_bill(days_from_trade=3)]
        distant_bills = [self._make_bill(days_from_trade=25)]

        close_score = score_bill_timing(close_bills, date(2025, 1, 15))
        distant_score = score_bill_timing(distant_bills, date(2025, 1, 15))

        assert close_score > distant_score

    def test_cosponsored_scores_lower_than_sponsored(self) -> None:
        sponsored = [self._make_bill(days_from_trade=2, relationship="sponsored")]
        cosponsored = [self._make_bill(days_from_trade=2, relationship="cosponsored")]

        s_score = score_bill_timing(sponsored, date(2025, 1, 15))
        c_score = score_bill_timing(cosponsored, date(2025, 1, 15))

        assert s_score > c_score

    def test_multiple_bills_add_bonus(self) -> None:
        single = [self._make_bill(days_from_trade=5)]
        multiple = [
            self._make_bill(days_from_trade=5),
            self._make_bill(days_from_trade=10),
        ]

        single_score = score_bill_timing(single, date(2025, 1, 15))
        multi_score = score_bill_timing(multiple, date(2025, 1, 15))

        assert multi_score > single_score

    def test_score_capped_at_10(self) -> None:
        bills = [
            self._make_bill(days_from_trade=1),
            self._make_bill(days_from_trade=2),
            self._make_bill(days_from_trade=3),
            self._make_bill(days_from_trade=4),
            self._make_bill(days_from_trade=5),
        ]
        score = score_bill_timing(bills, date(2025, 1, 15))
        assert score <= 10.0


# ---------------------------------------------------------------------------
# _bill_matches_sector tests
# ---------------------------------------------------------------------------


class TestBillMatchesSector:
    def test_technology_bill_matches_technology_sector(self) -> None:
        bill = {
            "title": "Advancing Artificial Intelligence Research Act",
            "subjects": ["Science, Technology, Communications"],
        }
        matches, explanation = _bill_matches_sector(bill, "Technology")
        assert matches is True
        assert "artificial intelligence" in explanation.lower() or "technology" in explanation.lower()

    def test_healthcare_bill_matches_healthcare_sector(self) -> None:
        bill = {
            "title": "Medicare Drug Price Negotiation Act",
            "subjects": ["Health"],
        }
        matches, _ = _bill_matches_sector(bill, "Healthcare")
        assert matches is True

    def test_unrelated_bill_does_not_match(self) -> None:
        bill = {
            "title": "National Parks Preservation Act",
            "subjects": ["Public Lands and Natural Resources"],
        }
        matches, _ = _bill_matches_sector(bill, "Technology")
        assert matches is False

    def test_no_sector_returns_false(self) -> None:
        bill = {"title": "Some Bill", "subjects": []}
        matches, _ = _bill_matches_sector(bill, None)
        assert matches is False


# ---------------------------------------------------------------------------
# fetch_member_bills -- API key handling
# ---------------------------------------------------------------------------


class TestFetchMemberBills:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_api_key(self) -> None:
        with patch("congress_trades.enrichment.bill_correlator.settings") as mock_settings:
            mock_settings.CONGRESS_API_KEY = ""
            result = await fetch_member_bills("A000001", date(2025, 1, 1), date(2025, 2, 1))
            assert result == []


# ---------------------------------------------------------------------------
# find_related_bills -- integration with mocks
# ---------------------------------------------------------------------------


class TestFindRelatedBills:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_api_key(self) -> None:
        with patch("congress_trades.enrichment.bill_correlator.settings") as mock_settings:
            mock_settings.CONGRESS_API_KEY = ""
            result = await find_related_bills(
                member_id="A000001",
                trade_date=date(2025, 1, 15),
                ticker="AAPL",
                sector="Technology",
            )
            assert result == []

    @pytest.mark.asyncio
    async def test_filters_bills_by_sector(self) -> None:
        mock_bills = [
            {
                "bill_id": "hr1-118",
                "title": "Semiconductor Manufacturing Incentive Act",
                "type": "HR",
                "introduced_date": "2025-01-17",
                "subjects": ["Technology"],
                "latest_action": "Introduced",
                "relationship": "sponsored",
            },
            {
                "bill_id": "hr2-118",
                "title": "National Parks Funding Act",
                "type": "HR",
                "introduced_date": "2025-01-16",
                "subjects": ["Public Lands"],
                "latest_action": "Introduced",
                "relationship": "sponsored",
            },
        ]

        with patch(
            "congress_trades.enrichment.bill_correlator.settings"
        ) as mock_settings, patch(
            "congress_trades.enrichment.bill_correlator.fetch_member_bills",
            new_callable=AsyncMock,
            return_value=mock_bills,
        ):
            mock_settings.CONGRESS_API_KEY = "test-key"
            result = await find_related_bills(
                member_id="A000001",
                trade_date=date(2025, 1, 15),
                ticker="INTC",
                sector="Technology",
            )

            # Only the semiconductor bill should match Technology sector
            assert len(result) == 1
            assert "semiconductor" in result[0]["title"].lower()
            assert result[0]["days_from_trade"] == 2
