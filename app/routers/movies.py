"""Movie search, catalog metadata, and model evaluation."""

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, Request

from app.dependencies import Recommender
from app.schemas import Movie, MovieMetadata


router = APIRouter(prefix="/api")


@router.get("/movies/search", tags=["Film"])
def search_movies(
    recommender: Recommender,
    q: Annotated[str, Query(min_length=1, max_length=120)],
    limit: Annotated[int, Query(ge=1, le=30)] = 10,
) -> list[Movie]:
    try:
        return recommender.search(q, limit)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/movies/popular", tags=["Film"])
def popular_movies(
    recommender: Recommender, limit: Annotated[int, Query(ge=1, le=50)] = 10
) -> list[Movie]:
    return recommender.popular(limit)


@router.get("/movies/{movie_id}", tags=["Film"])
def movie_detail(movie_id: Annotated[int, Path(gt=0)], recommender: Recommender) -> Movie:
    movie = recommender.movie(movie_id)
    if movie is None:
        raise HTTPException(status_code=404, detail="Film tidak ditemukan.")
    return movie


@router.get("/movies/{movie_id}/metadata", tags=["Film"])
async def movie_metadata(
    movie_id: Annotated[int, Path(gt=0)], request: Request, recommender: Recommender
) -> MovieMetadata:
    movie = movie_detail(movie_id, recommender)
    return await request.app.state.movie_metadata.get(movie)


@router.get("/genres", tags=["Film"])
def genres(recommender: Recommender) -> list[str]:
    return recommender.genres


@router.get("/model/evaluation", tags=["Model"])
def model_evaluation(recommender: Recommender) -> dict[str, Any]:
    return recommender.evaluation
