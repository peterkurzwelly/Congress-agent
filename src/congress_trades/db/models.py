"""SQLAlchemy 2.0 ORM models for the Congress Trades database."""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class Member(Base):
    __tablename__ = "members"

    bioguide_id: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    chamber: Mapped[str] = mapped_column(String(10))  # "house" or "senate"
    state: Mapped[str] = mapped_column(String(2))
    district: Mapped[str | None] = mapped_column(String(5), nullable=True)
    party: Mapped[str] = mapped_column(String(20))
    committees: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    filings: Mapped[list["Filing"]] = relationship(back_populates="member")
    trades: Mapped[list["Trade"]] = relationship(back_populates="member")

    def __repr__(self) -> str:
        return f"<Member {self.name} ({self.party}-{self.state})>"


class Filing(Base):
    __tablename__ = "filings"

    filing_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.bioguide_id"), index=True)
    filing_date: Mapped[date]
    disclosure_date: Mapped[date]
    filing_url: Mapped[str] = mapped_column(String(500))
    filing_type: Mapped[str] = mapped_column(String(20))  # "ptr", "annual", "amendment"
    source: Mapped[str] = mapped_column(String(10))  # "house" or "senate"
    raw_pdf_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    parsed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    amendment_of: Mapped[str | None] = mapped_column(
        ForeignKey("filings.filing_id"), nullable=True
    )

    member: Mapped["Member"] = relationship(back_populates="filings")
    trades: Mapped[list["Trade"]] = relationship(back_populates="filing")

    def __repr__(self) -> str:
        return f"<Filing {self.filing_id} ({self.filing_type}) by {self.member_id}>"


class Trade(Base):
    __tablename__ = "trades"

    trade_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    filing_id: Mapped[str] = mapped_column(ForeignKey("filings.filing_id"), index=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.bioguide_id"), index=True)
    asset_description: Mapped[str] = mapped_column(Text)
    ticker: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    asset_type: Mapped[str] = mapped_column(String(30))  # Stock, Bond, Option, Fund, etc.
    trade_type: Mapped[str] = mapped_column(String(30))  # Purchase, Sale, Sale (Full), etc.
    trade_date: Mapped[date] = mapped_column(index=True)
    owner: Mapped[str] = mapped_column(String(30))  # Self, Spouse, Joint, Dependent Child
    amount_range: Mapped[str] = mapped_column(String(50))  # "$1,001 - $15,000"
    amount_min: Mapped[int]
    amount_max: Mapped[int]
    capital_gains_over_200: Mapped[bool | None] = mapped_column(nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    filing: Mapped["Filing"] = relationship(back_populates="trades")
    member: Mapped["Member"] = relationship(back_populates="trades")
    enrichment: Mapped[Optional["EnrichedTrade"]] = relationship(back_populates="trade")

    def __repr__(self) -> str:
        asset = self.ticker or self.asset_description[:30]
        return f"<Trade {self.trade_id}: {self.trade_type} {asset}>"


class EnrichedTrade(Base):
    __tablename__ = "enriched_trades"

    trade_id: Mapped[int] = mapped_column(
        ForeignKey("trades.trade_id"), primary_key=True
    )
    resolved_ticker: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    price_at_trade: Mapped[float | None] = mapped_column(nullable=True)
    price_current: Mapped[float | None] = mapped_column(nullable=True)
    return_1d: Mapped[float | None] = mapped_column(nullable=True)
    return_7d: Mapped[float | None] = mapped_column(nullable=True)
    return_30d: Mapped[float | None] = mapped_column(nullable=True)
    return_90d: Mapped[float | None] = mapped_column(nullable=True)
    committee_relevance_score: Mapped[float | None] = mapped_column(nullable=True)
    anomaly_score: Mapped[float | None] = mapped_column(nullable=True)
    flags: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=list)
    scored_at: Mapped[datetime | None] = mapped_column(nullable=True)

    trade: Mapped["Trade"] = relationship(back_populates="enrichment")

    def __repr__(self) -> str:
        return f"<EnrichedTrade {self.trade_id} score={self.anomaly_score}>"


class Alert(Base):
    __tablename__ = "alerts"

    alert_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.trade_id"), index=True)
    alert_type: Mapped[str] = mapped_column(
        String(30)
    )  # new_filing, high_anomaly, large_trade, late_filing
    channel: Mapped[str] = mapped_column(String(20))  # telegram, email
    message: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime]

    trade: Mapped["Trade"] = relationship()

    def __repr__(self) -> str:
        return f"<Alert {self.alert_id} ({self.alert_type}) for trade {self.trade_id}>"
