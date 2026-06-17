"""SQLite engine + session helpers."""
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import text
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
    _migrate()


def _migrate() -> None:
    """Lightweight, additive column migrations.

    SQLModel.create_all() only creates missing tables; it never alters existing
    ones. Add new nullable columns here so older databases pick them up on boot.
    """
    additions = {
        "tunnel": [
            ("connect_user", "VARCHAR"),
            (
                "ssh_opts",
                "VARCHAR DEFAULT "
                "'-o PubkeyAuthentication=no -o PreferredAuthentications=password'",
            ),
        ],
    }
    with engine.begin() as conn:
        for table, columns in additions.items():
            existing = {
                row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))
            }
            for name, ddl in columns:
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
