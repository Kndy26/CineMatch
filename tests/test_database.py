import os
import unittest
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.main import app
from app.models.recommendation import (
    RecommendationInput,
    RecommendationResult,
    RecommendationSession,
)


TEST_DATABASE_URL = os.environ.get("CINEMATCH_TEST_DATABASE_URL")


async def get_api(path):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        return await client.get(path)


class HealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_app_liveness(self):
        response = await get_api("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    async def test_database_error_returns_service_unavailable(self):
        with patch("app.main.get_engine", side_effect=SQLAlchemyError):
            response = await get_api("/health/db")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "Database tidak tersedia."})


@unittest.skipUnless(TEST_DATABASE_URL, "Set CINEMATCH_TEST_DATABASE_URL to a migrated test database.")
class PostgreSQLTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(TEST_DATABASE_URL, connect_args={"connect_timeout": 5})
        cls.addClassCleanup(cls.engine.dispose)

    async def test_database_health_queries_postgresql(self):
        with patch("app.main.get_engine", return_value=self.engine):
            response = await get_api("/health/db")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_multiple_inputs_and_delete_cascade(self):
        with Session(self.engine) as db:
            saved = RecommendationSession(
                preferred_genre="Sci-Fi",
                inputs=[
                    RecommendationInput(movie_id=109487, movie_title="Interstellar (2014)", position=2),
                    RecommendationInput(movie_id=1, movie_title="Toy Story (1995)", position=1),
                ],
                results=[
                    RecommendationResult(
                        movie_id=104841, movie_title="Gravity (2013)",
                        genres=["Sci-Fi", "Action"], similarity_score=0.65, rank=1,
                    )
                ],
            )
            db.add(saved)
            db.flush()
            session_id = saved.id
            db.expire_all()
            self.assertEqual([film.movie_id for film in saved.inputs], [1, 109487])
            self.assertEqual(saved.results[0].genres, ["Sci-Fi", "Action"])

            db.execute(delete(RecommendationSession).where(RecommendationSession.id == session_id))
            for model in (RecommendationInput, RecommendationResult):
                remaining = db.scalar(
                    select(func.count()).select_from(model).where(model.session_id == session_id)
                )
                self.assertEqual(remaining, 0)

    def test_duplicate_input_position_is_rejected(self):
        with Session(self.engine) as db:
            db.add(RecommendationSession(inputs=[
                RecommendationInput(movie_id=1, movie_title="Toy Story (1995)", position=1),
                RecommendationInput(movie_id=2, movie_title="Jumanji (1995)", position=1),
            ]))
            with self.assertRaises(IntegrityError) as error:
                db.flush()
            self.assertEqual(
                error.exception.orig.diag.constraint_name, "uq_recommendation_inputs_position"
            )
