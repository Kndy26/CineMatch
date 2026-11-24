"""Create, read, reuse, and delete shared recommendation sessions."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import joinedload

from app.dependencies import Database, Recommender
from app.models.recommendation import RecommendationInput, RecommendationResult, RecommendationSession
from app.schemas import HistoryPage, RecommendationHistory, RecommendationRequest, RecommendedMovie
from app.services.recommender import InvalidPreferences, RecommendationService


router = APIRouter(prefix="/api/recommendations", tags=["Rekomendasi"])
history_query = select(RecommendationSession).options(
    joinedload(RecommendationSession.inputs),
    joinedload(RecommendationSession.results),
)


def history_item(
    saved: RecommendationSession, service: RecommendationService
) -> RecommendationHistory:
    results = []
    for result in saved.results:
        movie = service.movie(result.movie_id)
        results.append(RecommendedMovie(
            movie_id=result.movie_id,
            title=result.movie_title,
            genres=result.genres,
            rank=result.rank,
            similarity_score=result.similarity_score,
            year=movie.year if movie else None,
            imdb_id=movie.imdb_id if movie else None,
            tmdb_id=movie.tmdb_id if movie else None,
        ))
    return RecommendationHistory(
        id=saved.id,
        preferred_genre=saved.preferred_genre,
        created_at=saved.created_at,
        inputs=saved.inputs,
        results=results,
    )


@router.post("", status_code=201)
def create_recommendation(
    body: RecommendationRequest, recommender: Recommender, db: Database
) -> RecommendationHistory:
    try:
        movies = recommender.selected_movies(body.movie_ids)
        genre = recommender.preferred_genre(body.genre)
    except InvalidPreferences as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    matches = recommender.recommend(movies, genre)
    saved = RecommendationSession(
        preferred_genre=genre,
        inputs=[
            RecommendationInput(movie_id=movie.movie_id, movie_title=movie.title, position=position)
            for position, movie in enumerate(movies, start=1)
        ],
        results=[
            RecommendationResult(
                movie_id=movie.movie_id,
                movie_title=movie.title,
                genres=movie.genres,
                rank=rank,
                similarity_score=score,
            )
            for rank, (movie, score) in enumerate(matches, start=1)
        ],
    )
    with db.begin():
        db.add(saved)
        db.flush()
        response = history_item(saved, recommender)
    return response


@router.get("")
def recommendation_history(
    recommender: Recommender,
    db: Database,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=2_147_483_647)] = 0,
    q: Annotated[str | None, Query(max_length=120)] = None,
) -> HistoryPage:
    query = history_query
    if term := (q or "").strip():
        title_terms = [term]
        article, _, title = term.partition(" ")
        if article.casefold() in {"the", "a", "an"} and title.strip():
            title_terms.append(f"{title.strip()}, {article}")
        query = query.where(or_(
            RecommendationSession.inputs.any(or_(*(
                RecommendationInput.movie_title.icontains(value, autoescape=True) for value in title_terms
            ))),
            RecommendationSession.results.any(or_(*(
                RecommendationResult.movie_title.icontains(value, autoescape=True) for value in title_terms
            ))),
            RecommendationSession.preferred_genre.icontains(term, autoescape=True),
        ))
    query = query.order_by(
        RecommendationSession.created_at.desc(), RecommendationSession.id.desc()
    ).limit(limit + 1).offset(offset)
    rows = db.scalars(query).unique().all()
    return HistoryPage(
        items=[history_item(saved, recommender) for saved in rows[:limit]],
        next_offset=offset + limit if len(rows) > limit else None,
    )


@router.get("/{session_id}")
def recommendation_detail(
    session_id: UUID, recommender: Recommender, db: Database
) -> RecommendationHistory:
    query = history_query.where(RecommendationSession.id == session_id)
    saved = db.scalars(query).unique().one_or_none()
    if saved is None:
        raise HTTPException(status_code=404, detail="Sesi rekomendasi tidak ditemukan.")
    return history_item(saved, recommender)


@router.delete("/{session_id}", status_code=204)
def delete_recommendation(session_id: UUID, db: Database) -> Response:
    statement = delete(RecommendationSession).where(
        RecommendationSession.id == session_id
    ).returning(RecommendationSession.id)
    with db.begin():
        if db.scalar(statement) is None:
            raise HTTPException(status_code=404, detail="Sesi rekomendasi tidak ditemukan.")
    return Response(status_code=204)
