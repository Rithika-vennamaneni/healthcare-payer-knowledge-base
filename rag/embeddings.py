"""
Vector embeddings generation and management for RAG
Supports OpenAI and local embedding models
"""

import os
import logging
from typing import List, Optional, Dict
import numpy as np
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """
    Generate and manage vector embeddings for semantic search
    """
    
    def __init__(
        self,
        provider: str = "openai",
        model: str = None,
        api_key: str = None
    ):
        """
        Initialize embedding generator
        
        Args:
            provider: Embedding provider (openai, sentence-transformers)
            model: Model name (defaults based on provider)
            api_key: API key for provider (if needed)
        """
        self.provider = provider.lower()
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        
        if self.provider == "openai":
            self.model = model or "text-embedding-3-small"
            self._init_openai()
        elif self.provider == "sentence-transformers":
            self.model = model or "all-MiniLM-L6-v2"
            self._init_sentence_transformers()
        else:
            raise ValueError(f"Unsupported provider: {provider}")
        
        logger.info(f"Initialized {self.provider} embeddings with model {self.model}")
    
    def _init_openai(self):
        """Initialize OpenAI embeddings"""
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key)
            self.embedding_dim = 1536 if "3-small" in self.model else 1536
        except ImportError:
            raise ImportError("OpenAI package not installed. Run: pip install openai")
    
    def _init_sentence_transformers(self):
        """Initialize sentence-transformers embeddings"""
        try:
            from sentence_transformers import SentenceTransformer
            self.client = SentenceTransformer(self.model)
            self.embedding_dim = self.client.get_sentence_embedding_dimension()
        except ImportError:
            raise ImportError("sentence-transformers not installed. Run: pip install sentence-transformers")
    
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text
        
        Args:
            text: Input text
            
        Returns:
            Embedding vector as list of floats
        """
        if not text or not text.strip():
            return [0.0] * self.embedding_dim
        
        try:
            if self.provider == "openai":
                response = self.client.embeddings.create(
                    input=text,
                    model=self.model
                )
                return response.data[0].embedding
            
            elif self.provider == "sentence-transformers":
                embedding = self.client.encode(text, convert_to_numpy=True)
                return embedding.tolist()
        
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return [0.0] * self.embedding_dim
    
    def generate_embeddings_batch(
        self,
        texts: List[str],
        batch_size: int = 100
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batches
        
        Args:
            texts: List of input texts
            batch_size: Number of texts to process at once
            
        Returns:
            List of embedding vectors
        """
        embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            try:
                if self.provider == "openai":
                    response = self.client.embeddings.create(
                        input=batch,
                        model=self.model
                    )
                    batch_embeddings = [item.embedding for item in response.data]
                
                elif self.provider == "sentence-transformers":
                    batch_embeddings = self.client.encode(
                        batch,
                        convert_to_numpy=True,
                        show_progress_bar=False
                    ).tolist()
                
                embeddings.extend(batch_embeddings)
                
            except Exception as e:
                logger.error(f"Error in batch {i}-{i+batch_size}: {e}")
                # Add zero vectors for failed batch
                embeddings.extend([[0.0] * self.embedding_dim] * len(batch))
        
        return embeddings
    
    def cosine_similarity(
        self,
        embedding1: List[float],
        embedding2: List[float]
    ) -> float:
        """
        Calculate cosine similarity between two embeddings
        
        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
            
        Returns:
            Similarity score between -1 and 1
        """
        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)
        
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)


