"""Server-rendered pages for the CineMatch website."""

import json
import re
from math import ceil
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.dependencies import Recommender
from app.schemas import MAX_SEED_MOVIES
from app.services.movie_metadata import ARTWORK


APP_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = APP_DIR / "static"
DATA_DIR = APP_DIR / "data"
EVALUATION_METRICS = (
    ("precision_at_5", "Precision@5"),
    ("recall_at_5", "Recall@5"),
    ("hit_rate_at_5", "Hit Rate@5"),
    ("ndcg_at_5", "NDCG@5"),
)

router = APIRouter(include_in_schema=False, default_response_class=HTMLResponse)
templates = Jinja2Templates(directory=APP_DIR / "templates")


def load_page_data(filename):
    path = DATA_DIR / filename
    if not path.is_file():
        path = path.with_name(f"{path.stem}.example{path.suffix}")
    return json.loads(path.read_text(encoding="utf-8"))


def display_title(title):
    title = re.sub(r" \(\d{4}\)$", "", title)
    return re.sub(r"^(.+), (The|A|An)$", r"\2 \1", title)


templates.env.filters["film_title"] = display_title
templates.env.filters["id_number"] = lambda value: f"{value:,}".replace(",", ".")


def render(request, page, **context):
    return templates.TemplateResponse(
        request,
        f"{page}.html",
        {
            "page": page,
            "artwork": ARTWORK,
            "tmdb_enabled": request.app.state.movie_metadata.enabled,
            **context,
        },
    )


@router.get("/", name="home")
def home(request: Request, recommender: Recommender):
    report = recommender.evaluation
    metrics = report["metrics"]
    max_score = max(
        metrics[series][key]
        for series in ("knn", "popularity")
        for key, _ in EVALUATION_METRICS
    )
    axis_step = max(1, ceil(max_score * 20))
    return render(
        request,
        "home",
        popular_movies=recommender.popular(6),
        dataset=report["dataset"],
        metrics=metrics,
        evaluation_metrics=EVALUATION_METRICS,
        chart_limit=5 * axis_step,
        chart_ticks=range(0, 5 * axis_step + 1, axis_step),
        evaluated_users=report["evaluated_users"],
    )


@router.get("/discover", name="discover")
def discover(request: Request, recommender: Recommender):
    return render(request, "discover", genres=recommender.genres, max_movies=MAX_SEED_MOVIES)


@router.get("/history", name="history")
def history(request: Request):
    return render(request, "history")


@router.get("/contact", name="contact")
def contact(request: Request):
    return render(request, "contact", team=load_page_data("team.json"))
