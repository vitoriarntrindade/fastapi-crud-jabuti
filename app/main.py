"""FastAPI application factory and lifecycle management."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.api.routers import users
from app.cache.client import close_redis_client, get_redis_client
from app.core.config import get_settings
from app.core.exceptions import DatabaseError
from app.core.logging import configure_logging
from app.database.session import engine

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown lifecycle.

    Args:
        app: The FastAPI application instance.
    """
    settings = get_settings()
    logger.info("Starting up — env=%s", settings.app_env)
    await get_redis_client()
    logger.info("Application ready")

    yield

    logger.info("Shutting down")
    await close_redis_client()
    await engine.dispose()


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application.

    Returns:
        A fully configured FastAPI instance.
    """
    app = FastAPI(
        title="Jabuti Users API",
        description=(
            "Users CRUD API with FastAPI, PostgreSQL, and Redis."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    @app.exception_handler(ValidationError)
    async def validation_exception_handler(
        _request: Request, exc: ValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.errors()},
        )

    @app.exception_handler(DatabaseError)
    async def database_error_handler(
        _request: Request, exc: DatabaseError
    ) -> JSONResponse:
        logger.error("Unhandled database error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Database error — please try again later"},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        _request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )

    app.include_router(users.router)

    @app.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=True,
    )
