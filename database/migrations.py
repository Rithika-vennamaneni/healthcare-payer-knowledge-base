"""
Database migration utilities for moving from local files to database
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from database.models import Payer, PayerRule, PayerDocument, RuleType
from database.connection import get_db_manager

logger = logging.getLogger(__name__)


class DataMigrator:
    """Migrate existing scraped data to database"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def migrate_from_json(self, json_file: str) -> Dict[str, int]:
        """
        Migrate data from crawler JSON output to database
        
        Args:
            json_file: Path to JSON file from crawler
            
        Returns:
            Dictionary with migration statistics
        """
        logger.info(f"Starting migration from {json_file}")
        
        stats = {
            "payers_created": 0,
            "rules_created": 0,
            "documents_created": 0,
            "errors": 0
        }
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Process each payer in the JSON
            for payer_key, payer_data in data.items():
                if 'error' in payer_data:
                    logger.warning(f"Skipping {payer_key} due to error: {payer_data['error']}")
                    stats["errors"] += 1
                    continue
                
                try:
                    payer_stats = self._migrate_payer(payer_key, payer_data)
                    stats["payers_created"] += payer_stats["payers"]
                    stats["rules_created"] += payer_stats["rules"]
                    stats["documents_created"] += payer_stats["documents"]
                except Exception as e:
                    logger.error(f"Error migrating {payer_key}: {e}")
                    stats["errors"] += 1
            
            self.session.commit()
            logger.info(f"Migration completed: {stats}")
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            self.session.rollback()
            raise
        
        return stats
    
    def _migrate_payer(self, payer_key: str, payer_data: Dict) -> Dict[str, int]:
        """Migrate a single payer's data"""
        stats = {"payers": 0, "rules": 0, "documents": 0}
        
        # Create or get payer
        payer_name = payer_data.get('payer', payer_key)
        payer = self.session.query(Payer).filter_by(name=payer_name).first()
        
        if not payer:
            payer = Payer(
                name=payer_name,
                base_domain=payer_data.get('base_url', ''),
                config={
                    'crawl_timestamp': payer_data.get('crawl_timestamp'),
                    'metadata': payer_data.get('metadata', {})
                }
            )
            self.session.add(payer)
            self.session.flush()  # Get payer ID
            stats["payers"] = 1
            logger.info(f"Created payer: {payer_name}")
        
        # Migrate documents
        pdf_documents = payer_data.get('pdf_documents', [])
        for doc_data in pdf_documents:
            doc_stats = self._migrate_document(payer, doc_data)
            stats["documents"] += doc_stats["documents"]
            stats["rules"] += doc_stats["rules"]
        
        # Migrate extracted content
        extracted_content = payer_data.get('extracted_content', {})
        for rule_type in ['prior_authorization', 'timely_filing', 'appeals']:
            if rule_type in extracted_content:
                rules_data = extracted_content[rule_type].get('rules', [])
                for rule_data in rules_data:
                    if self._create_rule(payer, rule_type, rule_data):
                        stats["rules"] += 1
        
        return stats
    
    def _migrate_document(self, payer: Payer, doc_data: Dict) -> Dict[str, int]:
        """Migrate a single document"""
        stats = {"documents": 0, "rules": 0}
        
        # Check if document already exists
        source_url = doc_data.get('url', '')
        existing_doc = self.session.query(PayerDocument).filter_by(
            payer_id=payer.id,
            source_url=source_url
        ).first()
        
        if existing_doc:
            logger.debug(f"Document already exists: {source_url}")
            return stats
        
        # Create document
        document = PayerDocument(
            payer_id=payer.id,
            document_type='pdf',
            title=doc_data.get('text', doc_data.get('filename', 'Unknown')),
            filename=doc_data.get('filename'),
            source_url=source_url,
            local_file_path=doc_data.get('local_file'),
            raw_content=doc_data.get('extracted_content', {}).get('text', ''),
            structured_content={
                'pages': doc_data.get('extracted_content', {}).get('pages', []),
                'geographic_zones': doc_data.get('extracted_content', {}).get('geographic_zones', [])
            },
            downloaded_at=datetime.fromisoformat(doc_data.get('download_timestamp', datetime.utcnow().isoformat())),
            processing_status='completed',
            metadata={
                'relevance_score': doc_data.get('relevance_score'),
                'extraction_method': doc_data.get('extracted_content', {}).get('extraction_method')
            }
        )
        
        self.session.add(document)
        self.session.flush()  # Get document ID
        stats["documents"] = 1
        
        # Extract rules from document
        extracted_rules = doc_data.get('extracted_content', {}).get('extracted_rules', [])
        for rule_data in extracted_rules:
            if self._create_rule(payer, rule_data.get('type'), rule_data, document):
                stats["rules"] += 1
        
        return stats
    
    def _create_rule(
        self, 
        payer: Payer, 
        rule_type_str: str, 
        rule_data: Dict,
        source_document: Optional[PayerDocument] = None
    ) -> bool:
        """Create a payer rule"""
        try:
            # Map string to enum
            rule_type_map = {
                'prior_authorization': RuleType.PRIOR_AUTHORIZATION,
                'timely_filing': RuleType.TIMELY_FILING,
                'appeals': RuleType.APPEALS,
                'list_item': RuleType.OTHER,
                'paragraph': RuleType.OTHER,
                'table': RuleType.OTHER
            }
            
            rule_type = rule_type_map.get(rule_type_str, RuleType.OTHER)
            content = rule_data.get('content', '')
            
            # Skip empty or very short content
            if not content or len(str(content)) < 20:
                return False
            
            # Convert content to string if it's a list (table data)
            if isinstance(content, list):
                content = json.dumps(content)
            
            # Create rule
            rule = PayerRule(
                payer_id=payer.id,
                rule_type=rule_type,
                content=content,
                source_document_id=source_document.id if source_document else None,
                confidence_score=rule_data.get('confidence'),
                metadata={
                    'source_type': rule_data.get('source'),
                    'original_type': rule_type_str
                }
            )
            
            self.session.add(rule)
            return True
            
        except Exception as e:
            logger.error(f"Error creating rule: {e}")
            return False
    
    def migrate_payer_csv(self, csv_file: str) -> int:
        """
        Migrate payer information from CSV file
        
        Args:
            csv_file: Path to payer_companies.csv
            
        Returns:
            Number of payers created/updated
        """
        import pandas as pd
        
        logger.info(f"Migrating payers from {csv_file}")
        count = 0
        
        try:
            df = pd.read_csv(csv_file)
            
            for _, row in df.iterrows():
                payer = self.session.query(Payer).filter_by(name=row['company_name']).first()
                
                if not payer:
                    payer = Payer(
                        name=row['company_name'],
                        ticker_symbol=row['ticker_symbol'],
                        base_domain=row['base_domain'],
                        provider_portal_url=row['known_provider_portal'],
                        market_share=float(row['market_share']),
                        priority=row['priority']
                    )
                    self.session.add(payer)
                    count += 1
                else:
                    # Update existing payer
                    payer.ticker_symbol = row['ticker_symbol']
                    payer.base_domain = row['base_domain']
                    payer.provider_portal_url = row['known_provider_portal']
                    payer.market_share = float(row['market_share'])
                    payer.priority = row['priority']
            
            self.session.commit()
            logger.info(f"Migrated {count} payers from CSV")
            
        except Exception as e:
            logger.error(f"CSV migration failed: {e}")
            self.session.rollback()
            raise
        
        return count


