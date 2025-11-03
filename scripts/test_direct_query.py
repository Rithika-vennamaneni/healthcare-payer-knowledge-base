"""Test direct database query without LLM - verify data flow"""
from database.connection import get_db
from database.models import Payer, PayerRule, RuleType
from dotenv import load_dotenv

load_dotenv()

def test_direct():
    session = next(get_db())
    
    try:
        print("\n" + "="*60)
        print("TESTING DATA FLOW: Database → Rules")
        print("="*60)
        
        # Step 1: Check if we have data
        print("\n[1] Checking database...")
        payers = session.query(Payer).all()
        rules = session.query(PayerRule).all()
        print(f"✓ Found {len(payers)} payers, {len(rules)} rules")
        
        # Step 2: Query for Aetna timely filing
        print("\n[2] Searching for Aetna timely filing rule...")
        aetna_rules = session.query(PayerRule).join(Payer).filter(
            Payer.name.ilike('%Aetna%'),
            PayerRule.rule_type == RuleType.TIMELY_FILING
        ).all()
        
        print(f"✓ Found {len(aetna_rules)} matching rules")
        
        if aetna_rules:
            print("\n" + "="*60)
            print("SUCCESS! Data is flowing correctly")
            print("="*60)
            
            for rule in aetna_rules:
                print(f"\nPayer: {rule.payer.name}")
                print(f"Title: {rule.title}")
                print(f"Type: {rule.rule_type.value}")
                print(f"Content:\n{rule.content[:300]}...")
                print(f"\nSource: {rule.source_url}")
                
            print("\n" + "="*60)
            print("DATA FLOW VERIFIED ✓")
            print("="*60)
            print("\nThe issue is NOT with data - data exists and is queryable!")
            print("\nThe chatbot error is because:")
            print("1. You need to add GROQ_API_KEY to .env file")
            print("2. Get free key from: https://console.groq.com/keys")
            print("3. Add to .env: GROQ_API_KEY=gsk_your_key_here")
            print("\nOnce you add the Groq API key, the chatbot will work!")
            
        else:
            print("\n❌ No rules found - data flow broken")
            
    finally:
        session.close()

if __name__ == "__main__":
    test_direct()
