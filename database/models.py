"""
Database Models for Healthcare Payer Knowledge Base
Supports versioning, change tracking, and efficient RAG retrieval
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime,
    ForeignKey, Index, Enum as SQLEnum, ARRAY, JSON
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
from enum import Enum

# Use JSON for SQLite compatibility, JSON for PostgreSQL
try:
    from sqlalchemy.dialects.postgresql import JSON as JSONType
except ImportError:
    JSONType = JSON

Base = declarative_base()


class RuleType(Enum):
    """Types of payer rules"""
    PRIOR_AUTHORIZATION = "prior_authorization"
    TIMELY_FILING = "timely_filing"
    APPEALS = "appeals"
    CLAIM_SUBMISSION = "claim_submission"
    COVERAGE_POLICY = "coverage_policy"
    NETWORK_REQUIREMENTS = "network_requirements"
    OTHER = "other"


class ChangeType(Enum):
    """Types of changes detected"""
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    CONTENT_MODIFIED = "content_modified"
    DATE_MODIFIED = "date_modified"
    METADATA_MODIFIED = "metadata_modified"


class Payer(Base):
    """Healthcare payer/insurance company"""
    __tablename__ = "payers"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    ticker_symbol = Column(String(10), nullable=True)
    base_domain = Column(String(255), nullable=True)
    provider_portal_url = Column(String(512), nullable=True)
    market_share = Column(Float, nullable=True)
    priority = Column(String(20), nullable=True)  # high, medium, low
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Additional configuration stored as JSON
    config = Column(JSON, nullable=True)  # Scraping config, rate limits, etc.
    
    # Relationships
    rules = relationship("PayerRule", back_populates="payer", cascade="all, delete-orphan")
    documents = relationship("PayerDocument", back_populates="payer", cascade="all, delete-orphan")
    scrape_jobs = relationship("ScrapeJob", back_populates="payer", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Payer(id={self.id}, name='{self.name}')>"


class PayerRule(Base):
    """
    Versioned payer rules with change tracking
    Each rule update creates a new version
    """
    __tablename__ = "payer_rules"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    payer_id = Column(Integer, ForeignKey("payers.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Rule identification
    rule_type = Column(SQLEnum(RuleType), nullable=False, index=True)
    rule_identifier = Column(String(255), nullable=True, index=True)  # Unique identifier for tracking versions
    
    # Rule content
    title = Column(String(512), nullable=True)
    content = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)  # AI-generated summary for quick reference
    
    # Versioning
    version = Column(Integer, default=1, nullable=False)
    is_current = Column(Boolean, default=True, nullable=False, index=True)
    supersedes_id = Column(Integer, ForeignKey("payer_rules.id"), nullable=True)  # Previous version
    
    # Dates
    effective_date = Column(DateTime, nullable=True, index=True)
    expiration_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Source information
    source_url = Column(String(1024), nullable=True)
    source_document_id = Column(Integer, ForeignKey("payer_documents.id"), nullable=True)
    source_page_number = Column(Integer, nullable=True)
    
    # Geographic scope
    geographic_scope = Column(JSON, nullable=True)  # {"states": ["CA", "NY"], "regions": ["West"]}
    
    # Vector embedding for RAG (stored as JSON array for SQLite compatibility)
    embedding = Column(JSON, nullable=True)  # Store vector embeddings as JSON array
    embedding_model = Column(String(100), nullable=True)  # Model used for embedding
    
    # Additional data
    extra_metadata = Column(JSON, nullable=True)  # Additional structured data
    confidence_score = Column(Float, nullable=True)  # Extraction confidence
    
    # Relationships
    payer = relationship("Payer", back_populates="rules")
    source_document = relationship("PayerDocument", foreign_keys=[source_document_id])
    supersedes = relationship("PayerRule", remote_side=[id], foreign_keys=[supersedes_id])
    change_logs = relationship("ChangeLog", back_populates="rule", cascade="all, delete-orphan")
    
    # Indexes for efficient querying
    __table_args__ = (
        Index("idx_payer_rule_type_current", "payer_id", "rule_type", "is_current"),
        Index("idx_rule_identifier_version", "rule_identifier", "version"),
        Index("idx_effective_date", "effective_date"),
    )
    
    def __repr__(self):
        return f"<PayerRule(id={self.id}, payer_id={self.payer_id}, type={self.rule_type}, version={self.version})>"


class PayerDocument(Base):
    """
    Source documents (PDFs, web pages) from payer portals
    """
    __tablename__ = "payer_documents"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    payer_id = Column(Integer, ForeignKey("payers.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Document identification
    document_type = Column(String(50), nullable=False)  # pdf, webpage, manual, etc.
    title = Column(String(512), nullable=True)
    filename = Column(String(512), nullable=True)
    
    # Source
    source_url = Column(String(1024), nullable=False, index=True)
    local_file_path = Column(String(1024), nullable=True)
    
    # Content
    raw_content = Column(Text, nullable=True)  # Extracted text
    structured_content = Column(JSON, nullable=True)  # Parsed structured data
    
    # Document metadata
    file_size = Column(Integer, nullable=True)
    page_count = Column(Integer, nullable=True)
    file_hash = Column(String(64), nullable=True, index=True)  # SHA-256 for change detection
    
    # Dates
    document_date = Column(DateTime, nullable=True)
    downloaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_checked_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Status
    is_current = Column(Boolean, default=True, nullable=False)
    processing_status = Column(String(50), default="pending", nullable=False)  # pending, processing, completed, failed
    
    # Additional data
    extra_metadata = Column(JSON, nullable=True)
    
    # Relationships
    payer = relationship("Payer", back_populates="documents")
    rules = relationship("PayerRule", foreign_keys=[PayerRule.source_document_id])
    
    __table_args__ = (
        Index("idx_payer_document_type", "payer_id", "document_type"),
        Index("idx_file_hash", "file_hash"),
    )
    
    def __repr__(self):
        return f"<PayerDocument(id={self.id}, payer_id={self.payer_id}, title='{self.title}')>"


class ChangeLog(Base):
    """
    Audit trail for all changes to payer rules
    """
    __tablename__ = "change_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(Integer, ForeignKey("payer_rules.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Change details
    change_type = Column(SQLEnum(ChangeType), nullable=False, index=True)
    old_value = Column(JSON, nullable=True)  # Previous state
    new_value = Column(JSON, nullable=True)  # New state
    diff = Column(JSON, nullable=True)  # Structured diff
    
    # Change metadata
    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    detected_by = Column(String(100), nullable=True)  # scraper, manual, api, etc.
    
    # Alert status
    alert_sent = Column(Boolean, default=False, nullable=False)
    alert_sent_at = Column(DateTime, nullable=True)
    
    # Additional context
    notes = Column(Text, nullable=True)
    extra_metadata = Column(JSON, nullable=True)
    
    # Relationships
    rule = relationship("PayerRule", back_populates="change_logs")
    
    __table_args__ = (
        Index("idx_change_type_date", "change_type", "changed_at"),
        Index("idx_change_alert_status", "alert_sent", "changed_at"),
    )
    
    def __repr__(self):
        return f"<ChangeLog(id={self.id}, rule_id={self.rule_id}, type={self.change_type})>"


class ScrapeJob(Base):
    """
    Track scraping jobs and their status
    """
    __tablename__ = "scrape_jobs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    payer_id = Column(Integer, ForeignKey("payers.id", ondelete="CASCADE"), nullable=True, index=True)
    
    # Job details
    job_type = Column(String(50), nullable=False)  # full_crawl, incremental, targeted
    status = Column(String(50), default="pending", nullable=False, index=True)  # pending, running, completed, failed
    
    # Timing
    scheduled_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    
    # Results
    pages_crawled = Column(Integer, default=0)
    documents_downloaded = Column(Integer, default=0)
    rules_extracted = Column(Integer, default=0)
    rules_updated = Column(Integer, default=0)
    rules_created = Column(Integer, default=0)
    changes_detected = Column(Integer, default=0)
    
    # Error handling
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    
    # Metadata
    config = Column(JSON, nullable=True)  # Job-specific configuration
    results = Column(JSON, nullable=True)  # Detailed results
    
    # Relationships
    payer = relationship("Payer", back_populates="scrape_jobs")
    
    __table_args__ = (
        Index("idx_status_scheduled", "status", "scheduled_at"),
        Index("idx_payer_completed", "payer_id", "completed_at"),
    )
    
    def __repr__(self):
        return f"<ScrapeJob(id={self.id}, payer_id={self.payer_id}, status='{self.status}')>"


class ChatSession(Base):
    """
    Track chat sessions for analytics and context
    """
    __tablename__ = "chat_sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), unique=True, nullable=False, index=True)
    
    # User info (optional)
    user_id = Column(String(100), nullable=True, index=True)
    user_email = Column(String(255), nullable=True)
    
    # Session metadata
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_activity_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Relationships
    queries = relationship("ChatQuery", back_populates="session", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<ChatSession(id={self.id}, session_id='{self.session_id}')>"


class ChatQuery(Base):
    """
    Individual chat queries and responses for RAG system
    """
    __tablename__ = "chat_queries"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Query details
    query_text = Column(Text, nullable=False)
    query_embedding = Column(JSON, nullable=True)  # Store as JSON array for SQLite compatibility
    
    # Response
    response_text = Column(Text, nullable=True)
    sources_cited = Column(JSON, nullable=True)  # List of rule IDs and documents used
    
    # RAG metadata
    retrieval_method = Column(String(50), nullable=True)  # semantic, keyword, hybrid
    num_sources_retrieved = Column(Integer, nullable=True)
    confidence_score = Column(Float, nullable=True)
    
    # Timing
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    response_time_ms = Column(Float, nullable=True)
    
    # Feedback
    user_rating = Column(Integer, nullable=True)  # 1-5 stars
    user_feedback = Column(Text, nullable=True)
    
    # Additional data
    extra_metadata = Column(JSON, nullable=True)
    
    # Relationships
    session = relationship("ChatSession", back_populates="queries")
    
    __table_args__ = (
        Index("idx_session_created", "session_id", "created_at"),
    )
    
    def __repr__(self):
        return f"<ChatQuery(id={self.id}, session_id={self.session_id})>"


class Alert(Base):
    """
    Alerts for rule changes and system events
    """
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Alert details
    alert_type = Column(String(50), nullable=False, index=True)  # rule_change, scrape_failure, etc.
    severity = Column(String(20), nullable=False, index=True)  # low, medium, high, critical
    title = Column(String(512), nullable=False)
    message = Column(Text, nullable=False)
    
    # Related entities
    payer_id = Column(Integer, ForeignKey("payers.id"), nullable=True)
    rule_id = Column(Integer, ForeignKey("payer_rules.id"), nullable=True)
    change_log_id = Column(Integer, ForeignKey("change_logs.id"), nullable=True)
    
    # Status
    is_read = Column(Boolean, default=False, nullable=False)
    is_resolved = Column(Boolean, default=False, nullable=False)
    
    # Timing
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    read_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    
    # Notification
    notification_sent = Column(Boolean, default=False, nullable=False)
    notification_channels = Column(JSON, nullable=True)  # email, slack, etc.
    
    # Additional data
    extra_metadata = Column(JSON, nullable=True)
    
    __table_args__ = (
        Index("idx_alert_status", "is_read", "is_resolved", "created_at"),
        Index("idx_severity_created", "severity", "created_at"),
    )
    
    def __repr__(self):
        return f"<Alert(id={self.id}, type='{self.alert_type}', severity='{self.severity}')>"
