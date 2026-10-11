"""FastAPI application factory.

Creates and configures the FastAPI app with:
- CORS middleware (allowing Streamlit origin)
- Lifespan logging
- Router registration
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from src.api.routes import router
from src.config.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown hooks."""
    setup_logging()
    logger.info("🚀 SQLWhisperer API starting up")
    yield
    logger.info("👋 SQLWhisperer API shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    app = FastAPI(
        title="SQLWhisperer",
        description=(
            "Natural Language → Production SQL + Self-Healing.  "
            "Convert English questions into SQL, execute them, "
            "validate results, and iterate automatically."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS — allow Streamlit frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:8501",
            "http://127.0.0.1:8501",
            "http://streamlit:8501",  # Docker service name
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rate limiting middleware (120 req/min per client)
    from src.api.rate_limiter import RateLimitMiddleware
    app.add_middleware(RateLimitMiddleware, max_requests_per_minute=120)

    app.include_router(router)

    return app


# Module-level app instance for ``uvicorn src.api.app:app``
app = create_app()
