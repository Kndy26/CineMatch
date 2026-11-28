"""Request and response shapes for the CineMatch API."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MovieId = Annotated[int, Field(strict=True, gt=0, le=2_147_483_647)]
MAX_SEED_MOVIES = 5
RECOMMENDATION_LIMIT = 5


class Movie(BaseModel):
    movie_id: int
    title: str
    year: int | None
    genres: list[str]
    imdb_id: str | None
    tmdb_id: int | None
    train_rating_count: int


class MovieMetadata(BaseModel):
    poster_url: str | None = None
    synopsis: str | None = None
    synopsis_language: str | None = None


class RecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    movie_ids: list[MovieId] = Field(min_length=1, max_length=MAX_SEED_MOVIES)
    genre: str | None = Field(default=None, min_length=1, max_length=50)
    year_from: int | None = Field(default=None, ge=1800, le=2100)
    year_to: int | None = Field(default=None, ge=1800, le=2100)

    @field_validator("movie_ids")
    @classmethod
    def unique_movies(cls, movie_ids: list[int]) -> list[int]:
        if len(movie_ids) != len(set(movie_ids)):
            raise ValueError("Setiap film hanya boleh dipilih sekali.")
        return movie_ids

    @model_validator(mode="after")
    def valid_year_range(self) -> "RecommendationRequest":
        if self.year_from is not None and self.year_to is not None and self.year_from > self.year_to:
            raise ValueError("Tahun awal tidak boleh lebih besar dari tahun akhir.")
        return self


class SelectedMovie(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    movie_id: int
    title: str = Field(validation_alias="movie_title")
    position: int


class RecommendedMovie(BaseModel):
    movie_id: int
    title: str
    genres: list[str]
    year: int | None
    imdb_id: str | None
    tmdb_id: int | None
    similarity_score: float
    rank: int


class RecommendationHistory(BaseModel):
    id: UUID
    preferred_genre: str | None
    created_at: datetime
    inputs: list[SelectedMovie]
    results: list[RecommendedMovie]


class HistoryPage(BaseModel):
    items: list[RecommendationHistory]
    next_offset: int | None
