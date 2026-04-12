"""SQLAlchemy models for JobCLI."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

from jobcli.core.schemas import ATSType, ApplicationStatus, ExecutionPhase, SelectorType

Base = declarative_base()


class JobModel(Base):
    """Job table."""

    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String(1000), nullable=False, unique=True)
    title = Column(String(500))
    company = Column(String(500))
    location = Column(String(500))
    description = Column(Text)
    ats_type = Column(Enum(ATSType), default=ATSType.UNKNOWN)
    status = Column(Enum(ApplicationStatus), default=ApplicationStatus.PENDING)
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
    metadata = Column(JSON)
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


class Database:
    """Database connection manager."""

    def __init__(self, database_url: str = "sqlite:///~/.jobcli/jobcli.db") -> None:
        """Initialize database connection."""
        self.engine = create_engine(database_url, echo=False)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def create_tables(self) -> None:
        """Create all tables."""
        Base.metadata.create_all(bind=self.engine)

    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

    def drop_tables(self) -> None:
        """Drop all tables (for testing)."""
        Base.metadata.drop_all(bind=self.engine)
