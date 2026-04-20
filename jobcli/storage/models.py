"""SQLAlchemy models for JobCLI."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Column, DateTime, Enum, Float, Integer, String, Text, create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

from jobcli.core.schemas import ATSType, ApplicationStatus, ExecutionPhase, SelectorType

Base = declarative_base()


class JobModel(Base):
    """Job table."""

    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String(1000), nullable=False, unique=True)
    resolved_url = Column(String(1000), nullable=True)
    title = Column(String(500))
    company = Column(String(500))
    location = Column(String(500))
    description = Column(Text)
    ats_type = Column(Enum(ATSType), default=ATSType.UNKNOWN)
    status = Column(Enum(ApplicationStatus), default=ApplicationStatus.PENDING)
    score = Column(Float, nullable=True)
    scan_source = Column(String(100), nullable=True)
    evaluation_report_path = Column(String(1000), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class ApplicationLogModel(Base):
    """Application log entries."""

    __tablename__ = "application_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, nullable=False)
    phase = Column(Enum(ExecutionPhase))
    action = Column(String(100))
    success = Column(Boolean)
    error = Column(Text)
    log_metadata = Column(JSON)
    screenshot_path = Column(String(1000))
    dom_snapshot = Column(JSON)
    timestamp = Column(DateTime, default=datetime.now)


class LearnedLocatorModel(Base):
    """Learned locators from human feedback."""

    __tablename__ = "learned_locators"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ats_type = Column(Enum(ATSType), nullable=False)
    selector = Column(String(1000), nullable=False)
    selector_type = Column(Enum(SelectorType), nullable=False)
    purpose = Column(String(200), nullable=False)
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    confidence_score = Column(Float, default=0.5)
    domain_pattern = Column(String(500))
    url_pattern = Column(String(500))
    notes = Column(Text)
    # First job this locator was learned/seen on (oldest originator). Nullable
    # so cross-job reuse still works on rows created before this column existed.
    first_job_id = Column(Integer, nullable=True)
    # Most recent job that reinforced this locator (last writer wins).
    last_job_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    created_by = Column(String(50), default="human")


class UserDataModel(Base):
    """User resume and preferences."""

    __tablename__ = "user_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    data_type = Column(String(50), nullable=False, unique=True)  # 'resume', 'questions', etc.
    data = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class ConfigModel(Base):
    """Application configuration."""

    __tablename__ = "config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(200), nullable=False, unique=True)
    value = Column(Text, nullable=False)
    encrypted = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class FieldAnswerModel(Base):
    """Memory of answers provided for specific fields across ATS platforms."""

    __tablename__ = "field_answers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    field_label = Column(String(500), nullable=False)
    normalized_label = Column(String(500))
    value = Column(Text, nullable=False)
    ats_type = Column(Enum(ATSType), default=ATSType.UNKNOWN)
    field_type = Column(String(50), default="text")
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    source = Column(String(50), default="human")
    # The job the answer was first learned on, and the most recent job that
    # reused/updated it.  Both nullable so the row is still valid across jobs.
    first_job_id = Column(Integer, nullable=True)
    last_job_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class InteractionLogModel(Base):
    """Log of all Playwright interaction attempts to learn what strategies work."""

    __tablename__ = "interaction_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ats_type = Column(Enum(ATSType), default=ATSType.UNKNOWN)
    action_type = Column(String(50), nullable=False)
    field_label = Column(String(500))
    selector = Column(String(1000))
    strategy_name = Column(String(100))
    success = Column(Boolean, default=False)
    page_url_pattern = Column(String(500))
    # Which job this interaction happened on.  Append-only — never rewritten
    # so the full per-job attempt history survives.
    job_id = Column(Integer, nullable=True)
    timestamp = Column(DateTime, default=datetime.now)


class DropdownStrategyModel(Base):
    """Strategies that successfully interacted with dropdowns on specific ATS platforms."""

    __tablename__ = "dropdown_strategies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ats_type = Column(Enum(ATSType), default=ATSType.UNKNOWN)
    field_label = Column(String(500), nullable=False)
    strategy_name = Column(String(100), nullable=False)
    options_json = Column(JSON, nullable=True)
    selected_value = Column(String(500), nullable=True)
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    first_job_id = Column(Integer, nullable=True)
    last_job_id = Column(Integer, nullable=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class Database:
    """Database connection manager."""

    def __init__(self, database_url: str = "sqlite:///~/.jobcli/jobcli.db") -> None:
        """Initialize database connection."""
        self.engine = create_engine(database_url, echo=False)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def create_tables(self) -> None:
        """Create all tables."""
        Base.metadata.create_all(bind=self.engine)
        self._migrate_sqlite_schema()

    def _migrate_sqlite_schema(self) -> None:
        """Lightweight additive migrations for SQLite (no Alembic)."""
        if not str(self.engine.url).startswith("sqlite"):
            return
        try:
            inspector = inspect(self.engine)
            table_names = set(inspector.get_table_names())
            if "jobs" in table_names:
                cols = {c["name"] for c in inspector.get_columns("jobs")}
                if "resolved_url" not in cols:
                    with self.engine.begin() as conn:
                        conn.execute(text("ALTER TABLE jobs ADD COLUMN resolved_url VARCHAR(1000)"))

            # Back-fill job_id linkage columns on the memory tables so that
            # rows written from now on carry the originating job, while older
            # rows simply have NULL and remain valid for cross-job reuse.
            additive: dict[str, list[tuple[str, str]]] = {
                "field_answers": [
                    ("first_job_id", "INTEGER"),
                    ("last_job_id", "INTEGER"),
                ],
                "learned_locators": [
                    ("first_job_id", "INTEGER"),
                    ("last_job_id", "INTEGER"),
                ],
                "interaction_log": [
                    ("job_id", "INTEGER"),
                ],
                "dropdown_strategies": [
                    ("first_job_id", "INTEGER"),
                    ("last_job_id", "INTEGER"),
                ],
            }
            for table, pending in additive.items():
                if table not in table_names:
                    continue
                existing = {c["name"] for c in inspector.get_columns(table)}
                with self.engine.begin() as conn:
                    for col_name, col_type in pending:
                        if col_name not in existing:
                            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"))
        except Exception:
            pass

    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

    def drop_tables(self) -> None:
        """Drop all tables (for testing)."""
        Base.metadata.drop_all(bind=self.engine)
