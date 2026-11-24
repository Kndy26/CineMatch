"""FastAPI entry point for CineMatch."""

from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, SQLAlchemyError, TimeoutError

from .config import MetadataSettings
from .database import DatabaseConfigurationError, get_engine
from .routers import movies, pages, recommendations
from .services.movie_metadata import MovieMetadataService, tmdb_client
from .services.recommender import RecommendationService


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.recommender = RecommendationService.load()
    secret = MetadataSettings().tmdb_read_access_token
    token = secret.get_secret_value().strip() if secret else ""
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(tmdb_client(token)) if token else None
        app.state.movie_metadata = MovieMetadataService(client)
        yield


app = FastAPI(
    title="CineMatch",
    description="Pencarian film MovieLens, rekomendasi kemiripan, dan riwayat bersama.",
    lifespan=lifespan,
)
app.include_router(movies.router)
app.include_router(recommendations.router)
app.include_router(pages.router)
app.mount("/static", StaticFiles(directory=pages.STATIC_DIR), name="static")


@app.exception_handler(DatabaseConfigurationError)
@app.exception_handler(OperationalError)
@app.exception_handler(TimeoutError)
async def database_unavailable(_request: Request, _error: Exception) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "Database tidak tersedia."})


@app.get("/health", tags=["Health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get(
    "/health/db",
    tags=["Health"],
    responses={503: {"description": "Database tidak tersedia"}},
)
def database_health() -> dict[str, str]:
    try:
        with get_engine().connect() as connection:
            connection.scalar(select(1))
    except (SQLAlchemyError, ValidationError):
        raise HTTPException(status_code=503, detail="Database tidak tersedia.") from None
    return {"status": "ok"}
