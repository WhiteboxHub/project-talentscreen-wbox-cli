"""Session management with context managers."""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy.orm import Session

from jobcli.storage.models import Database


@contextmanager
def get_db_session(database: Database) -> Generator[Session, None, None]:
    """Get database session with automatic cleanup.

    Usage:
        with get_db_session(db) as session:
            repo = JobRepository(session)
            job = repo.get(1)
            # session automatically committed and closed
    """
    session = database.get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def get_db_transaction(database: Database) -> Generator[Session, None, None]:
    """Get database session with explicit transaction.

    Usage:
        with get_db_transaction(db) as session:
            repo.update_status(session, job_id, status)
            # More operations...
            # All committed together or rolled back on error
    """
    session = database.get_session()
    try:
        session.begin()
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
