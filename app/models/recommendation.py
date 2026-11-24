"""Shared recommendation sessions, selected films and ranked results."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint, DateTime, Double, ForeignKey, Identity, Index, String, Text,
    UniqueConstraint, Uuid, func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RecommendationSession(Base):
    __tablename__ = "recommendation_sessions"
    __table_args__ = (Index("ix_recommendation_sessions_created_at", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=func.gen_random_uuid())
    preferred_genre: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    inputs: Mapped[list["RecommendationInput"]] = relationship(
        back_populates="session",
        order_by="RecommendationInput.position",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    results: Mapped[list["RecommendationResult"]] = relationship(
        back_populates="session",
        order_by="RecommendationResult.rank",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class RecommendationInput(Base):
    __tablename__ = "recommendation_inputs"
    __table_args__ = (
        UniqueConstraint("session_id", "position", name="uq_recommendation_inputs_position"),
        CheckConstraint("position > 0", name="ck_recommendation_inputs_position"),
        CheckConstraint("movie_id > 0", name="ck_recommendation_inputs_movie_id"),
    )

    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("recommendation_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    movie_id: Mapped[int] = mapped_column(primary_key=True)
    movie_title: Mapped[str] = mapped_column(Text)
    position: Mapped[int]

    session: Mapped[RecommendationSession] = relationship(back_populates="inputs")


class RecommendationResult(Base):
    __tablename__ = "recommendation_results"
    __table_args__ = (
        UniqueConstraint("session_id", "rank", name="uq_recommendation_results_rank"),
        UniqueConstraint("session_id", "movie_id", name="uq_recommendation_results_movie_id"),
        CheckConstraint("rank > 0", name="ck_recommendation_results_rank"),
        CheckConstraint("movie_id > 0", name="ck_recommendation_results_movie_id"),
        CheckConstraint(
            "similarity_score BETWEEN 0 AND 1", name="ck_recommendation_results_similarity_score"
        ),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("recommendation_sessions.id", ondelete="CASCADE")
    )
    movie_id: Mapped[int]
    movie_title: Mapped[str] = mapped_column(Text)
    genres: Mapped[list[str]] = mapped_column(ARRAY(Text))
    similarity_score: Mapped[float] = mapped_column(Double)
    rank: Mapped[int]

    session: Mapped[RecommendationSession] = relationship(back_populates="results")
