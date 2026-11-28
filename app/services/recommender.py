"""Serve the saved MovieLens catalog and diversify KNN results across seed films."""

import json
import re
import unicodedata
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np

from app.schemas import Movie, RECOMMENDATION_LIMIT
from ml.recommender import ARTIFACT_DIR, MovieRecommender


TRAILING_ARTICLE = re.compile(r"^(.+), (the|a|an)( \(.*)?$")
RELEASE_YEAR = re.compile(r" \(\d{4}\)$")


class InvalidPreferences(ValueError):
    pass


def normalize_title(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.casefold())
    return " ".join("".join(char for char in text if not unicodedata.combining(char)).split())


def search_titles(title: str) -> tuple[str, ...]:
    normalized = normalize_title(title)
    aliases = [normalized]
    if match := TRAILING_ARTICLE.fullmatch(normalized):
        name, article, suffix = match.groups()
        aliases.append(f"{article} {name}{suffix or ''}")
    return tuple(dict.fromkeys(aliases + [RELEASE_YEAR.sub("", alias) for alias in aliases]))


class RecommendationService:
    def __init__(self, model: MovieRecommender, evaluation: dict[str, Any]):
        self.model = model
        self.evaluation = evaluation
        records = model.catalog.to_dict(orient="records")
        self._movies = [
            Movie(**{**record, "genres": list(genres)})
            for record, genres in zip(records, model.movie_genres, strict=True)
        ]
        self._titles = [search_titles(movie.title) for movie in self._movies]
        self.genres = sorted(model.genre_masks)
        self._genre_names = {genre.casefold(): genre for genre in self.genres}
        years = [movie.year for movie in self._movies if movie.year is not None]
        self.min_year = min(years) if years else 1900
        self.max_year = max(years) if years else 2026
        self._years = np.array(
            [movie.year if movie.year is not None else -1 for movie in self._movies],
            dtype=np.int64,
        )

    @classmethod
    def load(cls, artifact_dir: Path = ARTIFACT_DIR) -> "RecommendationService":
        model = MovieRecommender.load(artifact_dir)
        report_path = artifact_dir / "evaluation.json"
        return cls(model, json.loads(report_path.read_text(encoding="utf-8")))

    def movie(self, movie_id: int) -> Movie | None:
        row = self.model.movie_rows.get(movie_id)
        return self._movies[row] if row is not None else None

    def search(self, query: str, limit: int) -> list[Movie]:
        query = normalize_title(query)
        if not query:
            raise ValueError("Masukkan judul film untuk mencari.")

        ranked = []
        for movie, titles in zip(self._movies, self._titles, strict=True):
            if query in titles:
                priority = 0
            elif any(title.startswith(query) for title in titles):
                priority = 1
            elif any(query in title for title in titles):
                priority = 2
            else:
                continue
            ranked.append((priority, -movie.train_rating_count, movie.movie_id, movie))
        ranked.sort()
        return [movie for _, _, _, movie in ranked[:limit]]

    def popular(self, limit: int) -> list[Movie]:
        return [
            self._movies[row] for row in self.model.popularity_order[:limit]
            if self.model.train_counts[row] > 0
        ]

    def selected_movies(self, movie_ids: list[int]) -> list[Movie]:
        unknown_ids = [str(movie_id) for movie_id in movie_ids if movie_id not in self.model.movie_rows]
        if unknown_ids:
            raise InvalidPreferences("ID film tidak ditemukan: " + ", ".join(unknown_ids))
        return [self._movies[self.model.movie_rows[movie_id]] for movie_id in movie_ids]

    def preferred_genre(self, genre: str | None) -> str | None:
        if genre is None:
            return None
        canonical = self._genre_names.get(genre.casefold())
        if canonical is None:
            raise InvalidPreferences(f"Genre tidak ditemukan: {genre}")
        return canonical

    def recommend(
        self,
        seeds: list[Movie],
        genre: str | None,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[tuple[Movie, float]]:
        if year_from is not None and year_to is not None and year_from > year_to:
            raise InvalidPreferences("Tahun awal tidak boleh lebih besar dari tahun akhir.")

        seed_rows = [self.model.movie_rows[movie.movie_id] for movie in seeds]
        excluded = set(seed_rows)
        allowed = self.model.genre_masks.get(genre)
        year_mask = None
        if year_from is not None or year_to is not None:
            year_mask = self._years > 0
            if year_from is not None:
                year_mask &= self._years >= year_from
            if year_to is not None:
                year_mask &= self._years <= year_to

        best_scores = np.zeros(len(self._movies))
        queues = deque()

        for seed in seed_rows:
            rows, scores = self.model.rank(seed)
            best_scores[rows] = np.maximum(best_scores[rows], scores)
            eligible = scores > 0
            if allowed is not None:
                eligible &= allowed[rows]
            if year_mask is not None:
                eligible &= year_mask[rows]
            queues.append(iter(rows[eligible]))

        # Give each selected film a turn before taking a second neighbor from any film.
        selected = []
        while queues and len(selected) < RECOMMENDATION_LIMIT:
            candidates = queues.popleft()
            row = next((row for row in candidates if row not in excluded), None)
            if row is not None:
                selected.append(row)
                excluded.add(row)
                queues.append(candidates)

        selected.sort(key=lambda row: (
            -best_scores[row], -self.model.train_counts[row], self.model.movie_ids[row]
        ))
        return [(self._movies[row], round(float(best_scores[row]), 6)) for row in selected]
