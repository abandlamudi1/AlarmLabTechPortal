"""SQLAlchemy ORM models for the Checkout tool.

Spike introduced in Slice D-part1 (Issue #48) to validate that SQLAlchemy 2.x
integrates cleanly with the existing Flask app before committing to the full
Slice D-part2 ORM rollout.

Design constraints:
- Read-only spike: only the Equipment model is defined; write operations
  still use the raw sqlite3 layer in db.py.
- No module-level engine or session — engine is created inside get_session()
  using the DB_PATH that tests can monkeypatch (same isolation strategy as
  the existing sqlite3 layer).
- Uses SQLAlchemy 2.x DeclarativeBase style.
"""
from __future__ import annotations

from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.pool import NullPool

# Module imported at init time; DB_PATH is re-read inside get_session() so that
# monkeypatch.setattr(checkout_db, "DB_PATH", ...) in tests is respected.
import tools.checkout.db as _checkout_db


class Base(DeclarativeBase):
    pass


class Equipment(Base):
    """ORM mirror of the `equipment` table defined in db.py._SCHEMA.

    Column names and types match the raw schema exactly so that SQLAlchemy
    queries operate on the same rows as the existing sqlite3 layer.
    """

    __tablename__ = "equipment"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    checked_out_by = Column(String, nullable=True)
    checked_out_at = Column(String, nullable=True)
    return_date = Column(String, nullable=True)
    jira_link = Column(String, nullable=True)

    def as_dict(self) -> dict:
        """Return a plain dict compatible with the sqlite3.Row interface used
        by the existing templates."""
        return {
            "id": self.id,
            "name": self.name,
            "checked_out_by": self.checked_out_by,
            "checked_out_at": self.checked_out_at,
            "return_date": self.return_date,
            "jira_link": self.jira_link,
        }


def get_session() -> Session:
    """Return a SQLAlchemy Session bound to the current checkout DB path.

    Reads DB_PATH from the checkout db module at call time so that test
    fixtures that monkeypatch checkout_db.DB_PATH are respected without
    requiring any additional test-setup steps.

    The caller is responsible for closing the session (use as a context
    manager: ``with get_session() as s:``).
    """
    db_path = _checkout_db.DB_PATH
    # NullPool disables connection pooling — each Session.close() releases the
    # underlying connection immediately. Required for per-call engine creation;
    # without it, pool connections accumulate across requests.
    engine = create_engine(f"sqlite:///{db_path}", echo=False, poolclass=NullPool)
    return Session(engine)