def embed_rules(
    session: Session,
    embedding_generator: EmbeddingGenerator,
    batch_size: int = 50,
    force_reembed: bool = False
) -> int:
    """
    Generate embeddings for all rules in database
    
    Args:
        session: Database session
        embedding_generator: Embedding generator instance
        batch_size: Number of rules to process at once
        force_reembed: Re-generate embeddings even if they exist
        
    Returns:
        Number of rules embedded
    """
    from database.models import PayerRule
    
    # Get rules that need embeddings
    query = session.query(PayerRule).filter(PayerRule.is_current == True)
    
    if not force_reembed:
        query = query.filter(PayerRule.embedding == None)
    
    rules = query.all()
    
    if not rules:
        logger.info("No rules need embedding")
        return 0
    
    logger.info(f"Embedding {len(rules)} rules...")
    
    # Prepare texts for embedding
    texts = []
    for rule in rules:
        # Combine title and content for better semantic representation
        text = f"{rule.title or ''} {rule.content}".strip()
        texts.append(text)
    
    # Generate embeddings in batches
    embeddings = embedding_generator.generate_embeddings_batch(texts, batch_size)
    
    # Update rules with embeddings
    count = 0
    for rule, embedding in zip(rules, embeddings):
        rule.embedding = embedding
        rule.embedding_model = f"{embedding_generator.provider}:{embedding_generator.model}"
        count += 1
    
    session.commit()
    logger.info(f"Successfully embedded {count} rules")
    
    return count


def embed_query(
    query_text: str,
    embedding_generator: EmbeddingGenerator
) -> List[float]:
    """
    Generate embedding for a search query
    
    Args:
        query_text: Query text
        embedding_generator: Embedding generator instance
        
    Returns:
        Query embedding vector
    """
    return embedding_generator.generate_embedding(query_text)


def find_similar_rules(
    session: Session,
    query_embedding: List[float],
    payer_id: Optional[int] = None,
    rule_type: Optional[str] = None,
    top_k: int = 5,
    similarity_threshold: float = 0.5
) -> List[Dict]:
    """
    Find rules similar to query using vector similarity
    
    Args:
        session: Database session
        query_embedding: Query embedding vector
        payer_id: Filter by payer ID (optional)
        rule_type: Filter by rule type (optional)
        top_k: Number of results to return
        similarity_threshold: Minimum similarity score
        
    Returns:
        List of similar rules with similarity scores
    """
    from database.models import PayerRule, Payer, RuleType
    
    # Build query
    query = session.query(PayerRule).filter(
        PayerRule.is_current == True,
        PayerRule.embedding != None
    )
    
    if payer_id:
        query = query.filter(PayerRule.payer_id == payer_id)
    
    if rule_type:
        try:
            rule_type_enum = RuleType[rule_type.upper()]
            query = query.filter(PayerRule.rule_type == rule_type_enum)
        except KeyError:
            pass
    
    rules = query.all()
    
    if not rules:
        return []
    
    # Calculate similarities
    results = []
    query_vec = np.array(query_embedding)
    
    for rule in rules:
        rule_vec = np.array(rule.embedding)
        
        # Cosine similarity
        similarity = np.dot(query_vec, rule_vec) / (
            np.linalg.norm(query_vec) * np.linalg.norm(rule_vec)
        )
        
        if similarity >= similarity_threshold:
            # Get payer info
            payer = session.query(Payer).filter_by(id=rule.payer_id).first()
            
            results.append({
                'rule_id': rule.id,
                'payer_name': payer.name if payer else 'Unknown',
                'payer_id': rule.payer_id,
                'rule_type': rule.rule_type.value,
                'title': rule.title,
                'content': rule.content,
                'source_url': rule.source_url,
                'effective_date': rule.effective_date.isoformat() if rule.effective_date else None,
                'similarity_score': float(similarity),
                'version': rule.version
            })
    
    # Sort by similarity and return top_k
    results.sort(key=lambda x: x['similarity_score'], reverse=True)
    return results[:top_k]


