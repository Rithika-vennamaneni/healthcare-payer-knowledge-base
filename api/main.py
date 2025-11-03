"""
FastAPI backend for Healthcare Payer Knowledge Base
Provides REST API for chatbot, scraping, and data management
"""

import os
import logging
from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import FastAPI, Depends, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
load_dotenv()

from database.connection import get_db, get_db_manager
from database.models import Payer, PayerRule, Alert, ScrapeJob, RuleType
from rag.chatbot import create_chatbot
from rag.embeddings import EmbeddingGenerator, embed_rules
from scheduler.scrape_scheduler import ScrapeScheduler
from scheduler.change_detector import ChangeDetector

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Healthcare Payer Knowledge Base API",
    description="Dynamic knowledge base for healthcare payer rules with RAG-powered chatbot",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances
chatbot = None
scheduler = None
embedding_generator = None


# Pydantic models for API
class ChatQueryRequest(BaseModel):
    query: str = Field(..., description="User's question")
    session_id: Optional[str] = Field(None, description="Chat session ID for context")
    payer_name: Optional[str] = Field(None, description="Filter by payer name")
    rule_type: Optional[str] = Field(None, description="Filter by rule type")
    include_sources: bool = Field(True, description="Include source citations")


class ChatQueryResponse(BaseModel):
    response: str
    sources: List[dict]
    session_id: str
    query_id: int
    response_time_ms: float
    num_sources: int


class FeedbackRequest(BaseModel):
    query_id: int
    rating: int = Field(..., ge=1, le=5, description="Rating from 1-5")
    feedback_text: Optional[str] = None


class PayerResponse(BaseModel):
    id: int
    name: str
    ticker_symbol: Optional[str]
    provider_portal_url: Optional[str]
    market_share: Optional[float]
    priority: Optional[str]
    is_active: bool
    total_rules: int


class RuleResponse(BaseModel):
    id: int
    payer_name: str
    rule_type: str
    title: Optional[str]
    content: str
    version: int
    is_current: bool
    effective_date: Optional[str]
    source_url: Optional[str]
    created_at: str


class AlertResponse(BaseModel):
    id: int
    alert_type: str
    severity: str
    title: str
    message: str
    payer_name: Optional[str]
    created_at: str
    is_read: bool
    is_resolved: bool


class ScrapeJobResponse(BaseModel):
    id: int
    payer_name: Optional[str]
    job_type: str
    status: str
    started_at: Optional[str]
    completed_at: Optional[str]
    duration_seconds: Optional[float]
    pages_crawled: int
    documents_downloaded: int
    rules_created: int
    rules_updated: int
    changes_detected: int


class TriggerScrapeRequest(BaseModel):
    payer_id: int


class ScheduleScrapeRequest(BaseModel):
    payer_id: int
    schedule_type: str = Field(..., description="daily, weekly, or interval")
    hour: int = Field(2, ge=0, le=23)
    minute: int = Field(0, ge=0, le=59)
    day_of_week: Optional[str] = None
    interval_hours: Optional[int] = None


# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global chatbot, scheduler, embedding_generator
    
    logger.info("Starting Healthcare Payer Knowledge Base API...")
    
    # Initialize database
    db_manager = get_db_manager()
    db_manager.create_tables()
    
    # Initialize embedding generator
    try:
        embedding_generator = EmbeddingGenerator(provider="openai")
        logger.info("Embedding generator initialized")
    except Exception as e:
        logger.warning(f"Could not initialize embeddings: {e}")
    
    # Initialize chatbot
    try:
        chatbot = create_chatbot()
        logger.info("Chatbot initialized")
    except Exception as e:
        logger.warning(f"Could not initialize chatbot: {e}")
    
    # Initialize scheduler
    try:
        scheduler = ScrapeScheduler()
        scheduler.start()
        logger.info("Scheduler initialized")
    except Exception as e:
        logger.warning(f"Could not initialize scheduler: {e}")
    
    logger.info("API startup complete")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global scheduler
    
    if scheduler:
        scheduler.shutdown()
    
    logger.info("API shutdown complete")


