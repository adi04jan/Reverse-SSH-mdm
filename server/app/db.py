"""SQLite engine + session helpers."""
from collections.abc import Iterator
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from .config import settings

_db_file = Path(settings.db_path)
_db_file.parent.mkdir(parents=True, exist_ok=True)

# check_same_thread=False so the engine can be shared across FastAPI workers/threads.
engine = create_engine(
    f"sqlite:///{_db_file}",
    echo=False,
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    # Import models so SQLModel registers the tables before create_all.
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
