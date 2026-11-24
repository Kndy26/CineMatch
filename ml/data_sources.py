"""Load the MovieLens catalog and stream complete user histories."""

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


ML_DIR = Path(__file__).resolve().parent
RAW_DATA_DIR = ML_DIR / "data" / "raw"
LEGACY_DATA_DIR = ML_DIR.parents[1] / "archive"
DEFAULT_DATA_DIR = (
    LEGACY_DATA_DIR
    if LEGACY_DATA_DIR.is_dir() and not any(
        (RAW_DATA_DIR / name).is_file() for name in ("movies.csv", "movie.csv")
    )
    else RAW_DATA_DIR
)
RATING_COLUMNS = ["userId", "movieId", "rating", "timestamp"]
NO_GENRES = "(no genres listed)"


def source_file(data_dir, stem):
    for name in (f"{stem}.csv", f"{stem}s.csv"):
        path = data_dir / name
        if path.is_file():
            return path
    raise FileNotFoundError(f"Missing {stem}.csv or {stem}s.csv in {data_dir}")


def clean_catalog(data_dir):
    movies = pd.read_csv(source_file(data_dir, "movie"))
    links = pd.read_csv(source_file(data_dir, "link"), dtype={"imdbId": "string"})
    tags = pd.read_csv(source_file(data_dir, "tag"), usecols=["movieId", "tag"])

    movies["title"] = movies["title"].str.strip()
    movies["genres"] = movies["genres"].fillna("").str.strip().replace(NO_GENRES, "")
    catalog = movies.dropna(subset=["movieId", "title"])
    catalog = catalog.loc[catalog["title"].ne("")].drop_duplicates("movieId")
    catalog = catalog.sort_values("movieId").reset_index(drop=True)
    catalog["movieId"] = catalog["movieId"].astype("int64")
    catalog["year"] = catalog["title"].str.extract(r"\((\d{4})\)\s*$")[0].astype("Int64")

    link_rows = links.dropna(subset=["movieId"]).drop_duplicates("movieId")
    catalog = catalog.merge(link_rows, on="movieId", how="left", validate="one_to_one")
    catalog["imdbId"] = "tt" + catalog["imdbId"].str.zfill(7)
    catalog["tmdbId"] = catalog["tmdbId"].astype("Int64")

    normalized_tags = tags["tag"].fillna("").str.casefold().str.strip()
    normalized_tags = normalized_tags.str.replace(r"\s+", " ", regex=True)
    valid_tags = tags.loc[tags["movieId"].isin(catalog["movieId"])].copy()
    valid_tags["tag"] = normalized_tags.loc[valid_tags.index]
    valid_tags = valid_tags.loc[valid_tags["tag"].ne("")]
    unique_tags = valid_tags.drop_duplicates(["movieId", "tag"])
    tag_documents = unique_tags.groupby("movieId")["tag"].agg(" ".join)
    catalog["tag_text"] = catalog["movieId"].map(tag_documents).fillna("")

    genre_counts = Counter(
        genre for genres in catalog["genres"] if genres for genre in genres.split("|")
    )
    overview = {
        "movie_rows": len(movies),
        "catalog_movies": len(catalog),
        "movie_rows_removed": len(movies) - len(catalog),
        "movies_without_genres": int(catalog["genres"].eq("").sum()),
        "movies_without_year": int(catalog["year"].isna().sum()),
        "movies_with_tags": len(tag_documents),
        "genre_counts": dict(sorted(genre_counts.items())),
        "tag_rows": len(tags),
        "invalid_or_empty_tag_rows": len(tags) - len(valid_tags),
        "duplicate_movie_tag_rows": len(valid_tags) - len(unique_tags),
        "unique_movie_tag_pairs": len(unique_tags),
        "link_rows": len(links),
        "movies_without_imdb_id": int(catalog["imdbId"].isna().sum()),
        "movies_without_tmdb_id": int(catalog["tmdbId"].isna().sum()),
    }
    return catalog.rename(
        columns={"movieId": "movie_id", "imdbId": "imdb_id", "tmdbId": "tmdb_id"}
    ), overview


def inspect_tag_genome(data_dir, chunk_size):
    tags_path = data_dir / "genome-tags.csv"
    if not tags_path.is_file():
        tags_path = data_dir / "genome_tags.csv"
    scores_path = data_dir / "genome-scores.csv"
    if not scores_path.is_file():
        scores_path = data_dir / "genome_scores.csv"
    stats = {}
    if tags_path.is_file():
        stats["tag_rows"] = len(pd.read_csv(tags_path, usecols=["tagId"]))
    if scores_path.is_file():
        stats["score_rows"] = sum(
            len(chunk) for chunk in pd.read_csv(scores_path, usecols=["relevance"], chunksize=chunk_size)
        )
    return stats


