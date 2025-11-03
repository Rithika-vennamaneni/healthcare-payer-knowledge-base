"""
Database connection and session management
"""

import os
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
import logging

from database.models import Base

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database connections and sessions"""
    
    def __init__(self, database_url: str = None, echo: bool = False):
        """
        Initialize database manager
        
        Args:
            database_url: Database connection URL (defaults to env var)
            echo: Whether to echo SQL statements
        """
        self.database_url = database_url or os.getenv(
            "DATABASE_URL",
            "postgresql://localhost:5432/payer_knowledge_base"
        )
        
        # Handle SQLite for development
        if self.database_url.startswith("sqlite"):
            self.engine = create_engine(
                self.database_url,
                echo=echo,
                connect_args={"check_same_thread": False}
            )
        else:
            # PostgreSQL with connection pooling
            self.engine = create_engine(
                self.database_url,
                echo=echo,
                poolclass=QueuePool,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,  # Verify connections before using
                pool_recycle=3600,  # Recycle connections after 1 hour
            )
        
        # Create session factory
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )
        
        logger.info(f"Database manager initialized with URL: {self._mask_password(self.database_url)}")
    
    def _mask_password(self, url: str) -> str:
        """Mask password in database URL for logging"""
        if "@" in url:
            parts = url.split("@")
            if ":" in parts[0]:
                user_pass = parts[0].split(":")
                return f"{user_pass[0]}:****@{parts[1]}"
        return url
    
    def create_tables(self):
        """Create all tables in the database"""
        logger.info("Creating database tables...")
        Base.metadata.create_all(bind=self.engine)
        logger.info("Database tables created successfully")
    
    def drop_tables(self):
        """Drop all tables (use with caution!)"""
        logger.warning("Dropping all database tables...")
        Base.metadata.drop_all(bind=self.engine)
        logger.info("Database tables dropped")
    
    def get_session(self) -> Session:
        """Get a new database session"""
        return self.SessionLocal()
    
    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        """
        Provide a transactional scope for database operations
        
        Usage:
            with db_manager.session_scope() as session:
                session.add(obj)
                # Automatically commits on success, rolls back on error
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()
    
    def health_check(self) -> bool:
        """Check if database connection is healthy"""
        try:
            with self.session_scope() as session:
                session.execute("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False


# Global database manager instance
_db_manager = None


def get_db_manager(database_url: str = None, echo: bool = False) -> DatabaseManager:
    """Get or create global database manager instance"""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager(database_url=database_url, echo=echo)
    return _db_manager


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for FastAPI to get database session
    
    Usage in FastAPI:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db_manager = get_db_manager()
    session = db_manager.get_session()
    try:
        yield session
    finally:
        session.close()


def init_database(database_url: str = None, drop_existing: bool = False):
    """
    Initialize database with tables
    
    Args:
        database_url: Database connection URL
        drop_existing: Whether to drop existing tables first
    """
    db_manager = get_db_manager(database_url=database_url)
    
    if drop_existing:
        db_manager.drop_tables()
    
    db_manager.create_tables()
    logger.info("Database initialized successfully")
