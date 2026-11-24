"""Optional TMDB enrichment for the local MovieLens catalog."""

import json
import logging
import re
from asyncio import Semaphore
from collections import OrderedDict
from pathlib import Path
from time import monotonic

import httpx

from app.schemas import Movie, MovieMetadata


APP_DIR = Path(__file__).resolve().parents[1]
POSTERS_DIR = APP_DIR / "static" / "images" / "posters"
POSTER_PATH = re.compile(r"/[A-Za-z0-9_-]{1,100}\.(?:jpg|jpeg|png|webp)")
CACHE_LIMIT = 512
logger = logging.getLogger(__name__)


def load_artwork():
    artwork = json.loads((APP_DIR / "data" / "artwork.json").read_text(encoding="utf-8"))
    for movie_id, entry in artwork.items():
        entry["poster"] = bool(entry.get("poster") and (POSTERS_DIR / f"{movie_id}.jpg").is_file())
    return artwork


ARTWORK = load_artwork()


def tmdb_client(token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url="https://api.themoviedb.org/3/",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=httpx.Timeout(3.0, connect=2.0),
    )


class MovieMetadataService:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client
        self._requests = Semaphore(4)
        self._cache: OrderedDict[int, tuple[float, MovieMetadata]] = OrderedDict()

    @property
    def enabled(self) -> bool:
        return self._client is not None

    async def get(self, movie: Movie) -> MovieMetadata:
        curated = ARTWORK.get(str(movie.movie_id), {})
        synopsis = curated.get("synopsis")
        local = MovieMetadata(
            poster_url=f"/static/images/posters/{movie.movie_id}.jpg" if curated.get("poster") else None,
            synopsis=synopsis,
            synopsis_language="id-ID" if synopsis else None,
        )
        if not self.enabled or not movie.tmdb_id or (local.poster_url and local.synopsis):
            return local

        remote = await self._remote(movie.tmdb_id)
        return MovieMetadata(
            poster_url=local.poster_url or remote.poster_url,
            synopsis=local.synopsis or remote.synopsis,
            synopsis_language=local.synopsis_language or remote.synopsis_language,
        )

    async def _remote(self, tmdb_id: int) -> MovieMetadata:
        async with self._requests:
            cached = self._cache.get(tmdb_id)
            if cached and cached[0] > monotonic():
                self._cache.move_to_end(tmdb_id)
                return cached[1]

            metadata = await self._details(tmdb_id, "id-ID")
            if metadata is not None and (not metadata.synopsis or not metadata.poster_url):
                english = await self._details(tmdb_id, "en-US")
                if english is not None:
                    metadata = MovieMetadata(
                        poster_url=metadata.poster_url or english.poster_url,
                        synopsis=metadata.synopsis or english.synopsis,
                        synopsis_language=metadata.synopsis_language or english.synopsis_language,
                    )
            metadata = metadata or MovieMetadata()
            ttl = 3600 if metadata.synopsis else 60
            self._cache[tmdb_id] = (monotonic() + ttl, metadata)
            self._cache.move_to_end(tmdb_id)
            if len(self._cache) > CACHE_LIMIT:
                self._cache.popitem(last=False)
            return metadata

    async def _details(self, tmdb_id: int, language: str) -> MovieMetadata | None:
        assert self._client is not None
        try:
            response = await self._client.get(f"movie/{tmdb_id}", params={"language": language})
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Invalid TMDB response")
        except httpx.HTTPStatusError as error:
            logger.info("TMDB metadata request returned status %s", error.response.status_code)
            return None
        except (httpx.RequestError, ValueError) as error:
            logger.info("TMDB metadata unavailable (%s)", type(error).__name__)
            return None

        poster = payload.get("poster_path")
        overview = payload.get("overview")
        synopsis = overview.strip() if isinstance(overview, str) else ""
        return MovieMetadata(
            poster_url=(
                f"https://image.tmdb.org/t/p/w342{poster}"
                if isinstance(poster, str) and POSTER_PATH.fullmatch(poster) else None
            ),
            synopsis=synopsis or None,
            synopsis_language=language if synopsis else None,
        )
