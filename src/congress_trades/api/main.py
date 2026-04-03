"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from congress_trades.db.session import init_db

from .routes.analytics import router as analytics_router
from .routes.members import router as members_router
from .routes.trades import router as trades_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database on startup."""
    await init_db()
    yield


app = FastAPI(
    title="Congress Trades API",
    description="Track and analyze US congressional stock trades",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(trades_router, prefix="/api/trades", tags=["trades"])
app.include_router(members_router, prefix="/api/members", tags=["members"])
app.include_router(analytics_router, prefix="/api/analytics", tags=["analytics"])


@app.get("/health")
async def health_check():
    return {"status": "ok"}
