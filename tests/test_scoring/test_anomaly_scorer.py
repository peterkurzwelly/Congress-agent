"""Tests for the anomaly scorer module."""

from datetime import date

from congress_trades.scoring.anomaly_scorer import (
    _score_disclosure_delay,
    _score_trade_size,
    check_late_filing,
)


class TestCheckLateFiling:
    """Tests for the STOCK Act 45-day rule checker."""

    def test_on_time_30_days(self) -> None:
        """30 days between trade and disclosure is not late."""
        trade_date = date(2026, 1, 1)
        disclosure_date = date(2026, 1, 31)
        result = check_late_filing(trade_date, disclosure_date)

        assert result.is_late is False
        assert result.days_late == 0
        assert result.fine_exposure == 0

    def test_late_60_days(self) -> None:
        """60 days between trade and disclosure is late with $200 fine."""
        trade_date = date(2026, 1, 1)
        disclosure_date = date(2026, 3, 2)  # 60 days later
        result = check_late_filing(trade_date, disclosure_date)

        assert result.is_late is True
        assert result.days_late == 15  # 60 - 45
        assert result.fine_exposure == 200

    def test_exactly_45_days_not_late(self) -> None:
        """Exactly 45 days is the boundary and should NOT be late."""
        trade_date = date(2026, 1, 1)
        disclosure_date = date(2026, 2, 15)  # 45 days later
        result = check_late_filing(trade_date, disclosure_date)

        assert result.is_late is False
        assert result.days_late == 0
        assert result.fine_exposure == 0


class TestScoreTradeSize:
    """Tests for _score_trade_size."""

    def test_small_trade(self) -> None:
        """Trade under $15k midpoint scores 0."""
        assert _score_trade_size(1_001, 15_000) == 0.0

    def test_medium_trade(self) -> None:
        """Trade with midpoint in $50k-$100k range scores 6."""
        assert _score_trade_size(50_001, 100_000) == 6.0

    def test_large_trade(self) -> None:
        """Trade with midpoint >= $500k scores 15 (max)."""
        assert _score_trade_size(1_000_001, 5_000_000) == 15.0

    def test_mid_range_trade(self) -> None:
        """Trade with midpoint in $15k-$50k range scores 3."""
        assert _score_trade_size(15_001, 50_000) == 3.0


class TestScoreDisclosureDelay:
    """Tests for _score_disclosure_delay."""

    def test_within_30_days(self) -> None:
        """Delay of 20 days scores 0."""
        trade_date = date(2026, 1, 1)
        disclosure_date = date(2026, 1, 21)
        assert _score_disclosure_delay(trade_date, disclosure_date) == 0.0

    def test_between_30_and_45_days(self) -> None:
        """Delay of 40 days scores between 0 and 10 (linear ramp)."""
        trade_date = date(2026, 1, 1)
        disclosure_date = date(2026, 2, 10)  # 40 days
        score = _score_disclosure_delay(trade_date, disclosure_date)
        # (40 - 30) / 15 * 10 = 6.67
        assert 6.0 < score < 7.0

    def test_past_45_days(self) -> None:
        """Delay of 60 days scores above 10."""
        trade_date = date(2026, 1, 1)
        disclosure_date = date(2026, 3, 2)  # 60 days
        score = _score_disclosure_delay(trade_date, disclosure_date)
        # 10 + (60 - 45) * 0.5 = 17.5
        assert score == 17.5

    def test_max_score_cap(self) -> None:
        """Very long delay is capped at 20."""
        trade_date = date(2026, 1, 1)
        disclosure_date = date(2026, 7, 1)  # ~180 days
        score = _score_disclosure_delay(trade_date, disclosure_date)
        assert score == 20.0
