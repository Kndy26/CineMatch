"""Build, evaluate and save the CineMatch model using the local MovieLens CSVs."""

import argparse
import json
from importlib.metadata import version
from math import sqrt
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import joblib
import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import MultiLabelBinarizer, normalize

from .data_sources import DEFAULT_DATA_DIR, clean_catalog, inspect_tag_genome, scan_ratings
from .evaluate import evaluate
from .recommender import ARTIFACT_DIR, CATALOG_COLUMNS, MovieRecommender, split_genres


CHUNK_SIZE = 500_000
POSITIVE_THRESHOLD = 4.0
HOLDOUT_FRACTION = 0.20
GENRE_WEIGHT = 0.75
TAG_WEIGHT = 0.25


def build_features(catalog):
    genre_encoder = MultiLabelBinarizer(sparse_output=True)
    genre_vectors = genre_encoder.fit_transform(catalog["genres"].map(split_genres))
    genre_vectors = normalize(genre_vectors.astype(np.float32))

    tag_vectorizer = TfidfVectorizer(dtype=np.float32, sublinear_tf=True, norm="l2")
    tag_vectors = tag_vectorizer.fit_transform(catalog["tag_text"])

    # Square roots give the desired block contributions to cosine when both blocks exist.
    features = sparse.hstack(
        [genre_vectors * sqrt(GENRE_WEIGHT), tag_vectors * sqrt(TAG_WEIGHT)], format="csr"
    )
    return normalize(features), genre_encoder, tag_vectorizer


def make_report(dataset, evaluation, features, genre_encoder, tag_vectorizer):
    if dataset["rating_rows"] == 20_000_263 and dataset["movie_rows"] == 27_278:
        dataset = {"name": "MovieLens 20M", **dataset}
    else:
        dataset = {"name": "MovieLens", **dataset}
    return {
        "dataset": dataset,
        "model": {
            "algorithm": "K-Nearest Neighbors",
            "distance": "cosine",
            "search": "brute",
            "genre_weight": GENRE_WEIGHT,
            "tag_weight": TAG_WEIGHT,
            "genre_features": len(genre_encoder.classes_),
            "tag_features": len(tag_vectorizer.vocabulary_),
            "feature_shape": list(features.shape),
            "movies_without_features": int(np.count_nonzero(np.diff(features.indptr) == 0)),
            "versions": {
                package: version(package) for package in ("numpy", "scipy", "scikit-learn", "joblib")
            },
        },
        "protocol": {
            "k": 5,
            "split": "chronological_per_user",
            "holdout_fraction": HOLDOUT_FRACTION,
            "positive_rating_threshold": POSITIVE_THRESHOLD,
            "seed": "latest_positive_training_rating",
            "candidates": "catalog_excluding_all_training_movies_of_user",
            "popularity": "rating_count_from_training_splits_only",
            "content_metadata": "full_catalog_snapshot_including_user_tags",
            "tie_break": "training_rating_count_desc_then_movie_id_asc",
            "timing_scope": "uncached_ranking_and_candidate_filtering",
        },
        **evaluation,
    }


def save_artifacts(output_dir, recommender, genre_encoder, tag_vectorizer, report):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output_dir) as staging_dir:
        staging = Path(staging_dir)
        joblib.dump(
            {"model": recommender.model, "movie_ids": recommender.movie_ids},
            staging / "recommender.joblib",
            compress=3,
        )
        joblib.dump(genre_encoder, staging / "genre_encoder.joblib", compress=3)
        joblib.dump(tag_vectorizer, staging / "tag_vectorizer.joblib", compress=3)
        sparse.save_npz(staging / "movie_features.npz", recommender.features)
        recommender.catalog[CATALOG_COLUMNS].to_csv(
            staging / "movies_processed.csv", index=False, encoding="utf-8"
        )
        for path in staging.iterdir():
            path.replace(output_dir / path.name)
        report_file = staging / "evaluation.json"
        report_file.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        report_file.replace(output_dir / report_file.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=ARTIFACT_DIR)
    parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE)
    args = parser.parse_args()
    start = perf_counter()

    print("Reading catalog, links and tags...", flush=True)
    catalog, catalog_stats = clean_catalog(args.data_dir)
    print("Scanning ratings and preparing chronological user splits...", flush=True)
    counts, cases, rating_stats = scan_ratings(
        args.data_dir, catalog, args.chunk_size, POSITIVE_THRESHOLD, HOLDOUT_FRACTION
    )
    genome_stats = inspect_tag_genome(args.data_dir, args.chunk_size)

    print("Encoding content and fitting cosine KNN...", flush=True)
    features, genre_encoder, tag_vectorizer = build_features(catalog)
    recommender = MovieRecommender.fit(features, catalog.assign(train_rating_count=counts))
    print(f"Evaluating {sum(map(len, cases.values())):,} eligible users...", flush=True)
    result = evaluate(recommender, cases)

    dataset = {**catalog_stats, **rating_stats, "tag_genome": genome_stats}
    report = make_report(dataset, result, features, genre_encoder, tag_vectorizer)
    save_artifacts(args.output_dir, recommender, genre_encoder, tag_vectorizer, report)
    print(json.dumps(report["metrics"], indent=2))
    print(f"Saved artifacts to {args.output_dir.resolve()} in {perf_counter() - start:.1f} s.")


if __name__ == "__main__":
    main()