def hybrid_search(
    session: Session,
    query_text: str,
    embedding_generator: EmbeddingGenerator,
    payer_id: Optional[int] = None,
    rule_type: Optional[str] = None,
    top_k: int = 5,
    semantic_weight: float = 0.7
) -> List[Dict]:
    """
    Hybrid search combining semantic and keyword matching
    
    Args:
        session: Database session
        query_text: Search query
        embedding_generator: Embedding generator instance
        payer_id: Filter by payer ID (optional)
        rule_type: Filter by rule type (optional)
        top_k: Number of results to return
        semantic_weight: Weight for semantic score (0-1), keyword gets (1-weight)
        
    Returns:
        List of rules with combined scores
    """
    from database.models import PayerRule, Payer
    from sqlalchemy import func
    
    # Semantic search (with fallback if embeddings fail)
    try:
        query_embedding = embed_query(query_text, embedding_generator)
        semantic_results = find_similar_rules(
            session, query_embedding, payer_id, rule_type, top_k * 2, 0.3
        )
    except Exception as e:
        logger.warning(f"Semantic search failed, using keyword-only search: {e}")
        semantic_results = []
    
    # Keyword search using PostgreSQL full-text search or simple LIKE
    # Extract key terms from query for better matching
    query_lower = query_text.lower()
    search_terms = []
    
    # Extract payer names
    payer_names = ['aetna', 'united', 'anthem', 'cigna', 'humana', 'kaiser']
    for name in payer_names:
        if name in query_lower:
            search_terms.append(name)
    
    # Extract rule types
    if 'timely filing' in query_lower or 'filing' in query_lower:
        search_terms.append('timely filing')
    if 'prior auth' in query_lower or 'authorization' in query_lower:
        search_terms.append('authorization')
    if 'appeal' in query_lower:
        search_terms.append('appeal')
    
    # Build keyword query
    keyword_query = session.query(PayerRule).filter(PayerRule.is_current == True)
    
    # Add search conditions
    if search_terms:
        from sqlalchemy import or_
        conditions = []
        for term in search_terms:
            conditions.append(PayerRule.content.ilike(f"%{term}%"))
            conditions.append(PayerRule.title.ilike(f"%{term}%"))
        keyword_query = keyword_query.filter(or_(*conditions))
    else:
        keyword_query = keyword_query.filter(PayerRule.content.ilike(f"%{query_text}%"))
    
    if payer_id:
        keyword_query = keyword_query.filter(PayerRule.payer_id == payer_id)
    
    keyword_results = keyword_query.limit(top_k * 2).all()
    
    # Combine results
    combined_scores = {}
    
    # Add semantic scores
    for result in semantic_results:
        rule_id = result['rule_id']
        combined_scores[rule_id] = {
            'rule': result,
            'semantic_score': result['similarity_score'],
            'keyword_score': 0.0
        }
    
    # Add keyword scores
    for rule in keyword_results:
        payer = session.query(Payer).filter_by(id=rule.payer_id).first()
        
        # Simple keyword scoring based on occurrence count
        keyword_score = rule.content.lower().count(query_text.lower()) / len(rule.content)
        keyword_score = min(keyword_score * 100, 1.0)  # Normalize
        
        if rule.id in combined_scores:
            combined_scores[rule.id]['keyword_score'] = keyword_score
        else:
            combined_scores[rule.id] = {
                'rule': {
                    'rule_id': rule.id,
                    'payer_name': payer.name if payer else 'Unknown',
                    'payer_id': rule.payer_id,
                    'rule_type': rule.rule_type.value,
                    'title': rule.title,
                    'content': rule.content,
                    'source_url': rule.source_url,
                    'effective_date': rule.effective_date.isoformat() if rule.effective_date else None,
                    'version': rule.version
                },
                'semantic_score': 0.0,
                'keyword_score': keyword_score
            }
    
    # Calculate combined scores
    results = []
    for rule_id, scores in combined_scores.items():
        combined_score = (
            semantic_weight * scores['semantic_score'] +
            (1 - semantic_weight) * scores['keyword_score']
        )
        
        result = scores['rule'].copy()
        result['combined_score'] = float(combined_score)
        result['semantic_score'] = float(scores['semantic_score'])
        result['keyword_score'] = float(scores['keyword_score'])
        results.append(result)
    
    # Sort by combined score
    results.sort(key=lambda x: x['combined_score'], reverse=True)
    return results[:top_k]