# Health check endpoint
@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint"""
    db_healthy = get_db_manager().health_check()
    
    return {
        "status": "healthy" if db_healthy else "unhealthy",
        "timestamp": datetime.utcnow().isoformat(),
        "database": "connected" if db_healthy else "disconnected",
        "chatbot": "initialized" if chatbot else "not initialized",
        "scheduler": "running" if scheduler and scheduler.scheduler.running else "not running"
    }


# Chatbot endpoints
@app.post("/chat/query", response_model=ChatQueryResponse)
async def chat_query(
    request: ChatQueryRequest,
    db: Session = Depends(get_db)
):
    """
    Query the chatbot with a question about payer rules
    """
    if not chatbot:
        raise HTTPException(status_code=503, detail="Chatbot not initialized")
    
    try:
        result = chatbot.query(
            session=db,
            query_text=request.query,
            session_id=request.session_id,
            payer_name=request.payer_name,
            rule_type=request.rule_type,
            include_sources=request.include_sources
        )
        return result
    except Exception as e:
        logger.error(f"Chat query error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chat/history/{session_id}")
async def get_chat_history(
    session_id: str,
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get conversation history for a session"""
    if not chatbot:
        raise HTTPException(status_code=503, detail="Chatbot not initialized")
    
    history = chatbot.get_conversation_history(db, session_id, limit)
    return {"session_id": session_id, "history": history}


@app.post("/chat/feedback")
async def submit_feedback(
    request: FeedbackRequest,
    db: Session = Depends(get_db)
):
    """Submit feedback for a chat response"""
    if not chatbot:
        raise HTTPException(status_code=503, detail="Chatbot not initialized")
    
    chatbot.submit_feedback(
        db,
        request.query_id,
        request.rating,
        request.feedback_text
    )
    return {"status": "success", "message": "Feedback submitted"}


# Payer endpoints
@app.get("/payers", response_model=List[PayerResponse])
async def list_payers(
    active_only: bool = Query(True),
    db: Session = Depends(get_db)
):
    """List all payers"""
    query = db.query(Payer)
    
    if active_only:
        query = query.filter(Payer.is_active == True)
    
    payers = query.all()
    
    results = []
    for payer in payers:
        total_rules = db.query(PayerRule).filter(
            PayerRule.payer_id == payer.id,
            PayerRule.is_current == True
        ).count()
        
        results.append(PayerResponse(
            id=payer.id,
            name=payer.name,
            ticker_symbol=payer.ticker_symbol,
            provider_portal_url=payer.provider_portal_url,
            market_share=payer.market_share,
            priority=payer.priority,
            is_active=payer.is_active,
            total_rules=total_rules
        ))
    
    return results


@app.get("/payers/{payer_id}")
async def get_payer(
    payer_id: int,
    db: Session = Depends(get_db)
):
    """Get detailed information about a payer"""
    payer = db.query(Payer).filter(Payer.id == payer_id).first()
    
    if not payer:
        raise HTTPException(status_code=404, detail="Payer not found")
    
    # Get rule counts by type
    rule_counts = {}
    for rule_type in RuleType:
        count = db.query(PayerRule).filter(
            PayerRule.payer_id == payer_id,
            PayerRule.rule_type == rule_type,
            PayerRule.is_current == True
        ).count()
        rule_counts[rule_type.value] = count
    
    return {
        "id": payer.id,
        "name": payer.name,
        "ticker_symbol": payer.ticker_symbol,
        "base_domain": payer.base_domain,
        "provider_portal_url": payer.provider_portal_url,
        "market_share": payer.market_share,
        "priority": payer.priority,
        "is_active": payer.is_active,
        "rule_counts": rule_counts,
        "created_at": payer.created_at.isoformat(),
        "updated_at": payer.updated_at.isoformat()
    }


