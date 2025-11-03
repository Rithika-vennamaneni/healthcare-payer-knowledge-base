"""Save scraped PDF data to database"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.connection import get_db
from database.models import Payer, PayerDocument, PayerRule, RuleType
from datetime import datetime
import re
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PDFDatabaseSaver:
    def __init__(self):
        self.session = next(get_db())
    
    def save_pdf_documents(self, pdf_documents):
        """Save PDFs and extracted rules to database"""
        logger.info(f"\n{'='*70}")
        logger.info("SAVING TO DATABASE")
        logger.info(f"{'='*70}")
        
        total_rules = 0
        for pdf_doc in pdf_documents:
            try:
                payer = self.get_or_create_payer(pdf_doc['payer'])
                document = self.save_document(payer, pdf_doc)
                rules_saved = self.extract_and_save_rules(payer, document, pdf_doc)
                total_rules += rules_saved
                logger.info(f"  ✓ {pdf_doc['title'][:50]}: {rules_saved} rules")
            except Exception as e:
                logger.error(f"  ✗ {pdf_doc['title'][:50]}: {e}")
                import traceback
                traceback.print_exc()
        
        self.session.commit()
        logger.info(f"\n✓ Database save complete - {total_rules} total rules saved")
        return total_rules
    
    def get_or_create_payer(self, payer_name):
        """Get or create payer"""
        payer = self.session.query(Payer).filter_by(name=payer_name).first()
        if not payer:
            payer = Payer(name=payer_name, priority='high', is_active=True)
            self.session.add(payer)
            self.session.commit()
        return payer
    
    def save_document(self, payer, pdf_doc):
        """Save PDF document record"""
        existing = self.session.query(PayerDocument).filter_by(
            payer_id=payer.id,
            title=pdf_doc['title']
        ).first()
        
        if existing:
            existing.file_path = pdf_doc['filepath']
            existing.url = pdf_doc['url']
            existing.extracted_text = pdf_doc['full_text']
            existing.page_count = pdf_doc['page_count']
            existing.updated_at = datetime.utcnow()
            return existing
        else:
            document = PayerDocument(
                payer_id=payer.id,
                document_type='pdf',
                title=pdf_doc['title'],
                file_path=pdf_doc['filepath'],
                url=pdf_doc['url'],
                extracted_text=pdf_doc['full_text'],
                page_count=pdf_doc.get('page_count'),
                rule_metadata={'downloaded_at': pdf_doc['downloaded_at']}
            )
            self.session.add(document)
            self.session.commit()
            return document
    
    def extract_and_save_rules(self, payer, document, pdf_doc):
        """Extract and save individual rules"""
        rules_saved = 0
        
        for section in pdf_doc.get('sections', []):
            if len(section['content']) < 100:
                continue
            
            rule_type = self.classify_rule_type(section['title'])
            
            existing = self.session.query(PayerRule).filter_by(
                payer_id=payer.id,
                title=section['title']
            ).first()
            
            if existing:
                if existing.content != section['content']:
                    existing.content = section['content']
                    existing.version += 1
                    existing.updated_at = datetime.utcnow()
                    existing.source_url = document.url
                    existing.source_document_id = document.id
            else:
                rule = PayerRule(
                    payer_id=payer.id,
                    rule_type=rule_type,
                    title=section['title'],
                    content=section['content'],
                    source_url=document.url,
                    source_document_id=document.id,
                    version=1,
                    is_current=True
                )
                self.session.add(rule)
                rules_saved += 1
        
        return rules_saved
    
    def classify_rule_type(self, title):
        """Classify rule type from title"""
        title_lower = title.lower()
        
        if any(kw in title_lower for kw in ['timely filing', 'claim submission deadline']):
            return RuleType.TIMELY_FILING
        elif any(kw in title_lower for kw in ['prior auth', 'authorization', 'precert']):
            return RuleType.PRIOR_AUTHORIZATION
        elif any(kw in title_lower for kw in ['appeal', 'dispute', 'grievance']):
            return RuleType.APPEALS
        elif any(kw in title_lower for kw in ['reimburse', 'payment', 'fee']):
            return RuleType.REIMBURSEMENT
        elif any(kw in title_lower for kw in ['coverage', 'benefit', 'eligibility']):
            return RuleType.COVERAGE
        elif any(kw in title_lower for kw in ['billing', 'coding', 'claim format']):
            return RuleType.BILLING
        else:
            return RuleType.GENERAL
    
    def close(self):
        """Close database session"""
        self.session.close()
