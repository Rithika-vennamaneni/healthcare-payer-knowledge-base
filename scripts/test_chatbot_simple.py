"""Test chatbot with simple keyword matching (no embeddings needed)"""
from database.connection import get_db
from database.models import Payer, PayerRule, RuleType

def test_simple():
    session = next(get_db())
    
    try:
        query = "What is Aetna timely filing rule?"
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print('='*60)
        
        # Simple keyword search (no embeddings)
        print("\n[1] Searching database with keywords...")
        rules = session.query(PayerRule).join(Payer).filter(
            Payer.name.ilike('%Aetna%'),
            PayerRule.rule_type == RuleType.TIMELY_FILING
        ).all()
        
        print(f"✓ Found {len(rules)} matching rules")
        
        if rules:
            for rule in rules:
                print(f"\n{'='*60}")
                print(f"Payer: {rule.payer.name}")
                print(f"Title: {rule.title}")
                print(f"Type: {rule.rule_type.value}")
                print(f"{'='*60}")
                print(f"\nContent:\n{rule.content}")
                print(f"\nSource: {rule.source_url}")
                
            print(f"\n{'='*60}")
            print("✓ SUCCESS! Rules found and can be returned to chatbot")
            print('='*60)
            print("\nThe chatbot error is likely due to:")
            print("1. OpenAI API quota exceeded (can't generate embeddings)")
            print("2. Embeddings stored as JSON strings instead of arrays")
            print("\nSOLUTION: Use keyword/SQL search as fallback when embeddings fail")
        else:
            print("\n❌ No rules found")
            
    finally:
        session.close()

if __name__ == "__main__":
    test_simple()
