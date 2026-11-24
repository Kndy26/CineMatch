"""Load the saved cosine KNN model and rank films in the MovieLens catalog."""

from itertools import islice
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.neighbors import NearestNeighbors


ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
CATALOG_COLUMNS = [
    "movie_id", "title", "year", "genres", "imdb_id", "tmdb_id", "train_rating_count"
]


def split_genres(value):
    return tuple(value.split("|")) if value else ()


def candidate_positions(rows, excluded, limit, allowed=None):
    eligible = (
        position for position, row in enumerate(rows)
        if row not in excluded and (allowed is None or allowed[row])
    )
    return list(islice(eligible, limit))


class MovieRecommender:
    def __init__(self, model, features, catalog):
        if model.n_samples_fit_ != len(catalog) or features.shape != (
            len(catalog), model.n_features_in_
        ):
            raise ValueError("The model, feature matrix and catalog must have matching dimensions.")
        self.model = model
        self.features = features
        self.catalog = catalog
        self.movie_ids = catalog["movie_id"].to_numpy()
        self.movie_rows = {movie_id: row for row, movie_id in enumerate(self.movie_ids)}
        self.train_counts = catalog["train_rating_count"].to_numpy()
        self.movie_genres = catalog["genres"].map(split_genres)
        genres = sorted({genre for values in self.movie_genres for genre in values})
        self.genre_masks = {
            genre: np.asarray([genre in values for values in self.movie_genres])
            for genre in genres
        }
        self.popularity_order = np.lexsort((self.movie_ids, -self.train_counts))

    @classmethod
    def fit(cls, features, catalog):
        model = NearestNeighbors(n_neighbors=6, metric="cosine", algorithm="brute")
        return cls(model.fit(features), features, catalog)

    @classmethod
    def load(cls, artifact_dir=ARTIFACT_DIR):
        artifact_dir = Path(artifact_dir)
        artifact = joblib.load(artifact_dir / "recommender.joblib")
        features = sparse.load_npz(artifact_dir / "movie_features.npz")
        catalog = pd.read_csv(
            artifact_dir / "movies_processed.csv",
            dtype={"year": "Int64", "tmdb_id": "Int64", "imdb_id": "string"},
            keep_default_na=False,
            na_values={"year": [""], "tmdb_id": [""], "imdb_id": [""]},
        )
        if not np.array_equal(artifact["movie_ids"], catalog["movie_id"]):
            raise ValueError("The movie IDs in the model and catalog must match in order.")
        return cls(artifact["model"], features, catalog)

    def rank(self, seed_row):
        distances, neighbors = self.model.kneighbors(
            self.features[seed_row], n_neighbors=len(self.catalog)
        )
        rows = neighbors[0]
        scores = np.round(np.clip(1.0 - distances[0], 0.0, 1.0), 6)
        order = np.lexsort((self.movie_ids[rows], -self.train_counts[rows], -scores))
        return rows[order], scores[order]

    def recommend(self, movie_id, genre=None, limit=5):
        if movie_id not in self.movie_rows:
            raise ValueError(f"Unknown movie_id: {movie_id}")
        if genre is not None and genre not in self.genre_masks:
            raise ValueError(f"Unknown genre: {genre}")
        if limit < 1:
            raise ValueError("Limit must be positive.")

        seed_row = self.movie_rows[movie_id]
        rows, scores = self.rank(seed_row)
        positions = candidate_positions(rows, {seed_row}, limit, self.genre_masks.get(genre))
        results = self.catalog.iloc[rows[positions]][CATALOG_COLUMNS].to_dict(orient="records")
        for rank, (result, score) in enumerate(zip(results, scores[positions]), start=1):
            result["genres"] = list(split_genres(result["genres"]))
            result["similarity_score"] = round(float(score), 6)
            result["rank"] = rank
        return results
