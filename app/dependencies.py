"""FastAPI dependencies shared by the API routers."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.database import get_session
from app.services.recommender import RecommendationService


def get_recommender(request: Request) -> RecommendationService:
    return request.app.state.recommender


Recommender = Annotated[RecommendationService, Depends(get_recommender)]
Database = Annotated[Session, Depends(get_session)]
