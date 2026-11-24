"""Run Alembic against CineMatch's configured PostgreSQL database."""

from logging.config import fileConfig

from alembic import context

from app.config import get_settings
from app.database import get_engine
from app.models.recommendation import RecommendationSession


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = RecommendationSession.metadata


if context.is_offline_mode():
    context.configure(
        url=str(get_settings().database_url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    with get_engine().connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
