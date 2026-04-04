"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from congress_trades.config import settings
from congress_trades.db.session import init_db

from .routes.analytics import router as analytics_router
from .routes.exports import router as exports_router
from .routes.feeds import router as feeds_router
from .routes.members import router as members_router
from .routes.trades import router as trades_router
from .routes.watchlist import router as watchlist_router

logger = logging.getLogger(__name__)

# Resolve the frontend dist directory relative to the project root.
# Works both in development (running from repo root) and in Docker.
_FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database on startup and optionally start the scheduler."""
    await init_db()

    if settings.ENABLE_SCHEDULER:
        from congress_trades.scrapers.scheduler import start_scheduler, stop_scheduler

        logger.info("Starting APScheduler (ENABLE_SCHEDULER=True)")
        start_scheduler()

    yield

    if settings.ENABLE_SCHEDULER:
        from congress_trades.scrapers.scheduler import stop_scheduler

        logger.info("Stopping APScheduler")
        stop_scheduler()


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
app.include_router(feeds_router, prefix="/feeds", tags=["feeds"])
app.include_router(exports_router, prefix="/exports", tags=["exports"])
app.include_router(watchlist_router, prefix="/watchlist", tags=["watchlist"])


@app.get("/health")
async def health_check():
    return {"status": "ok"}


# Serve frontend static files if the dist directory exists (i.e. after build).
# This block is skipped in development so the Vite dev server can be used instead.
if _FRONTEND_DIR.is_dir():

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Catch-all route: serve static file if it exists, otherwise index.html for SPA routing."""
        file_path = _FRONTEND_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_FRONTEND_DIR / "index.html")

    # Note: Static assets (JS, CSS, images) are served by the catch-all route above.
    # The catch-all checks for actual files first, then falls back to index.html.
