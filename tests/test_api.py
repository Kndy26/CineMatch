import os
import unittest
from contextlib import AsyncExitStack
from unittest.mock import patch
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient, MockTransport, Response
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.exc import IntegrityError, OperationalError

from app.database import get_session
from app.main import app
from app.models.recommendation import RecommendationInput, RecommendationResult, RecommendationSession
from app.services.movie_metadata import MovieMetadataService
from app.services.recommender import RecommendationService


TEST_DATABASE_URL = os.environ.get("CINEMATCH_TEST_DATABASE_URL")


class AppTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.stack = AsyncExitStack()
        self.addAsyncCleanup(self.stack.aclose)
        self.startup_loader = self.stack.enter_context(
            patch.object(RecommendationService, "load", wraps=RecommendationService.load)
        )
        await self.stack.enter_async_context(app.router.lifespan_context(app))
        self.client = await self.stack.enter_async_context(
            AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")
        )


class CatalogApiTests(AppTestCase):
    async def test_metadata_uses_tmdb_mapping_and_keeps_catalog_available(self):
        def upstream(request):
            self.assertEqual(request.url.path, "/3/movie/137113")
            self.assertEqual(request.url.params["language"], "id-ID")
            return Response(200, json={"poster_path": "/film.jpg", "overview": "Sinopsis."})

        async with AsyncClient(
            base_url="https://api.themoviedb.org/3/", transport=MockTransport(upstream)
        ) as client:
            with patch.object(app.state, "movie_metadata", MovieMetadataService(client)):
                result = await self.client.get("/api/movies/111759/metadata")
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json(), {
                    "poster_url": "https://image.tmdb.org/t/p/w342/film.jpg",
                    "synopsis": "Sinopsis.",
                    "synopsis_language": "id-ID",
                })
                missing = await self.client.get("/api/movies/2147483647/metadata")
                self.assertEqual(missing.status_code, 404)
        catalog = await self.client.get("/api/movies/111759")
        self.assertEqual(catalog.json()["tmdb_id"], 137113)

    async def test_home_chart_renders_real_artifact_metrics(self):
        report = app.state.recommender.evaluation
        response = await self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Grafik metrik top-5", response.text)
        for method in ("knn", "popularity"):
            score = report["metrics"][method]["hit_rate_at_5"]
            self.assertIn(f"{score * 100:.2f}%".replace(".", ","), response.text)

    async def test_movie_search_detail_and_genres_use_one_startup_load(self):
        search = await self.client.get("/api/movies/search", params={"q": " THE MATRIX ", "limit": 2})
        self.assertEqual(search.status_code, 200)
        self.assertEqual(len(search.json()), 2)
        self.assertEqual(search.json()[0]["movie_id"], 2571)

        detail = await self.client.get("/api/movies/109487")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["title"], "Interstellar (2014)")
        self.assertIsNotNone(detail.json()["tmdb_id"])
        genres = await self.client.get("/api/genres")
        self.assertEqual(genres.status_code, 200)
        self.assertIn("Sci-Fi", genres.json())
        self.startup_loader.assert_called_once()

    async def test_search_empty_results_and_invalid_catalog_requests(self):
        miss = await self.client.get("/api/movies/search", params={"q": "no film named zxq1234"})
        self.assertEqual(miss.status_code, 200)
        self.assertEqual(miss.json(), [])
        for path, code in (
            ("/api/movies/search?q=%20%20", 422),
            ("/api/movies/search?q=matrix&limit=31", 422),
            ("/api/movies/popular?limit=0", 422),
            ("/api/movies/2147483647", 404),
            ("/api/movies/-1", 422),
        ):
            with self.subTest(path=path):
                self.assertEqual((await self.client.get(path)).status_code, code)

    async def test_popular_movies_and_evaluation(self):
        response = await self.client.get("/api/movies/popular?limit=3")
        self.assertEqual(response.status_code, 200)
        films = response.json()
        self.assertEqual(len(films), 3)
        counts = [film["train_rating_count"] for film in films]
        self.assertEqual(counts, sorted(counts, reverse=True))
        self.assertNotIn("similarity_score", films[0])

        response = await self.client.get("/api/model/evaluation")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["dataset"]["catalog_movies"], 27278)
        self.assertIn("ndcg_at_5", response.json()["metrics"]["knn"])

    async def test_recommendation_input_validation(self):
        self.stack.enter_context(patch.dict(app.dependency_overrides, {get_session: lambda: None}))
        for payload in (
            {"movie_ids": []},
            {"movie_ids": [1, 1]},
            {"movie_ids": [1, 2, 3, 4, 5, 6]},
            {"movie_ids": [True]},
            {"movie_ids": [2147483647]},
            {"movie_ids": [1], "genre": "Unknown"},
            {"movie_ids": [1], "genre": "  "},
        ):
            with self.subTest(payload=payload):
                response = await self.client.post("/api/recommendations", json=payload)
                self.assertEqual(response.status_code, 422)
        self.assertEqual(
            (await self.client.get("/api/recommendations/not-a-uuid")).status_code, 422
        )

    async def test_history_returns_503_when_database_unavailable(self):
        unavailable = OperationalError(None, None, RuntimeError("connection unavailable"))
        with patch("app.database.get_engine", side_effect=unavailable):
            response = await self.client.get("/api/recommendations")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "Database tidak tersedia."})