# Rule endpoints
@app.get("/rules", response_model=List[RuleResponse])
async def list_rules(
    payer_id: Optional[int] = Query(None),
    rule_type: Optional[str] = Query(None),
    current_only: bool = Query(True),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """List payer rules with filters"""
    query = db.query(PayerRule)
    
    if payer_id:
        query = query.filter(PayerRule.payer_id == payer_id)
    
    if rule_type:
        try:
            rule_type_enum = RuleType[rule_type.upper()]
            query = query.filter(PayerRule.rule_type == rule_type_enum)
        except KeyError:
            raise HTTPException(status_code=400, detail=f"Invalid rule_type: {rule_type}")
    
    if current_only:
        query = query.filter(PayerRule.is_current == True)
    
    rules = query.order_by(PayerRule.created_at.desc()).offset(offset).limit(limit).all()
    
    results = []
    for rule in rules:
        payer = db.query(Payer).filter(Payer.id == rule.payer_id).first()
        
        results.append(RuleResponse(
            id=rule.id,
            payer_name=payer.name if payer else "Unknown",
            rule_type=rule.rule_type.value,
            title=rule.title,
            content=rule.content[:500] + "..." if len(rule.content) > 500 else rule.content,
            version=rule.version,
            is_current=rule.is_current,
            effective_date=rule.effective_date.isoformat() if rule.effective_date else None,
            source_url=rule.source_url,
            created_at=rule.created_at.isoformat()
        ))
    
    return results


@app.get("/rules/{rule_id}")
async def get_rule(
    rule_id: int,
    include_history: bool = Query(False),
    db: Session = Depends(get_db)
):
    """Get detailed information about a specific rule"""
    rule = db.query(PayerRule).filter(PayerRule.id == rule_id).first()
    
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    payer = db.query(Payer).filter(Payer.id == rule.payer_id).first()
    
    result = {
        "id": rule.id,
        "payer_name": payer.name if payer else "Unknown",
        "payer_id": rule.payer_id,
        "rule_type": rule.rule_type.value,
        "rule_identifier": rule.rule_identifier,
        "title": rule.title,
        "content": rule.content,
        "summary": rule.summary,
        "version": rule.version,
        "is_current": rule.is_current,
        "effective_date": rule.effective_date.isoformat() if rule.effective_date else None,
        "expiration_date": rule.expiration_date.isoformat() if rule.expiration_date else None,
        "source_url": rule.source_url,
        "geographic_scope": rule.geographic_scope,
        "confidence_score": rule.confidence_score,
        "created_at": rule.created_at.isoformat(),
        "updated_at": rule.updated_at.isoformat()
    }
    
    if include_history and rule.rule_identifier:
        # Get all versions of this rule
        versions = db.query(PayerRule).filter(
            PayerRule.rule_identifier == rule.rule_identifier
        ).order_by(PayerRule.version.desc()).all()
        
        result["version_history"] = [
            {
                "version": v.version,
                "created_at": v.created_at.isoformat(),
                "is_current": v.is_current
            }
            for v in versions
        ]
    
    return result


# Alert endpoints
@app.get("/alerts", response_model=List[AlertResponse])
async def list_alerts(
    unread_only: bool = Query(False),
    severity: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """List alerts"""
    query = db.query(Alert)
    
    if unread_only:
        query = query.filter(Alert.is_read == False)
    
    if severity:
        query = query.filter(Alert.severity == severity)
    
    alerts = query.order_by(Alert.created_at.desc()).limit(limit).all()
    
    results = []
    for alert in alerts:
        payer = None
        if alert.payer_id:
            payer = db.query(Payer).filter(Payer.id == alert.payer_id).first()
        
        results.append(AlertResponse(
            id=alert.id,
            alert_type=alert.alert_type,
            severity=alert.severity,
            title=alert.title,
            message=alert.message,
            payer_name=payer.name if payer else None,
            created_at=alert.created_at.isoformat(),
            is_read=alert.is_read,
            is_resolved=alert.is_resolved
        ))
    
    return results


@app.post("/alerts/{alert_id}/mark-read")
async def mark_alert_read(
    alert_id: int,
    db: Session = Depends(get_db)
):
    """Mark an alert as read"""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.is_read = True
    alert.read_at = datetime.utcnow()
    db.commit()
    
    return {"status": "success", "message": "Alert marked as read"}


# Scraping endpoints
@app.post("/scrape/trigger")
async def trigger_scrape(
    request: TriggerScrapeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Trigger an immediate scrape for a payer"""
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")
    
    payer = db.query(Payer).filter(Payer.id == request.payer_id).first()
    if not payer:
        raise HTTPException(status_code=404, detail="Payer not found")
    
    # Trigger scrape in background
    job_id = scheduler.trigger_immediate_scrape(request.payer_id)
    
    return {
        "status": "started",
        "message": f"Scrape job started for {payer.name}",
        "job_id": job_id
    }


@app.post("/scrape/schedule")
async def schedule_scrape(
    request: ScheduleScrapeRequest,
    db: Session = Depends(get_db)
):
    """Schedule periodic scraping for a payer"""
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")
    
    payer = db.query(Payer).filter(Payer.id == request.payer_id).first()
    if not payer:
        raise HTTPException(status_code=404, detail="Payer not found")
    
    job_id = scheduler.schedule_payer_scrape(
        payer_id=request.payer_id,
        schedule_type=request.schedule_type,
        hour=request.hour,
        minute=request.minute,
        day_of_week=request.day_of_week,
        interval_hours=request.interval_hours
    )
    
    return {
        "status": "scheduled",
        "message": f"Scraping scheduled for {payer.name}",
        "job_id": job_id
    }


@app.get("/scrape/jobs", response_model=List[ScrapeJobResponse])
async def list_scrape_jobs(
    payer_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """List scrape job history"""
    query = db.query(ScrapeJob)
    
    if payer_id:
        query = query.filter(ScrapeJob.payer_id == payer_id)
    
    if status:
        query = query.filter(ScrapeJob.status == status)
    
    jobs = query.order_by(ScrapeJob.started_at.desc()).limit(limit).all()
    
    results = []
    for job in jobs:
        payer = None
        if job.payer_id:
            payer = db.query(Payer).filter(Payer.id == job.payer_id).first()
        
        results.append(ScrapeJobResponse(
            id=job.id,
            payer_name=payer.name if payer else None,
            job_type=job.job_type,
            status=job.status,
            started_at=job.started_at.isoformat() if job.started_at else None,
            completed_at=job.completed_at.isoformat() if job.completed_at else None,
            duration_seconds=job.duration_seconds,
            pages_crawled=job.pages_crawled,
            documents_downloaded=job.documents_downloaded,
            rules_created=job.rules_created,
            rules_updated=job.rules_updated,
            changes_detected=job.changes_detected
        ))
    
    return results


# Embedding management endpoints
@app.post("/embeddings/generate")
async def generate_embeddings(
    background_tasks: BackgroundTasks,
    force_reembed: bool = Query(False),
    db: Session = Depends(get_db)
):
    """Generate embeddings for all rules"""
    if not embedding_generator:
        raise HTTPException(status_code=503, detail="Embedding generator not initialized")
    
    # Run in background
    def generate():
        count = embed_rules(db, embedding_generator, force_reembed=force_reembed)
        logger.info(f"Generated embeddings for {count} rules")
    
    background_tasks.add_task(generate)
    
    return {
        "status": "started",
        "message": "Embedding generation started in background"
    }


# Statistics endpoint
@app.get("/stats")
async def get_statistics(db: Session = Depends(get_db)):
    """Get system statistics"""
    from sqlalchemy import func
    
    total_payers = db.query(Payer).filter(Payer.is_active == True).count()
    total_rules = db.query(PayerRule).filter(PayerRule.is_current == True).count()
    total_alerts = db.query(Alert).filter(Alert.is_read == False).count()
    
    recent_jobs = db.query(ScrapeJob).filter(
        ScrapeJob.completed_at >= datetime.utcnow() - timedelta(days=7)
    ).count()
    
    # Rules by type
    rules_by_type = {}
    for rule_type in RuleType:
        count = db.query(PayerRule).filter(
            PayerRule.rule_type == rule_type,
            PayerRule.is_current == True
        ).count()
        rules_by_type[rule_type.value] = count
    
    return {
        "total_payers": total_payers,
        "total_rules": total_rules,
        "unread_alerts": total_alerts,
        "scrape_jobs_last_7_days": recent_jobs,
        "rules_by_type": rules_by_type,
        "timestamp": datetime.utcnow().isoformat()
    }


# Serve Frontend
frontend_path = Path(__file__).parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")
    
    @app.get("/")
    async def serve_frontend():
        """Serve the frontend HTML"""
        return FileResponse(str(frontend_path / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
