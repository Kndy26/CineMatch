import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix

from ml.data_sources import inspect_tag_genome, scan_ratings
from ml.evaluate import ranking_metrics
from ml.recommender import MovieRecommender, candidate_positions


class RatingSplitTests(unittest.TestCase):
    def test_group_lens_archive_file_names_and_epoch_timestamps(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "ratings.csv").write_text(
                "userId,movieId,rating,timestamp\n1,1,5,1262304000\n1,2,4,1262390400\n",
                encoding="utf-8",
            )
            (path / "genome-tags.csv").write_text("tagId,tag\n1,space\n", encoding="utf-8")
            (path / "genome-scores.csv").write_text(
                "movieId,tagId,relevance\n1,1,0.8\n", encoding="utf-8"
            )
            catalog = pd.DataFrame({"movie_id": [1, 2]})
            counts, cases, audit = scan_ratings(path, catalog, 1, 4.0, 0.20)
            self.assertEqual(inspect_tag_genome(path, 1), {"tag_rows": 1, "score_rows": 1})

        np.testing.assert_array_equal(counts, [1, 0])
        self.assertEqual(cases[0][0].relevant_rows, {1})
        self.assertEqual(audit["first_rating"], "2010-01-01T00:00:00")

    def test_chronological_split_keeps_users_complete_across_csv_chunks(self):
        data = """userId,movieId,rating,timestamp
1,1,1,2010-01-01 00:00:00
1,1,5,2010-04-01 00:00:00
1,2,5,2010-01-01 00:00:00
1,3,4.5,2010-03-01 00:00:00
1,4,1,2010-02-01 00:00:00
2,1,5,2010-01-01 00:00:00
2,5,2,2010-04-01 00:00:00
2,99,5,2010-05-01 00:00:00
"""
        catalog = pd.DataFrame({"movie_id": [1, 2, 3, 4, 5]})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "rating.csv").write_text(data, encoding="utf-8")
            counts, cases, audit = scan_ratings(path, catalog, 2, 4.0, 0.20)

        np.testing.assert_array_equal(counts, [1, 1, 1, 1, 0])
        self.assertEqual(set(cases), {2})
        self.assertEqual(len(cases[2]), 1)
        self.assertEqual(cases[2][0].seen_rows.tolist(), [1, 3, 2])
        self.assertEqual(cases[2][0].relevant_rows, {0})
        self.assertEqual(audit["rating_rows"], 8)
        self.assertEqual(audit["duplicate_rating_rows"], 1)
        self.assertEqual(audit["invalid_rating_rows"], 1)
        self.assertEqual(audit["holdout_ratings"], 2)


class RankingTests(unittest.TestCase):
    def test_top_five_metrics_reward_relevant_movies_in_higher_positions(self):
        precision, recall, hit_rate, ndcg = ranking_metrics([3, 2, 1, 4, 5], {1, 3, 6})
        self.assertAlmostEqual(precision, 2 / 5)
        self.assertAlmostEqual(recall, 2 / 3)
        self.assertEqual(hit_rate, 1)
        self.assertAlmostEqual(ndcg, (1 + 1 / 2) / (1 + 1 / math.log2(3) + 1 / 2))
        self.assertEqual(ranking_metrics([2, 4, 5], {1, 3, 6}), (0, 0, 0, 0))

    def test_seen_movies_are_skipped_before_taking_top_five(self):
        rows = np.arange(8)
        selected = candidate_positions(rows, excluded={0, 2, 3}, limit=5)
        self.assertEqual(rows[selected].tolist(), [1, 4, 5, 6, 7])

    def test_genre_filter_searches_past_global_top_five_and_excludes_seed(self):
        catalog = pd.DataFrame({
            "movie_id": [10, 20, 30, 40, 50, 60, 70, 80],
            "title": list("ABCDEFGH"),
            "year": [2000] * 8,
            "genres": ["Drama"] * 6 + ["Comedy", "Drama|Comedy"],
            "imdb_id": [None] * 8,
            "tmdb_id": [None] * 8,
            "train_rating_count": [10, 2, 3, 4, 5, 6, 2, 1],
        })
        features = csr_matrix([[1.0, 0.0]] * 6 + [[0.0, 1.0], [0.0, 1.0]])
        recommender = MovieRecommender.fit(features, catalog)

        self.assertEqual([row["movie_id"] for row in recommender.recommend(10)], [60, 50, 40, 30, 20])
        filtered = recommender.recommend(10, genre="Comedy")
        self.assertEqual([row["movie_id"] for row in filtered], [70, 80])
        self.assertTrue(all("Comedy" in row["genres"] for row in filtered))
        with self.assertRaisesRegex(ValueError, "Unknown movie_id"):
            recommender.recommend(99)
        with self.assertRaisesRegex(ValueError, "Unknown genre"):
            recommender.recommend(10, genre="Fantasy")
