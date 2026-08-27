# core/database.py
import os
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from core.config import settings

DATABASE_URL = settings.DATABASE_URL or os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db() -> Generator[Session, None, None]:
    """Dependency helper yielding a scoped database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