def migrate_existing_data(
    json_files: List[str] = None,
    csv_file: str = None,
    database_url: str = None
):
    """
    Main migration function to move existing data to database
    
    Args:
        json_files: List of JSON files from crawler
        csv_file: Path to payer CSV file
        database_url: Database connection URL
    """
    logger.info("Starting data migration...")
    
    # Initialize database
    db_manager = get_db_manager(database_url=database_url)
    db_manager.create_tables()
    
    with db_manager.session_scope() as session:
        migrator = DataMigrator(session)
        
        # Migrate payer CSV first
        if csv_file and Path(csv_file).exists():
            migrator.migrate_payer_csv(csv_file)
        
        # Migrate JSON files
        if json_files:
            for json_file in json_files:
                if Path(json_file).exists():
                    migrator.migrate_from_json(json_file)
                else:
                    logger.warning(f"JSON file not found: {json_file}")
    
    logger.info("Migration completed successfully")


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)
    
    # Find existing JSON files
    json_files = list(Path(".").glob("crawl_results_*.json"))
    csv_file = "payer_companies.csv"
    
    if json_files or Path(csv_file).exists():
        migrate_existing_data(
            json_files=[str(f) for f in json_files],
            csv_file=csv_file if Path(csv_file).exists() else None,
            database_url="sqlite:///payer_knowledge_base.db"  # Use SQLite for testing
        )
    else:
        print("No data files found to migrate")
