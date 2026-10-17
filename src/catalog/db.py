import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base


def database_url() -> str:
    return os.getenv("DATABASE_URL", "sqlite:///./catalog.db")


def make_engine(url: str | None = None):
    value = url or database_url()
    kwargs: dict[str, Any] = {"future": True}
    if value.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(value, **kwargs)


class Database:
    def __init__(self, url: str | None = None):
        self.engine = make_engine(url)
        self.Session = sessionmaker(self.engine, class_=Session, expire_on_commit=False)
        self.create_all()
        self.ensure_fts()

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)

    def ensure_fts(self) -> None:
        if self.engine.dialect.name == "sqlite":
            with self.engine.begin() as conn:
                conn.exec_driver_sql(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(text, content='')"
                )

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


_default: Database | None = None


def get_database() -> Database:
    global _default
    if _default is None:
        _default = Database()
    return _default
