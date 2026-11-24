import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx

from app.schemas import Movie, MovieMetadata
from app.services import movie_metadata as metadata_service
from app.services.movie_metadata import MovieMetadataService


def movie(movie_id: int = 100, tmdb_id: int | None = 30) -> Movie:
    return Movie(
        movie_id=movie_id, title="Test", year=2000, genres=[], imdb_id=None,
        tmdb_id=tmdb_id, train_rating_count=0,
    )


class MovieMetadataTests(unittest.IsolatedAsyncioTestCase):
    def test_curated_posters_depend_on_files_available_in_checkout(self):
        with TemporaryDirectory() as directory, patch.object(
            metadata_service, "POSTERS_DIR", Path(directory)
        ):
            self.assertFalse(metadata_service.load_artwork()["1"]["poster"])
            (Path(directory) / "1.jpg").touch()
            self.assertTrue(metadata_service.load_artwork()["1"]["poster"])

    async def test_curated_art_and_missing_metadata_without_credentials(self):
        service = MovieMetadataService()
        with patch.dict(metadata_service.ARTWORK, {"1": {"poster": True, "synopsis": "Sinopsis."}}):
            curated = await service.get(movie(1))
        self.assertEqual(curated.poster_url, "/static/images/posters/1.jpg")
        self.assertEqual(curated.synopsis_language, "id-ID")
        self.assertTrue(curated.synopsis)
        self.assertEqual(await service.get(movie()), MovieMetadata())

    async def test_fetches_english_if_localized_synopsis_is_missing_and_caches(self):
        requests = []

        def upstream(request):
            language = request.url.params["language"]
            requests.append(language)
            self.assertEqual(request.url.path, "/3/movie/30")
            if language == "id-ID":
                return httpx.Response(200, json={"poster_path": "/localized.jpg", "overview": " "})
            return httpx.Response(200, json={"poster_path": "/english.jpg", "overview": "Film synopsis."})

        async with httpx.AsyncClient(
            base_url="https://api.themoviedb.org/3/", transport=httpx.MockTransport(upstream)
        ) as client:
            service = MovieMetadataService(client)
            result = await service.get(movie())
            self.assertEqual(result.poster_url, "https://image.tmdb.org/t/p/w342/localized.jpg")
            self.assertEqual(result.synopsis, "Film synopsis.")
            self.assertEqual(result.synopsis_language, "en-US")
            self.assertEqual(await service.get(movie()), result)
            self.assertEqual(requests, ["id-ID", "en-US"])

    async def test_bad_paths_and_remote_failures_fall_back(self):
        def upstream(request):
            if request.url.path.endswith("/31"):
                raise httpx.ConnectTimeout("Timed out", request=request)
            if request.url.path.endswith("/32"):
                return httpx.Response(429)
            return httpx.Response(200, json={
                "poster_path": "//example.org/not-a-poster.jpg", "overview": "Sinopsis lokal.",
            })

        async with httpx.AsyncClient(
            base_url="https://api.themoviedb.org/3/", transport=httpx.MockTransport(upstream)
        ) as client:
            service = MovieMetadataService(client)
            result = await service.get(movie())
            self.assertIsNone(result.poster_url)
            self.assertEqual(result.synopsis_language, "id-ID")
            for tmdb_id in (31, 32, None):
                with self.subTest(tmdb_id=tmdb_id):
                    self.assertEqual(await service.get(movie(tmdb_id=tmdb_id)), MovieMetadata())
