"""
Scheduler for periodic payer portal scraping
Supports configurable schedules and automatic change detection
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from database.models import Payer, ScrapeJob
from database.connection import get_db_manager
from payer_portal_crawler import PayerPortalCrawler
from scheduler.change_detector import ChangeDetector

logger = logging.getLogger(__name__)


class ScrapeScheduler:
    """
    Manages scheduled scraping jobs for payer portals
    """
    
    def __init__(self, database_url: str = None):
        """
        Initialize the scheduler
        
        Args:
            database_url: Database connection URL
        """
        self.db_manager = get_db_manager(database_url=database_url)
        self.scheduler = BackgroundScheduler(
            job_defaults={
                'coalesce': True,  # Combine multiple pending executions
                'max_instances': 1,  # Only one instance per job
                'misfire_grace_time': 300  # 5 minutes grace period
            }
        )
        self.change_detector = ChangeDetector()
        
        logger.info("Scrape scheduler initialized")
    
    def start(self):
        """Start the scheduler"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started")
    
    def shutdown(self, wait: bool = True):
        """Stop the scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=wait)
            logger.info("Scheduler stopped")
    
    def schedule_payer_scrape(
        self,
        payer_id: int,
        schedule_type: str = "daily",
        hour: int = 2,
        minute: int = 0,
        day_of_week: str = None,
        interval_hours: int = None
    ) -> str:
        """
        Schedule periodic scraping for a specific payer
        
        Args:
            payer_id: Database ID of the payer
            schedule_type: Type of schedule (daily, weekly, interval)
            hour: Hour to run (0-23) for daily/weekly
            minute: Minute to run (0-59)
            day_of_week: Day for weekly schedule (mon, tue, etc.)
            interval_hours: Hours between runs for interval schedule
            
        Returns:
            Job ID
        """
        with self.db_manager.session_scope() as session:
            payer = session.query(Payer).filter_by(id=payer_id).first()
            if not payer:
                raise ValueError(f"Payer {payer_id} not found")
            
            job_id = f"scrape_payer_{payer_id}"
            
            # Remove existing job if present
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
            
            # Create appropriate trigger
            if schedule_type == "daily":
                trigger = CronTrigger(hour=hour, minute=minute)
            elif schedule_type == "weekly":
                if not day_of_week:
                    day_of_week = "mon"
                trigger = CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute)
            elif schedule_type == "interval":
                if not interval_hours:
                    interval_hours = 24
                trigger = IntervalTrigger(hours=interval_hours)
            else:
                raise ValueError(f"Invalid schedule_type: {schedule_type}")
            
            # Schedule the job
            self.scheduler.add_job(
                func=self._execute_scrape_job,
                trigger=trigger,
                id=job_id,
                name=f"Scrape {payer.name}",
                args=[payer_id],
                replace_existing=True
            )
            
            logger.info(f"Scheduled {schedule_type} scrape for {payer.name} (ID: {payer_id})")
            return job_id
    
    def schedule_all_payers(
        self,
        priority_schedules: Dict[str, Dict] = None
    ):
        """
        Schedule scraping for all active payers based on priority
        
        Args:
            priority_schedules: Custom schedules per priority level
                Example: {
                    "high": {"schedule_type": "daily", "hour": 2},
                    "medium": {"schedule_type": "weekly", "day_of_week": "mon"},
                    "low": {"schedule_type": "weekly", "day_of_week": "sun"}
                }
        """
        if priority_schedules is None:
            priority_schedules = {
                "high": {"schedule_type": "daily", "hour": 2},
                "medium": {"schedule_type": "weekly", "day_of_week": "mon", "hour": 3},
                "low": {"schedule_type": "weekly", "day_of_week": "sun", "hour": 4}
            }
        
        with self.db_manager.session_scope() as session:
            payers = session.query(Payer).filter_by(is_active=True).all()
            
            for payer in payers:
                priority = payer.priority or "medium"
                schedule_config = priority_schedules.get(priority, priority_schedules["medium"])
                
                try:
                    self.schedule_payer_scrape(payer.id, **schedule_config)
                except Exception as e:
                    logger.error(f"Failed to schedule {payer.name}: {e}")
        
        logger.info(f"Scheduled scraping for all active payers")
    
    def trigger_immediate_scrape(self, payer_id: int) -> int:
        """
        Trigger an immediate scrape for a payer (bypassing schedule)
        
        Args:
            payer_id: Database ID of the payer
            
        Returns:
            Scrape job ID
        """
        logger.info(f"Triggering immediate scrape for payer {payer_id}")
        return self._execute_scrape_job(payer_id)
    
    def _execute_scrape_job(self, payer_id: int) -> int:
        """
        Execute a scraping job for a specific payer
        
        Args:
            payer_id: Database ID of the payer
            
        Returns:
            Scrape job ID
        """
        start_time = datetime.utcnow()
        job_id = None
        payer_name = None
        
        with self.db_manager.session_scope() as session:
            payer = session.query(Payer).filter_by(id=payer_id).first()
            if not payer:
                logger.error(f"Payer {payer_id} not found")
                return None
            
            # Store payer name before session closes
            payer_name = payer.name
            
            # Create scrape job record
            scrape_job = ScrapeJob(
                payer_id=payer_id,
                job_type="scheduled",
                status="running",
                started_at=start_time
            )
            session.add(scrape_job)
            session.flush()
            job_id = scrape_job.id
            
            logger.info(f"Starting scrape job {job_id} for {payer_name}")
        
        # Execute the scrape
        crawler = None
        try:
            # Get payer key from name (convert to lowercase with underscores)
            payer_key = payer_name.lower().replace(" ", "_").replace("/", "_")
            
            # Map common payer names to crawler keys
            payer_key_map = {
                "united_healthcare": "united_healthcare",
                "anthem_elevance_health": "anthem",
                "aetna_(cvs_health)": "aetna",
                "aetna": "aetna"
            }
            payer_key = payer_key_map.get(payer_key, payer_key)
            
            # Initialize crawler
            crawler = PayerPortalCrawler(headless=True)
            
            # Check if payer is configured in crawler
            if payer_key not in crawler.payer_configs:
                raise ValueError(f"Payer {payer_key} not configured in crawler")
            
            # Perform the crawl
            crawl_results = crawler.crawl_payer(payer_key)
            
            # Process results and detect changes
            with self.db_manager.session_scope() as session:
                scrape_job = session.query(ScrapeJob).filter_by(id=job_id).first()
                
                if 'error' in crawl_results:
                    scrape_job.status = "failed"
                    scrape_job.error_message = crawl_results['error']
                else:
                    # Detect changes
                    changes = self.change_detector.process_crawl_results(
                        session, payer_id, crawl_results
                    )
                    
                    # Update job with results
                    scrape_job.status = "completed"
                    scrape_job.pages_crawled = crawl_results.get('metadata', {}).get('total_pages_crawled', 0)
                    scrape_job.documents_downloaded = crawl_results.get('metadata', {}).get('total_pdfs_downloaded', 0)
                    scrape_job.rules_created = changes.get('rules_created', 0)
                    scrape_job.rules_updated = changes.get('rules_updated', 0)
                    scrape_job.changes_detected = changes.get('total_changes', 0)
                    scrape_job.results = {
                        'crawl_summary': crawl_results.get('metadata', {}),
                        'changes_summary': changes
                    }
                
                scrape_job.completed_at = datetime.utcnow()
                scrape_job.duration_seconds = (scrape_job.completed_at - start_time).total_seconds()
                
                logger.info(f"Scrape job {job_id} completed: {scrape_job.status}")
        
        except Exception as e:
            logger.error(f"Scrape job {job_id} failed: {e}", exc_info=True)
            
            with self.db_manager.session_scope() as session:
                scrape_job = session.query(ScrapeJob).filter_by(id=job_id).first()
                scrape_job.status = "failed"
                scrape_job.error_message = str(e)
                scrape_job.completed_at = datetime.utcnow()
                scrape_job.duration_seconds = (scrape_job.completed_at - start_time).total_seconds()
        
        finally:
            if crawler:
                crawler.close()
        
        return job_id
    
    def get_scheduled_jobs(self) -> List[Dict]:
        """
        Get list of all scheduled jobs
        
        Returns:
            List of job information dictionaries
        """
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
                'trigger': str(job.trigger)
            })
        return jobs
    
    def remove_schedule(self, job_id: str) -> bool:
        """
        Remove a scheduled job
        
        Args:
            job_id: Job ID to remove
            
        Returns:
            True if removed, False if not found
        """
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed scheduled job: {job_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove job {job_id}: {e}")
            return False
    
    def get_job_history(
        self,
        payer_id: int = None,
        limit: int = 50,
        status: str = None
    ) -> List[ScrapeJob]:
        """
        Get history of scrape jobs
        
        Args:
            payer_id: Filter by payer ID (optional)
            limit: Maximum number of jobs to return
            status: Filter by status (optional)
            
        Returns:
            List of ScrapeJob objects
        """
        with self.db_manager.session_scope() as session:
            query = session.query(ScrapeJob)
            
            if payer_id:
                query = query.filter_by(payer_id=payer_id)
            
            if status:
                query = query.filter_by(status=status)
            
            jobs = query.order_by(ScrapeJob.started_at.desc()).limit(limit).all()
            
            # Detach from session
            session.expunge_all()
            return jobs


def setup_default_schedules(database_url: str = None):
    """
    Set up default scraping schedules for all payers
    
    Args:
        database_url: Database connection URL
    """
    scheduler = ScrapeScheduler(database_url=database_url)
    scheduler.schedule_all_payers()
    scheduler.start()
    
    logger.info("Default schedules configured")
    logger.info(f"Scheduled jobs: {len(scheduler.get_scheduled_jobs())}")
    
    return scheduler


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Setup and start scheduler
    scheduler = setup_default_schedules(database_url="sqlite:///payer_knowledge_base.db")
    
    print("\nScheduled Jobs:")
    for job in scheduler.get_scheduled_jobs():
        print(f"  - {job['name']}: Next run at {job['next_run_time']}")
    
    print("\nScheduler is running. Press Ctrl+C to stop.")
    
    try:
        # Keep the script running
        import time
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\nShutting down scheduler...")
        scheduler.shutdown()
