"""Tests for the FastAPI API routes."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from congress_trades.api.main import app
from congress_trades.db.session import get_db


@pytest.fixture
def override_db(populated_db: AsyncSession):
    """Override the get_db dependency with the test session."""

    async def _get_test_db():
        yield populated_db

    app.dependency_overrides[get_db] = _get_test_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture
async def client(override_db) -> AsyncClient:
    """Create an httpx AsyncClient bound to the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_health_check(client: AsyncClient) -> None:
    """GET /health returns 200 with status ok."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_list_trades(client: AsyncClient) -> None:
    """GET /api/trades/ returns a paginated response with our sample trade."""
    resp = await client.get("/api/trades/")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "total" in body
    assert body["total"] >= 1
    assert len(body["data"]) >= 1
    # Check the trade has expected fields
    trade = body["data"][0]
    assert trade["ticker"] == "NVDA"
    assert trade["member_name"] == "Nancy Pelosi"


async def test_get_trade_by_id(client: AsyncClient) -> None:
    """GET /api/trades/1 returns the trade with enrichment data."""
    resp = await client.get("/api/trades/1")
    assert resp.status_code == 200
    trade = resp.json()
    assert trade["trade_id"] == 1
    assert trade["ticker"] == "NVDA"
    assert trade["resolved_ticker"] == "NVDA"
    assert trade["sector"] == "Technology"
    assert trade["anomaly_score"] == 73.0
    assert trade["member_name"] == "Nancy Pelosi"


async def test_get_trade_not_found(client: AsyncClient) -> None:
    """GET /api/trades/9999 returns 404."""
    resp = await client.get("/api/trades/9999")
    assert resp.status_code == 404


async def test_list_members(client: AsyncClient) -> None:
    """GET /api/members/ returns paginated response with our sample member."""
    resp = await client.get("/api/members/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    member = body["data"][0]
    assert member["name"] == "Nancy Pelosi"
    assert member["party"] == "Democrat"
    assert member["state"] == "CA"


async def test_aggregate_stats(client: AsyncClient) -> None:
    """GET /api/analytics/stats returns correct aggregate counts."""
    resp = await client.get("/api/analytics/stats")
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["total_trades"] >= 1
    assert stats["total_buys"] >= 1  # sample trade is a Purchase
    assert stats["unique_tickers"] >= 1
    assert stats["unique_politicians"] >= 1
