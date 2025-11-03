"""
Change detection and alerting system for payer rules
Compares new scraped data against existing records
"""

import logging
import hashlib
import difflib
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_

from database.models import (
    Payer, PayerRule, PayerDocument, ChangeLog, Alert,
    RuleType, ChangeType
)

logger = logging.getLogger(__name__)


class ChangeDetector:
    """
    Detects changes in payer rules and generates alerts
    """
    
    def __init__(self, similarity_threshold: float = 0.85):
        """
        Initialize change detector
        
        Args:
            similarity_threshold: Minimum similarity ratio to consider content unchanged (0-1)
        """
        self.similarity_threshold = similarity_threshold
    
    def process_crawl_results(
        self,
        session: Session,
        payer_id: int,
        crawl_results: Dict
    ) -> Dict[str, int]:
        """
        Process crawl results and detect changes
        
        Args:
            session: Database session
            payer_id: Payer database ID
            crawl_results: Results from crawler
            
        Returns:
            Dictionary with change statistics
        """
        stats = {
            'rules_created': 0,
            'rules_updated': 0,
            'rules_unchanged': 0,
            'documents_created': 0,
            'documents_updated': 0,
            'total_changes': 0,
            'alerts_created': 0
        }
        
        logger.info(f"Processing crawl results for payer {payer_id}")
        
        # Process documents first
        pdf_documents = crawl_results.get('pdf_documents', [])
        document_map = {}  # Map source URLs to document IDs
        
        for doc_data in pdf_documents:
            doc_id, is_new, has_changes = self._process_document(session, payer_id, doc_data)
            if doc_id:
                document_map[doc_data.get('url', '')] = doc_id
                if is_new:
                    stats['documents_created'] += 1
                elif has_changes:
                    stats['documents_updated'] += 1
        
        # Process rules from extracted content
        extracted_content = crawl_results.get('extracted_content', {})
        
        for rule_type_str in ['prior_authorization', 'timely_filing', 'appeals']:
            if rule_type_str not in extracted_content:
                continue
            
            rules_data = extracted_content[rule_type_str].get('rules', [])
            
            for rule_data in rules_data:
                result = self._process_rule(
                    session, payer_id, rule_type_str, rule_data, None
                )
                
                if result == 'created':
                    stats['rules_created'] += 1
                    stats['total_changes'] += 1
                elif result == 'updated':
                    stats['rules_updated'] += 1
                    stats['total_changes'] += 1
                elif result == 'unchanged':
                    stats['rules_unchanged'] += 1
        
        # Process rules from documents
        for doc_data in pdf_documents:
            doc_id = document_map.get(doc_data.get('url', ''))
            extracted_rules = doc_data.get('extracted_content', {}).get('extracted_rules', [])
            
            for rule_data in extracted_rules:
                result = self._process_rule(
                    session, payer_id, rule_data.get('type'), rule_data, doc_id
                )
                
                if result == 'created':
                    stats['rules_created'] += 1
                    stats['total_changes'] += 1
                elif result == 'updated':
                    stats['rules_updated'] += 1
                    stats['total_changes'] += 1
                elif result == 'unchanged':
                    stats['rules_unchanged'] += 1
        
        # Create summary alert if significant changes detected
        if stats['total_changes'] > 0:
            alert = self._create_change_alert(session, payer_id, stats)
            if alert:
                stats['alerts_created'] += 1
        
        session.flush()
        logger.info(f"Change detection completed: {stats}")
        
        return stats
    
    def _process_document(
        self,
        session: Session,
        payer_id: int,
        doc_data: Dict
    ) -> Tuple[Optional[int], bool, bool]:
        """
        Process a document and detect changes
        
        Returns:
            Tuple of (document_id, is_new, has_changes)
        """
        source_url = doc_data.get('url', '')
        if not source_url:
            return None, False, False
        
        # Calculate content hash
        content = doc_data.get('extracted_content', {}).get('text', '')
        content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
        
        # Check if document exists
        existing_doc = session.query(PayerDocument).filter_by(
            payer_id=payer_id,
            source_url=source_url
        ).first()
        
        if not existing_doc:
            # Create new document
            document = PayerDocument(
                payer_id=payer_id,
                document_type='pdf',
                title=doc_data.get('text', doc_data.get('filename', 'Unknown')),
                filename=doc_data.get('filename'),
                source_url=source_url,
                local_file_path=doc_data.get('local_file'),
                raw_content=content,
                structured_content={
                    'pages': doc_data.get('extracted_content', {}).get('pages', []),
                    'geographic_zones': doc_data.get('extracted_content', {}).get('geographic_zones', [])
                },
                file_hash=content_hash,
                downloaded_at=datetime.utcnow(),
                processing_status='completed',
                metadata={
                    'relevance_score': doc_data.get('relevance_score'),
                    'extraction_method': doc_data.get('extracted_content', {}).get('extraction_method')
                }
            )
            session.add(document)
            session.flush()
            
            logger.info(f"Created new document: {document.title}")
            return document.id, True, False
        
        else:
            # Check for changes
            has_changes = False
            
            if existing_doc.file_hash != content_hash:
                # Document content changed
                logger.info(f"Document content changed: {existing_doc.title}")
                
                existing_doc.raw_content = content
                existing_doc.file_hash = content_hash
                existing_doc.last_checked_at = datetime.utcnow()
                existing_doc.structured_content = {
                    'pages': doc_data.get('extracted_content', {}).get('pages', []),
                    'geographic_zones': doc_data.get('extracted_content', {}).get('geographic_zones', [])
                }
                has_changes = True
            else:
                # No changes, just update last checked
                existing_doc.last_checked_at = datetime.utcnow()
            
            return existing_doc.id, False, has_changes
    
    def _process_rule(
        self,
        session: Session,
        payer_id: int,
        rule_type_str: str,
        rule_data: Dict,
        source_document_id: Optional[int]
    ) -> str:
        """
        Process a rule and detect changes
        
        Returns:
            'created', 'updated', or 'unchanged'
        """
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
        content = str(rule_data.get('content', ''))
        
        # Skip empty or very short content
        if not content or len(content) < 20:
            return 'unchanged'
        
        # Generate rule identifier based on content hash
        rule_identifier = hashlib.md5(
            f"{payer_id}:{rule_type.value}:{content[:100]}".encode()
        ).hexdigest()
        
        # Find existing similar rules
        existing_rules = session.query(PayerRule).filter(
            and_(
                PayerRule.payer_id == payer_id,
                PayerRule.rule_type == rule_type,
                PayerRule.is_current == True
            )
        ).all()
        
        # Check for similar content
        best_match = None
        best_similarity = 0
        
        for existing_rule in existing_rules:
            similarity = self._calculate_similarity(content, existing_rule.content)
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = existing_rule
        
        # Determine action based on similarity
        if best_match and best_similarity >= self.similarity_threshold:
            # Content is similar enough - check for minor changes
            if best_similarity < 0.99:  # Some changes detected
                return self._update_rule(session, best_match, content, rule_data, source_document_id)
            else:
                return 'unchanged'
        else:
            # New rule or significantly different
            return self._create_rule(session, payer_id, rule_type, rule_identifier, content, rule_data, source_document_id)
    
    def _create_rule(
        self,
        session: Session,
        payer_id: int,
        rule_type: RuleType,
        rule_identifier: str,
        content: str,
        rule_data: Dict,
        source_document_id: Optional[int]
    ) -> str:
        """Create a new rule"""
        rule = PayerRule(
            payer_id=payer_id,
            rule_type=rule_type,
            rule_identifier=rule_identifier,
            content=content,
            source_document_id=source_document_id,
            confidence_score=rule_data.get('confidence'),
            metadata={
                'source_type': rule_data.get('source'),
                'original_type': rule_data.get('type')
            }
        )
        session.add(rule)
        session.flush()
        
        # Create change log
        change_log = ChangeLog(
            rule_id=rule.id,
            change_type=ChangeType.CREATED,
            new_value={'content': content},
            detected_by='scraper'
        )
        session.add(change_log)
        
        logger.debug(f"Created new rule: {rule.id}")
        return 'created'
    
    def _update_rule(
        self,
        session: Session,
        existing_rule: PayerRule,
        new_content: str,
        rule_data: Dict,
        source_document_id: Optional[int]
    ) -> str:
        """Update an existing rule with new version"""
        # Mark old rule as not current
        existing_rule.is_current = False
        
        # Create new version
        new_rule = PayerRule(
            payer_id=existing_rule.payer_id,
            rule_type=existing_rule.rule_type,
            rule_identifier=existing_rule.rule_identifier,
            content=new_content,
            version=existing_rule.version + 1,
            supersedes_id=existing_rule.id,
            source_document_id=source_document_id,
            confidence_score=rule_data.get('confidence'),
            metadata={
                'source_type': rule_data.get('source'),
                'original_type': rule_data.get('type')
            }
        )
        session.add(new_rule)
        session.flush()
        
        # Create change log with diff
        diff = self._generate_diff(existing_rule.content, new_content)
        change_log = ChangeLog(
            rule_id=new_rule.id,
            change_type=ChangeType.CONTENT_MODIFIED,
            old_value={'content': existing_rule.content, 'version': existing_rule.version},
            new_value={'content': new_content, 'version': new_rule.version},
            diff=diff,
            detected_by='scraper'
        )
        session.add(change_log)
        
        logger.info(f"Updated rule {existing_rule.id} -> {new_rule.id} (v{new_rule.version})")
        return 'updated'
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate similarity ratio between two texts
        
        Returns:
            Similarity ratio between 0 and 1
        """
        return difflib.SequenceMatcher(None, text1, text2).ratio()
    
    def _generate_diff(self, old_text: str, new_text: str) -> Dict:
        """
        Generate structured diff between old and new text
        
        Returns:
            Dictionary with diff information
        """
        differ = difflib.Differ()
        diff_lines = list(differ.compare(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True)
        ))
        
        added = [line[2:] for line in diff_lines if line.startswith('+ ')]
        removed = [line[2:] for line in diff_lines if line.startswith('- ')]
        
        return {
            'added_lines': added,
            'removed_lines': removed,
            'total_changes': len(added) + len(removed),
            'similarity': self._calculate_similarity(old_text, new_text)
        }
    
    def _create_change_alert(
        self,
        session: Session,
        payer_id: int,
        stats: Dict
    ) -> Optional[Alert]:
        """Create an alert for detected changes"""
        payer = session.query(Payer).filter_by(id=payer_id).first()
        if not payer:
            return None
        
        # Determine severity based on number of changes
        total_changes = stats['total_changes']
        if total_changes >= 10:
            severity = 'high'
        elif total_changes >= 5:
            severity = 'medium'
        else:
            severity = 'low'
        
        alert = Alert(
            alert_type='rule_change',
            severity=severity,
            title=f"Rule Changes Detected for {payer.name}",
            message=f"Detected {total_changes} changes: "
                   f"{stats['rules_created']} new rules, "
                   f"{stats['rules_updated']} updated rules, "
                   f"{stats['documents_created']} new documents",
            payer_id=payer_id,
            metadata=stats
        )
        session.add(alert)
        
        logger.info(f"Created {severity} severity alert for {payer.name}")
        return alert
    
    def get_recent_changes(
        self,
        session: Session,
        payer_id: Optional[int] = None,
        days: int = 7,
        limit: int = 100
    ) -> List[ChangeLog]:
        """
        Get recent changes
        
        Args:
            session: Database session
            payer_id: Filter by payer (optional)
            days: Number of days to look back
            limit: Maximum number of changes to return
            
        Returns:
            List of ChangeLog objects
        """
        from datetime import timedelta
        
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        query = session.query(ChangeLog).filter(
            ChangeLog.changed_at >= cutoff_date
        )
        
        if payer_id:
            query = query.join(PayerRule).filter(PayerRule.payer_id == payer_id)
        
        changes = query.order_by(ChangeLog.changed_at.desc()).limit(limit).all()
        
        return changes
    
    def get_unalerted_changes(
        self,
        session: Session,
        limit: int = 50
    ) -> List[ChangeLog]:
        """
        Get changes that haven't been alerted yet
        
        Args:
            session: Database session
            limit: Maximum number of changes to return
            
        Returns:
            List of ChangeLog objects
        """
        changes = session.query(ChangeLog).filter(
            ChangeLog.alert_sent == False
        ).order_by(ChangeLog.changed_at.desc()).limit(limit).all()
        
        return changes
    
    def mark_changes_alerted(
        self,
        session: Session,
        change_ids: List[int]
    ):
        """
        Mark changes as alerted
        
        Args:
            session: Database session
            change_ids: List of change log IDs
        """
        session.query(ChangeLog).filter(
            ChangeLog.id.in_(change_ids)
        ).update(
            {
                ChangeLog.alert_sent: True,
                ChangeLog.alert_sent_at: datetime.utcnow()
            },
            synchronize_session=False
        )
        
        logger.info(f"Marked {len(change_ids)} changes as alerted")
