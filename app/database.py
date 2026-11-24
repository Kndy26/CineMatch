"""SQLAlchemy engine and request-scoped sessions."""

from collections.abc import Iterator
from functools import lru_cache

from pydantic import ValidationError
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session

from .config import get_settings


class Base(DeclarativeBase):
    pass


class DatabaseConfigurationError(RuntimeError):
    pass


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        str(get_settings().database_url),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5},
    )


def get_session() -> Iterator[Session]:
    try:
        engine = get_engine()
    except ValidationError as error:
        raise DatabaseConfigurationError from error
    with Session(engine) as session:
        yield session