@unittest.skipUnless(TEST_DATABASE_URL, "Set CINEMATCH_TEST_DATABASE_URL to a migrated test database.")
class RecommendationApiTests(AppTestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(TEST_DATABASE_URL, connect_args={"connect_timeout": 5})
        cls.addClassCleanup(cls.engine.dispose)

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.stack.enter_context(patch("app.database.get_engine", return_value=self.engine))

    def remove_fixture(self, session_id):
        with self.engine.begin() as connection:
            connection.execute(
                delete(RecommendationSession).where(RecommendationSession.id == UUID(session_id))
            )

    async def create_session(self, body):
        response = await self.client.post("/api/recommendations", json=body)
        self.assertEqual(response.status_code, 201, response.text)
        saved = response.json()
        self.addCleanup(self.remove_fixture, saved["id"])
        return saved

    async def test_create_reuse_paginate_and_delete_shared_history(self):
        first = await self.create_session({"movie_ids": [109487, 1]})
        inputs = [film["movie_id"] for film in first["inputs"]]
        self.assertEqual(inputs, [109487, 1])
        self.assertEqual([film["position"] for film in first["inputs"]], [1, 2])
        result_ids = {film["movie_id"] for film in first["results"]}
        self.assertEqual(len(result_ids), 5)
        self.assertFalse(result_ids.intersection(inputs))
        self.assertIn(3114, result_ids)
        self.assertIn(104841, result_ids)
        scores = [film["similarity_score"] for film in first["results"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(all(0 < score <= 1 for score in scores))

        detail = await self.client.get(f"/api/recommendations/{first['id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json(), first)
        reused = [film["movie_id"] for film in detail.json()["inputs"]]
        second = await self.create_session({"movie_ids": reused, "genre": " sci-fi "})
        self.assertEqual(second["preferred_genre"], "Sci-Fi")
        self.assertTrue(second["results"])
        self.assertTrue(all("Sci-Fi" in film["genres"] for film in second["results"]))

        page = await self.client.get("/api/recommendations?limit=1")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.json(), {"items": [second], "next_offset": 1})
        previous = await self.client.get("/api/recommendations?limit=1&offset=1")
        self.assertEqual(previous.json()["items"], [first])

        search = await self.client.get("/api/recommendations", params={"q": "interstellar"})
        self.assertEqual(search.status_code, 200)
        self.assertTrue({first["id"], second["id"]}.issubset(
            {item["id"] for item in search.json()["items"]}
        ))
        wildcard = await self.client.get("/api/recommendations", params={"q": "%"})
        self.assertFalse({first["id"], second["id"]}.intersection(
            {item["id"] for item in wildcard.json()["items"]}
        ))

        missing = await self.client.get(f"/api/recommendations/{uuid4()}")
        self.assertEqual(missing.status_code, 404)
        target = f"/api/recommendations/{first['id']}"
        removed = await self.client.delete(target)
        self.assertEqual(removed.status_code, 204)
        self.assertEqual(removed.content, b"")
        self.assertEqual((await self.client.get(target)).status_code, 404)
        self.assertEqual((await self.client.delete(target)).status_code, 404)
        with self.engine.connect() as connection:
            for model in (RecommendationInput, RecommendationResult):
                count = connection.scalar(select(func.count()).select_from(model).where(
                    model.session_id == UUID(first["id"])
                ))
                self.assertEqual(count, 0)

    async def test_empty_matches_can_be_saved_and_reused(self):
        with patch.object(app.state.recommender, "recommend", return_value=[]):
            saved = await self.create_session({"movie_ids": [1]})
        fetched = await self.client.get(f"/api/recommendations/{saved['id']}")
        self.assertEqual(fetched.json()["results"], [])
        self.assertEqual(fetched.json()["inputs"][0]["movie_id"], 1)

    async def test_database_rolls_back_session_on_result_failure(self):
        recommender = app.state.recommender
        movie = recommender.movie(3114)
        count_query = select(func.count()).select_from(RecommendationSession)
        with self.engine.connect() as connection:
            before = connection.scalar(count_query)
        with patch.object(recommender, "recommend", return_value=[(movie, 0.9), (movie, 0.8)]):
            with self.assertRaises(IntegrityError):
                await self.client.post("/api/recommendations", json={"movie_ids": [1]})
        with self.engine.connect() as connection:
            self.assertEqual(connection.scalar(count_query), before)
