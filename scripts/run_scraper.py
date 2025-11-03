#!/usr/bin/env python3
"""
Run scraper manually and store results in database
"""

import sys
import os
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from payer_portal_crawler import PayerPortalCrawler
from database.connection import get_db_manager
from scheduler.change_detector import ChangeDetector
from database.models import Payer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Run scraper and store results"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run payer portal scraper")
    parser.add_argument(
        "--payer",
        choices=["united_healthcare", "anthem", "aetna", "all"],
        default="all",
        help="Payer to scrape"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run browser in headless mode"
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", "sqlite:///payer_knowledge_base.db"),
        help="Database URL"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Healthcare Payer Portal Scraper")
    print("=" * 60)
    
    # Initialize database
    db_manager = get_db_manager(database_url=args.database_url)
    change_detector = ChangeDetector()
    
    # Initialize crawler
    print(f"\nInitializing crawler (headless={args.headless})...")
    crawler = PayerPortalCrawler(headless=args.headless)
    
    try:
        # Determine which payers to scrape
        if args.payer == "all":
            payers_to_scrape = list(crawler.payer_configs.keys())
        else:
            payers_to_scrape = [args.payer]
        
        print(f"\nScraping {len(payers_to_scrape)} payer(s)...")
        
        for payer_key in payers_to_scrape:
            print(f"\n{'='*60}")
            print(f"Scraping: {payer_key}")
            print(f"{'='*60}")
            
            # Perform crawl
            results = crawler.crawl_payer(payer_key)
            
            if 'error' in results:
                print(f"✗ Error: {results['error']}")
                continue
            
            # Get payer ID from database
            with db_manager.session_scope() as session:
                payer_name = results.get('payer', payer_key)
                payer = session.query(Payer).filter(
                    Payer.name.ilike(f"%{payer_name}%")
                ).first()
                
                if not payer:
                    print(f"⚠ Payer not found in database: {payer_name}")
                    print("  Creating new payer entry...")
                    payer = Payer(
                        name=payer_name,
                        base_domain=results.get('base_url', ''),
                        is_active=True
                    )
                    session.add(payer)
                    session.flush()
                
                # Process results and detect changes
                print("\nProcessing results and detecting changes...")
                stats = change_detector.process_crawl_results(
                    session, payer.id, results
                )
                
                print(f"\n✓ Scraping completed for {payer_name}")
                print(f"  - Pages crawled: {results.get('metadata', {}).get('total_pages_crawled', 0)}")
                print(f"  - PDFs downloaded: {results.get('metadata', {}).get('total_pdfs_downloaded', 0)}")
                print(f"  - Rules created: {stats['rules_created']}")
                print(f"  - Rules updated: {stats['rules_updated']}")
                print(f"  - Documents created: {stats['documents_created']}")
                print(f"  - Total changes: {stats['total_changes']}")
        
        print(f"\n{'='*60}")
        print("Scraping completed successfully!")
        print(f"{'='*60}")
        
    except KeyboardInterrupt:
        print("\n\nScraping interrupted by user")
        return 1
    except Exception as e:
        print(f"\n✗ Error during scraping: {e}")
        logger.exception("Scraping error")
        return 1
    finally:
        crawler.close()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
