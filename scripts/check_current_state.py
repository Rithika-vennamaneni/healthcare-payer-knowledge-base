#!/usr/bin/env python3
"""Show current state of database and scraping"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.connection import get_db
from database.models import Payer, PayerRule, PayerDocument, ScrapeJob
import json

def check_state():
    session = next(get_db())
    
    try:
        print("\n" + "="*70)
        print("CURRENT SYSTEM STATE")
        print("="*70)
        
        # Check database
        print("\n[DATABASE]")
        payers = session.query(Payer).all()
        print(f"  Payers: {len(payers)}")
        for p in payers:
            rule_count = session.query(PayerRule).filter_by(payer_id=p.id).count()
            print(f"    - {p.name}: {rule_count} rules")
        
        total_rules = session.query(PayerRule).count()
        rules_with_embeddings = session.query(PayerRule).filter(PayerRule.embedding.isnot(None)).count()
        print(f"\n  Total Rules: {total_rules}")
        print(f"  Rules with embeddings: {rules_with_embeddings}")
        
        # Check for documents table
        try:
            doc_count = session.query(PayerDocument).count()
            print(f"  PDF Documents: {doc_count}")
            if doc_count > 0:
                print(f"\n  Sample documents:")
                for doc in session.query(PayerDocument).limit(3).all():
                    print(f"    - {doc.title[:60]}")
        except Exception as e:
            print(f"  PDF Documents: Table exists but error - {e}")
        
        # Check scrape jobs
        try:
            job_count = session.query(ScrapeJob).count()
            print(f"\n  Scrape Jobs: {job_count}")
            if job_count > 0:
                latest = session.query(ScrapeJob).order_by(ScrapeJob.started_at.desc()).first()
                print(f"    Latest: {latest.payer.name} - {latest.status} at {latest.started_at}")
        except:
            print(f"  Scrape Jobs: 0")
        
        # Sample rule with source URL
        if total_rules > 0:
            sample = session.query(PayerRule).first()
            print(f"\n[SAMPLE RULE]")
            print(f"  Title: {sample.title}")
            print(f"  Source URL: {sample.source_url}")
            print(f"  URL valid? {'Yes' if sample.source_url and sample.source_url.startswith('http') else 'NO - INVALID'}")
            print(f"  Has embedding? {'Yes' if sample.embedding else 'No'}")
        
        # Check for JSON files
        print("\n[SCRAPED FILES]")
        json_files = list(Path('.').glob('**/*.json'))
        json_files = [f for f in json_files if 'node_modules' not in str(f) and 'venv' not in str(f)]
        if json_files:
            print(f"  Found {len(json_files)} JSON files:")
            for f in json_files[:5]:
                print(f"    - {f}")
        else:
            print(f"  No JSON files found")
        
        # Check for PDFs
        pdf_files = list(Path('.').glob('**/*.pdf'))
        pdf_files = [f for f in pdf_files if 'node_modules' not in str(f) and 'venv' not in str(f)]
        if pdf_files:
            print(f"\n  Found {len(pdf_files)} PDF files:")
            for f in pdf_files[:5]:
                print(f"    - {f}")
        else:
            print(f"  No PDF files found")
        
        # Check crawler configuration
        print("\n[CRAWLER CONFIGURATION]")
        try:
            from payer_portal_crawler import PayerPortalCrawler
            crawler = PayerPortalCrawler(headless=True)
            print(f"  Configured payers: {len(crawler.payer_configs)}")
            for key in crawler.payer_configs.keys():
                print(f"    - {key}")
            crawler.close()
        except Exception as e:
            print(f"  Could not load crawler config: {e}")
        
        print("\n" + "="*70)
        print("RECOMMENDATIONS:")
        print("="*70)
        
        if total_rules == 0:
            print("\n❌ NO RULES IN DATABASE")
            print("  Run: python scripts/run_scraper.py --payer aetna")
        elif rules_with_embeddings == 0:
            print("\n⚠ NO EMBEDDINGS")
            print("  Run: python scripts/generate_embeddings.py")
        elif doc_count == 0:
            print("\n⚠ NO PDF DOCUMENTS")
            print("  Crawler hasn't downloaded PDFs yet")
        else:
            print("\n✓ System looks good!")
            print("  Test chatbot: curl -X POST http://localhost:8000/chat/query \\")
            print("    -H 'Content-Type: application/json' \\")
            print("    -d '{\"query\":\"What is Aetna timely filing rule?\"}'")
        
    finally:
        session.close()

if __name__ == '__main__':
    check_state()
