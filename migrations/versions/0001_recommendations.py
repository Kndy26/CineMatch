"""Create shared recommendation sessions, inputs and results."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY


revision = "0001_recommendations"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recommendation_sessions",
        sa.Column("id", sa.Uuid(), server_default=sa.func.gen_random_uuid(), primary_key=True),
        sa.Column("preferred_genre", sa.String(50), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_recommendation_sessions_created_at", "recommendation_sessions", ["created_at"]
    )

    op.create_table(
        "recommendation_inputs",
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("recommendation_sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("movie_id", sa.Integer(), primary_key=True),
        sa.Column("movie_title", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("session_id", "position", name="uq_recommendation_inputs_position"),
        sa.CheckConstraint("position > 0", name="ck_recommendation_inputs_position"),
        sa.CheckConstraint("movie_id > 0", name="ck_recommendation_inputs_movie_id"),
    )

    op.create_table(
        "recommendation_results",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("recommendation_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("movie_id", sa.Integer(), nullable=False),
        sa.Column("movie_title", sa.Text(), nullable=False),
        sa.Column("genres", ARRAY(sa.Text()), nullable=False),
        sa.Column("similarity_score", sa.Double(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.UniqueConstraint("session_id", "rank", name="uq_recommendation_results_rank"),
        sa.UniqueConstraint("session_id", "movie_id", name="uq_recommendation_results_movie_id"),
        sa.CheckConstraint("rank > 0", name="ck_recommendation_results_rank"),
        sa.CheckConstraint("movie_id > 0", name="ck_recommendation_results_movie_id"),
        sa.CheckConstraint(
            "similarity_score BETWEEN 0 AND 1", name="ck_recommendation_results_similarity_score"
        ),
    )


def downgrade() -> None:
    op.drop_table("recommendation_results")
    op.drop_table("recommendation_inputs")
    op.drop_index("ix_recommendation_sessions_created_at", table_name="recommendation_sessions")
    op.drop_table("recommendation_sessions")
