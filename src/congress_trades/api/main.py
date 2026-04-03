"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from congress_trades.db.session import init_db

from .routes.analytics import router as analytics_router
from .routes.members import router as members_router
from .routes.trades import router as trades_router

# Resolve the frontend dist directory relative to the project root.
# Works both in development (running from repo root) and in Docker.
_FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend" / "dist"


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


# Serve frontend static files if the dist directory exists (i.e. after build).
# This block is skipped in development so the Vite dev server can be used instead.
if _FRONTEND_DIR.is_dir():

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Catch-all route: serve static file if it exists, otherwise index.html for client-side routing."""
        file_path = _FRONTEND_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_FRONTEND_DIR / "index.html")

    # Note: Static assets (JS, CSS, images) are served by the catch-all route above.
    # The catch-all checks for actual files first, then falls back to index.html.
