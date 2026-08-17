"""SQLAlchemy engine and session helpers."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Session:
    return SessionLocal()


def ensure_schema() -> None:
    """Add columns introduced after the first create_all (Postgres + SQLite).

    Each statement runs in its own transaction. On Postgres, a failed ALTER
    (e.g. column already exists) aborts the whole transaction, so bundling
    them would skip later columns such as services.image_url.
    """
    stmts = [
        "ALTER TABLE tickets ADD COLUMN phone VARCHAR(32) DEFAULT ''",
        "ALTER TABLE tickets ADD COLUMN preferred_call_window VARCHAR(128) DEFAULT ''",
        "ALTER TABLE services ADD COLUMN image_url VARCHAR(256) DEFAULT ''",
        "ALTER TABLE services ADD COLUMN price_cents INTEGER DEFAULT 0",
        "ALTER TABLE services ADD COLUMN currency VARCHAR(8) DEFAULT 'USD'",
        "ALTER TABLE services ADD COLUMN pay_when VARCHAR(32) DEFAULT 'none'",
        "ALTER TABLE services ADD COLUMN fulfillment VARCHAR(16) DEFAULT 'online'",
        "ALTER TABLE services ADD COLUMN location_text VARCHAR(512) DEFAULT ''",
        "ALTER TABLE appointments ADD COLUMN payment_due_at TIMESTAMPTZ",
        "ALTER TABLE appointments ADD COLUMN payment_due_at DATETIME",
        "ALTER TABLE appointments ADD COLUMN stripe_checkout_session_id VARCHAR(128) DEFAULT ''",
    ]
    for sql in stmts:
        try:
            with engine.begin() as conn:
                conn.exec_driver_sql(sql)
        except Exception:
            pass
