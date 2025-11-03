#!/usr/bin/env python3
"""Main script to scrape PDFs and save to database"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper.pdf_crawler import PayerPDFCrawler, PAYER_CONFIGS
from scraper.pdf_to_database import PDFDatabaseSaver
from database.connection import get_db
from database.models import PayerRule
import argparse
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def scrape_and_save(payer_name=None):
    """Scrape PDFs and save to database"""
    
    logger.info("\n" + "="*70)
    logger.info("HEALTHCARE PAYER PDF SCRAPER")
    logger.info("="*70)
    
    crawler = PayerPDFCrawler()
    saver = PDFDatabaseSaver()
    
    # Which payers to scrape
    if payer_name and payer_name != 'all':
        if payer_name not in PAYER_CONFIGS:
            logger.error(f"❌ Unknown payer: {payer_name}")
            logger.info(f"Available: {', '.join(PAYER_CONFIGS.keys())}")
            return
        payers_to_scrape = {payer_name: PAYER_CONFIGS[payer_name]}
    else:
        payers_to_scrape = PAYER_CONFIGS
    
    # Scrape each payer
    all_documents = []
    for payer, config in payers_to_scrape.items():
        logger.info(f"\n{'='*70}")
        logger.info(f"SCRAPING: {payer}")
        logger.info(f"URLs to check: {len(config['urls'])}")
        for url in config['urls']:
            logger.info(f"  - {url}")
        logger.info(f"{'='*70}")
        
        documents = crawler.scrape_payer(payer, config)
        all_documents.extend(documents)
    
    if not all_documents:
        logger.warning("\n❌ No documents scraped")
        logger.info("This could mean:")
        logger.info("  - No PDFs found on the websites")
        logger.info("  - PDFs didn't match the keywords")
        logger.info("  - Website structure changed")
        return
    
    # Save to database
    logger.info(f"\nSaving {len(all_documents)} documents...")
    total_rules = saver.save_pdf_documents(all_documents)
    
    # Generate embeddings
    logger.info(f"\nGenerating embeddings...")
    session = next(get_db())
    new_rules = session.query(PayerRule).filter(PayerRule.embedding == None).all()
    
    if new_rules:
        try:
            from rag.embeddings import EmbeddingGenerator
            import json
            
            generator = EmbeddingGenerator()
            embedded_count = 0
            
            for rule in new_rules:
                try:
                    text = f"{rule.title}\n\n{rule.content}"
                    embedding = generator.generate_embedding(text)
                    rule.embedding = json.dumps(embedding)
                    embedded_count += 1
                    
                    if embedded_count % 10 == 0:
                        session.commit()
                        logger.info(f"  Embedded {embedded_count}/{len(new_rules)} rules...")
                except Exception as e:
                    logger.warning(f"  Failed to embed rule {rule.id}: {e}")
            
            session.commit()
            logger.info(f"✓ Generated {embedded_count} embeddings")
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
    
    # Summary
    session = next(get_db())
    logger.info(f"\n{'='*70}")
    logger.info("SCRAPING COMPLETE")
    logger.info(f"{'='*70}")
    logger.info(f"  Documents scraped: {len(all_documents)}")
    logger.info(f"  Rules saved: {total_rules}")
    logger.info(f"  Total rules in DB: {session.query(PayerRule).count()}")
    logger.info(f"  Rules with embeddings: {session.query(PayerRule).filter(PayerRule.embedding != None).count()}")
    logger.info(f"\n✓ Ready to test chatbot!")
    logger.info(f"  Test: curl -X POST http://localhost:8000/chat/query \\")
    logger.info(f"    -H 'Content-Type: application/json' \\")
    logger.info(f"    -d '{{\"query\":\"What is Aetna timely filing rule?\"}}'")
    
    saver.close()
    session.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Scrape payer PDFs and save to database")
    parser.add_argument('--payer', default='Aetna', help='Payer name or "all"')
    args = parser.parse_args()
    
    scrape_and_save(args.payer)
