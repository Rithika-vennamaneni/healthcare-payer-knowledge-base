"""Check if crawler has run and what data exists"""
from database.connection import get_db
from database.models import Payer, PayerRule, ScrapeJob, PayerDocument
from datetime import datetime

def check_status():
    session = next(get_db())
    
    try:
        print("\n" + "="*70)
        print("SCRAPING STATUS REPORT")
        print("="*70)
        
        # Check scrape jobs
        print("\n[1] SCRAPE JOB HISTORY:")
        jobs = session.query(ScrapeJob).order_by(ScrapeJob.started_at.desc()).limit(10).all()
        
        if not jobs:
            print("    ❌ NO SCRAPE JOBS FOUND!")
            print("    → The crawler has NEVER run")
            print("    → All data is from manual seeding")
        else:
            print(f"    ✓ Found {len(jobs)} scrape jobs")
            for job in jobs[:5]:
                status_icon = "✓" if job.status == "completed" else "✗"
                print(f"    {status_icon} {job.payer.name}: {job.status} at {job.started_at}")
                if job.status == "completed":
                    print(f"       - Rules created: {job.rules_created}")
                    print(f"       - Rules updated: {job.rules_updated}")
                    print(f"       - Pages crawled: {job.pages_crawled}")
        
        # Check documents
        print("\n[2] CRAWLED DOCUMENTS:")
        docs = session.query(PayerDocument).all()
        if not docs:
            print("    ❌ NO DOCUMENTS FOUND!")
            print("    → No PDFs have been downloaded")
        else:
            print(f"    ✓ Found {len(docs)} documents")
            for doc in docs[:5]:
                print(f"    - {doc.title} ({doc.document_type})")
        
        # Check rules by source
        print("\n[3] RULES BY SOURCE:")
        rules = session.query(PayerRule).all()
        print(f"    Total rules: {len(rules)}")
        
        manual_rules = [r for r in rules if not r.source_document_id]
        crawled_rules = [r for r in rules if r.source_document_id]
        
        print(f"    - Manual/seeded: {len(manual_rules)}")
        print(f"    - From crawler: {len(crawled_rules)}")
        
        if len(manual_rules) > 0:
            print("\n    Manual rules:")
            for rule in manual_rules:
                print(f"      • {rule.payer.name}: {rule.title}")
        
        if len(crawled_rules) > 0:
            print("\n    Crawled rules:")
            for rule in crawled_rules[:5]:
                print(f"      • {rule.payer.name}: {rule.title}")
        
        # Check when last updated
        print("\n[4] LAST UPDATE TIMES:")
        for payer in session.query(Payer).all():
            rule_count = session.query(PayerRule).filter_by(payer_id=payer.id).count()
            if rule_count > 0:
                latest_rule = session.query(PayerRule).filter_by(payer_id=payer.id).order_by(
                    PayerRule.updated_at.desc()
                ).first()
                print(f"    {payer.name}: {rule_count} rules, last updated {latest_rule.updated_at}")
        
        # Recommendations
        print("\n" + "="*70)
        print("RECOMMENDATIONS:")
        print("="*70)
        
        if not jobs:
            print("\n✓ TO START CRAWLING:")
            print("  1. Run manual scrape:")
            print("     python scripts/run_scraper.py --payer aetna")
            print("\n  2. Or trigger via API:")
            print("     curl -X POST http://localhost:8000/scrape/trigger/3")
            print("\n  3. Scheduler is running - will auto-scrape based on priority")
            print("     (High: daily, Medium: weekly Mon, Low: weekly Sun)")
        
        if len(crawled_rules) == 0:
            print("\n⚠ All current data is from manual seeding, not web crawling")
            print("  Run the scraper to get real payer data!")
        
        print("\n" + "="*70)
        
    finally:
        session.close()

if __name__ == "__main__":
    check_status()