def rating_batches(path, chunk_size, audit):
    """Keep the last user of each CSV chunk for the next chunk."""
    carry = None
    previous_user = None
    reader = pd.read_csv(
        path, usecols=RATING_COLUMNS, dtype={"rating": "float32"}, chunksize=chunk_size
    )
    for chunk in reader:
        audit["rating_rows"] += len(chunk)
        valid_users = chunk["userId"].notna() & chunk["userId"].gt(0)
        audit["invalid_rating_rows"] += int((~valid_users).sum())
        chunk = chunk.loc[valid_users]
        if chunk.empty:
            continue
        user_ids = chunk["userId"]
        if not user_ids.is_monotonic_increasing or (
            previous_user is not None and user_ids.iat[0] < previous_user
        ):
            raise ValueError("Ratings must be grouped in ascending userId order, as in MovieLens.")
        previous_user = user_ids.iat[-1]
        if carry is not None:
            chunk = pd.concat([carry, chunk], ignore_index=True)
        boundary = chunk["userId"].searchsorted(previous_user)
        carry = chunk.iloc[boundary:].copy()
        if boundary:
            yield chunk.iloc[:boundary]
    if carry is not None:
        yield carry


def clean_ratings(batch, catalog_ids, audit):
    timestamps = batch["timestamp"]
    if pd.api.types.is_numeric_dtype(timestamps):
        timestamps = pd.to_datetime(timestamps, unit="s", errors="coerce")
    else:
        timestamps = pd.to_datetime(timestamps, format="%Y-%m-%d %H:%M:%S", errors="coerce")

    movie_rows = catalog_ids.get_indexer(batch["movieId"])
    valid = timestamps.notna() & batch["rating"].between(0.5, 5.0) & (movie_rows >= 0)
    audit["invalid_rating_rows"] += int((~valid).sum())
    ratings = batch.loc[valid, ["userId", "rating"]].assign(
        timestamp=timestamps.loc[valid], movie_row=movie_rows[valid]
    )
    ratings = ratings.sort_values(["userId", "timestamp", "movie_row"])
    clean = ratings.drop_duplicates(["userId", "movie_row"], keep="last")
    audit["duplicate_rating_rows"] += len(ratings) - len(clean)
    return clean


@dataclass
class EvaluationCase:
    seed_row: int
    seen_rows: np.ndarray
    relevant_rows: set[int]


def scan_ratings(data_dir, catalog, chunk_size, positive_threshold, holdout_fraction):
    if chunk_size < 1:
        raise ValueError("Chunk size must be positive.")
    if not 0 < holdout_fraction < 1:
        raise ValueError("Holdout fraction must be between zero and one.")

    movie_ids = pd.Index(catalog["movie_id"])
    train_counts = np.zeros(len(movie_ids), dtype=np.int64)
    users_by_seed = {}
    audit = Counter(rating_rows=0, invalid_rating_rows=0, duplicate_rating_rows=0)
    distribution = Counter()
    first_rating = last_rating = None
    for raw_batch in rating_batches(source_file(data_dir, "rating"), chunk_size, audit):
        ratings = clean_ratings(raw_batch, movie_ids, audit)
        if ratings.empty:
            continue

        audit["valid_ratings"] += len(ratings)
        distribution.update(ratings["rating"].value_counts().to_dict())
        batch_first, batch_last = ratings["timestamp"].min(), ratings["timestamp"].max()
        first_rating = batch_first if first_rating is None else min(first_rating, batch_first)
        last_rating = batch_last if last_rating is None else max(last_rating, batch_last)

        users = ratings["userId"].to_numpy()
        movie_rows = ratings["movie_row"].to_numpy(dtype=np.int32)
        positive = ratings["rating"].to_numpy() >= positive_threshold
        starts = np.r_[0, np.flatnonzero(users[1:] != users[:-1]) + 1]
        ends = np.r_[starts[1:], len(ratings)]
        sizes = ends - starts
        cuts = ends - np.ceil(sizes * holdout_fraction).astype(int)
        train = np.arange(len(ratings)) < np.repeat(cuts, sizes)
        train_counts += np.bincount(movie_rows[train], minlength=len(movie_ids))
        audit["users"] += len(starts)
        audit["train_ratings"] += int(train.sum())

        for start, cut, end in zip(starts, cuts, ends):
            liked_train = np.flatnonzero(positive[start:cut])
            liked_holdout = movie_rows[cut:end][positive[cut:end]]
            if not len(liked_train) or not len(liked_holdout):
                continue
            seed_row = int(movie_rows[start + liked_train[-1]])
            case = EvaluationCase(seed_row, movie_rows[start:cut], set(liked_holdout))
            users_by_seed.setdefault(seed_row, []).append(case)

    overview = {
        **audit,
        "holdout_ratings": audit["valid_ratings"] - audit["train_ratings"],
        "rating_distribution": {str(rating): count for rating, count in sorted(distribution.items())},
        "first_rating": first_rating.isoformat() if first_rating is not None else None,
        "last_rating": last_rating.isoformat() if last_rating is not None else None,
    }
    return train_counts, users_by_seed, overview
