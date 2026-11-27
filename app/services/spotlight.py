"""Build the home carousel from the shared recommendation history."""

from dataclasses import dataclass
from random import shuffle

from pydantic import ValidationError
from sqlalchemy import Float, desc, func, literal, select, union_all
from sqlalchemy.exc import OperationalError, ProgrammingError, TimeoutError
from sqlalchemy.orm import Session

from app import database
from app.models.recommendation import RecommendationInput, RecommendationResult, RecommendationSession
from app.schemas import Movie
from app.services.recommender import RecommendationService


SPOTLIGHT_LIMIT = 10
DEFAULT_MOVIE_IDS = (109487, 104841, 296, 3114, 2571, 356, 106487, 480)


@dataclass(frozen=True)
class SpotlightFilm:
    movie: Movie
    is_choice: bool = False
    score: float | None = None


def spotlight_films(service: RecommendationService) -> list[SpotlightFilm]:
    latest_session = (
        select(RecommendationSession.id)
        .order_by(RecommendationSession.created_at.desc(), RecommendationSession.id.desc())
        .limit(1)
        .scalar_subquery()
    )
    choices = (
        select(RecommendationInput.movie_id, RecommendationInput.position)
        .where(RecommendationInput.session_id == latest_session)
        .cte("spotlight_choices")
    )
    match = func.max(RecommendationResult.similarity_score)
    best_matches = (
        select(RecommendationResult.movie_id, match.label("score"))
        .where(RecommendationResult.movie_id.not_in(select(choices.c.movie_id)))
        .group_by(RecommendationResult.movie_id)
        .order_by(match.desc(), RecommendationResult.movie_id)
        .limit(SPOTLIGHT_LIMIT)
        .subquery()
    )
    ranked_films = union_all(
        select(
            choices.c.movie_id,
            literal(True).label("is_choice"),
            literal(None, Float).label("score"),
            choices.c.position.label("position"),
        ),
        select(best_matches.c.movie_id, literal(False), best_matches.c.score, literal(0)),
    ).order_by(desc("is_choice"), desc("score"), "position", "movie_id").limit(SPOTLIGHT_LIMIT)

    films = []
    try:
        with Session(database.get_engine()) as db:
            for movie_id, is_choice, score, _ in db.execute(ranked_films):
                if movie := service.movie(movie_id):
                    films.append(SpotlightFilm(movie, is_choice, score))
    except (OperationalError, ProgrammingError, TimeoutError, ValidationError):
        pass

    existing_ids = {film.movie.movie_id for film in films}
    defaults = list(DEFAULT_MOVIE_IDS)
    if not films:
        shuffle(defaults)
    for movie_id in defaults:
        if movie_id not in existing_ids and (movie := service.movie(movie_id)):
            films.append(SpotlightFilm(movie))
    return films[:SPOTLIGHT_LIMIT]
