"""
RAG-powered chatbot for payer knowledge base queries
Integrates retrieval with LLM generation
"""

import os
import logging
from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from rag.embeddings import EmbeddingGenerator, hybrid_search
from database.models import ChatSession, ChatQuery

logger = logging.getLogger(__name__)


class PayerKnowledgeChatbot:
    """
    Conversational chatbot with RAG for payer rules
    """
    
    def __init__(
        self,
        embedding_generator: EmbeddingGenerator,
        llm_provider: str = "openai",
        llm_model: str = None,
        api_key: str = None
    ):
        """
        Initialize chatbot
        
        Args:
            embedding_generator: Embedding generator for retrieval
            llm_provider: LLM provider (openai, anthropic)
            llm_model: Model name
            api_key: API key for LLM provider
        """
        self.embedding_generator = embedding_generator
        self.llm_provider = llm_provider.lower()
        
        if self.llm_provider == "openai":
            self.api_key = api_key or os.getenv("OPENAI_API_KEY")
            self.llm_model = llm_model or "gpt-4o-mini"
            self._init_openai()
        elif self.llm_provider == "anthropic":
            self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
            self.llm_model = llm_model or "claude-3-5-sonnet-20241022"
            self._init_anthropic()
        elif self.llm_provider == "groq":
            self.api_key = api_key or os.getenv("GROQ_API_KEY")
            self.llm_model = llm_model or "llama-3.1-70b-versatile"
            self._init_groq()
        else:
            raise ValueError(f"Unsupported LLM provider: {llm_provider}")
        
        logger.info(f"Initialized chatbot with {self.llm_provider}:{self.llm_model}")
    
    def _init_openai(self):
        """Initialize OpenAI client"""
        try:
            from openai import OpenAI
            self.llm_client = OpenAI(api_key=self.api_key)
        except ImportError:
            raise ImportError("OpenAI package not installed. Run: pip install openai")
    
    def _init_anthropic(self):
        """Initialize Anthropic client"""
        try:
            from anthropic import Anthropic
            self.llm_client = Anthropic(api_key=self.api_key or os.getenv("ANTHROPIC_API_KEY"))
        except ImportError:
            raise ImportError("Anthropic package not installed. Run: pip install anthropic")
    
    def _init_groq(self):
        """Initialize Groq client"""
        try:
            from groq import Groq
            self.llm_client = Groq(api_key=self.api_key)
        except ImportError:
            raise ImportError("Groq package not installed. Run: pip install groq")
    
    def query(
        self,
        session: Session,
        query_text: str,
        session_id: str = None,
        payer_name: Optional[str] = None,
        rule_type: Optional[str] = None,
        top_k: int = 5,
        include_sources: bool = True
    ) -> Dict:
        """
        Process a user query and generate response
        
        Args:
            session: Database session
            query_text: User's question
            session_id: Chat session ID (for context)
            payer_name: Filter by payer name (optional)
            rule_type: Filter by rule type (optional)
            top_k: Number of sources to retrieve
            include_sources: Include source citations in response
            
        Returns:
            Dictionary with response and metadata
        """
        start_time = datetime.utcnow()
        
        # Get or create chat session
        chat_session = self._get_or_create_session(session, session_id)
        
        # Retrieve relevant rules
        payer_id = self._get_payer_id(session, payer_name) if payer_name else None
        
        retrieved_rules = hybrid_search(
            session=session,
            query_text=query_text,
            embedding_generator=self.embedding_generator,
            payer_id=payer_id,
            rule_type=rule_type,
            top_k=top_k
        )
        
        # Generate response using LLM
        response_text = self._generate_response(
            query_text=query_text,
            retrieved_rules=retrieved_rules,
            include_sources=include_sources
        )
        
        # Calculate response time
        response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        # Save query to database
        chat_query = ChatQuery(
            session_id=chat_session.id,
            query_text=query_text,
            response_text=response_text,
            sources_cited=[
                {
                    'rule_id': rule['rule_id'],
                    'payer_name': rule['payer_name'],
                    'rule_type': rule['rule_type'],
                    'score': rule.get('combined_score', rule.get('similarity_score', 0))
                }
                for rule in retrieved_rules
            ],
            retrieval_method='hybrid',
            num_sources_retrieved=len(retrieved_rules),
            response_time_ms=response_time
        )
        session.add(chat_query)
        session.commit()
        
        return {
            'response': response_text,
            'sources': retrieved_rules if include_sources else [],
            'session_id': chat_session.session_id,
            'query_id': chat_query.id,
            'response_time_ms': response_time,
            'num_sources': len(retrieved_rules)
        }
    
    def _get_or_create_session(
        self,
        session: Session,
        session_id: Optional[str]
    ) -> ChatSession:
        """Get existing or create new chat session"""
        if session_id:
            chat_session = session.query(ChatSession).filter_by(
                session_id=session_id
            ).first()
            
            if chat_session:
                chat_session.last_activity_at = datetime.utcnow()
                return chat_session
        
        # Create new session
        import uuid
        new_session_id = session_id or str(uuid.uuid4())
        
        chat_session = ChatSession(session_id=new_session_id)
        session.add(chat_session)
        session.flush()
        
        return chat_session
    
    def _get_payer_id(self, session: Session, payer_name: str) -> Optional[int]:
        """Get payer ID from name"""
        from database.models import Payer
        
        payer = session.query(Payer).filter(
            Payer.name.ilike(f"%{payer_name}%")
        ).first()
        
        return payer.id if payer else None
    
    def _generate_response(
        self,
        query_text: str,
        retrieved_rules: List[Dict],
        include_sources: bool
    ) -> str:
        """
        Generate response using LLM with retrieved context
        
        Args:
            query_text: User's question
            retrieved_rules: Retrieved rules from database
            include_sources: Whether to include source citations
            
        Returns:
            Generated response text
        """
        # Build context from retrieved rules
        context = self._build_context(retrieved_rules)
        
        # Create system prompt
        system_prompt = """You are a helpful assistant specializing in healthcare payer rules and regulations. 
You help healthcare staff understand payer requirements for prior authorization, timely filing, appeals, and other administrative processes.

When answering questions:
1. Be accurate and cite specific rules when available
2. If information is not in the provided context, say so clearly
3. Provide practical, actionable guidance
4. Include relevant timeframes and deadlines
5. Mention the payer name when discussing specific rules
6. If rules vary by payer, explain the differences

Always base your answers on the provided context. Do not make up information."""
        
        # Create user prompt with context
        user_prompt = f"""Context (Retrieved Payer Rules):
{context}

User Question: {query_text}

Please provide a clear, accurate answer based on the context above. If the context doesn't contain enough information to fully answer the question, acknowledge this."""
        
        try:
            if self.llm_provider == "openai":
                response = self.llm_client.chat.completions.create(
                    model=self.llm_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.3,
                    max_tokens=1000
                )
                response_text = response.choices[0].message.content
            
            elif self.llm_provider == "anthropic":
                response = self.llm_client.messages.create(
                    model=self.llm_model,
                    max_tokens=1000,
                    temperature=0.3,
                    system=system_prompt,
                    messages=[
                        {"role": "user", "content": user_prompt}
                    ]
                )
                response_text = response.content[0].text
            
            elif self.llm_provider == "groq":
                response = self.llm_client.chat.completions.create(
                    model=self.llm_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.3,
                    max_tokens=1000
                )
                response_text = response.choices[0].message.content
            
            # Add source citations if requested
            if include_sources and retrieved_rules:
                response_text += "\n\n**Sources:**\n"
                for i, rule in enumerate(retrieved_rules[:3], 1):
                    response_text += f"{i}. {rule['payer_name']} - {rule['rule_type']}"
                    if rule.get('source_url'):
                        response_text += f" ([Source]({rule['source_url']}))"
                    response_text += "\n"
            
            return response_text
        
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return "I apologize, but I encountered an error generating a response. Please try again."
    
    def _build_context(self, retrieved_rules: List[Dict]) -> str:
        """Build context string from retrieved rules"""
        if not retrieved_rules:
            return "No relevant rules found in the knowledge base."
        
        context_parts = []
        
        for i, rule in enumerate(retrieved_rules, 1):
            context_part = f"\n--- Rule {i} ---\n"
            context_part += f"Payer: {rule['payer_name']}\n"
            context_part += f"Type: {rule['rule_type']}\n"
            
            if rule.get('title'):
                context_part += f"Title: {rule['title']}\n"
            
            if rule.get('effective_date'):
                context_part += f"Effective Date: {rule['effective_date']}\n"
            
            # Truncate very long content
            content = rule['content']
            if len(content) > 1000:
                content = content[:1000] + "..."
            
            context_part += f"Content: {content}\n"
            
            context_parts.append(context_part)
        
        return "\n".join(context_parts)
    
    def get_conversation_history(
        self,
        session: Session,
        session_id: str,
        limit: int = 10
    ) -> List[Dict]:
        """
        Get conversation history for a session
        
        Args:
            session: Database session
            session_id: Chat session ID
            limit: Maximum number of messages to return
            
        Returns:
            List of query/response pairs
        """
        chat_session = session.query(ChatSession).filter_by(
            session_id=session_id
        ).first()
        
        if not chat_session:
            return []
        
        queries = session.query(ChatQuery).filter_by(
            session_id=chat_session.id
        ).order_by(ChatQuery.created_at.desc()).limit(limit).all()
        
        history = []
        for query in reversed(queries):
            history.append({
                'query': query.query_text,
                'response': query.response_text,
                'timestamp': query.created_at.isoformat(),
                'sources': query.sources_cited
            })
        
        return history
    
    def submit_feedback(
        self,
        session: Session,
        query_id: int,
        rating: int,
        feedback_text: Optional[str] = None
    ):
        """
        Submit user feedback for a query
        
        Args:
            session: Database session
            query_id: Query ID
            rating: Rating (1-5)
            feedback_text: Optional feedback text
        """
        query = session.query(ChatQuery).filter_by(id=query_id).first()
        
        if query:
            query.user_rating = rating
            query.user_feedback = feedback_text
            session.commit()
            logger.info(f"Feedback submitted for query {query_id}: {rating} stars")


def create_chatbot(
    embedding_provider: str = None,
    llm_provider: str = None,
    embedding_model: str = None,
    llm_model: str = None
) -> PayerKnowledgeChatbot:
    """
    Factory function to create chatbot instance
    
    Args:
        embedding_provider: Provider for embeddings (defaults to env var)
        llm_provider: Provider for LLM (defaults to env var)
        embedding_model: Embedding model name (defaults to env var)
        llm_model: LLM model name (defaults to env var)
        
    Returns:
        Configured chatbot instance
    """
    # Read from environment if not provided
    embedding_provider = embedding_provider or os.getenv("EMBEDDING_PROVIDER", "openai")
    llm_provider = llm_provider or os.getenv("LLM_PROVIDER", "openai")
    embedding_model = embedding_model or os.getenv("EMBEDDING_MODEL")
    llm_model = llm_model or os.getenv("LLM_MODEL")
    
    embedding_generator = EmbeddingGenerator(
        provider=embedding_provider,
        model=embedding_model
    )
    
    chatbot = PayerKnowledgeChatbot(
        embedding_generator=embedding_generator,
        llm_provider=llm_provider,
        llm_model=llm_model
    )
    
    return chatbot
