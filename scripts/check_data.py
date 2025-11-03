"""Check what data exists in the database"""
from database.connection import get_db_manager
from database.models import Payer, PayerRule

def check_database():
    from database.connection import get_db
    session = next(get_db())
    
    try:
        # Check payers
        payers = session.query(Payer).all()
        print(f"\n✓ Payers in database: {len(payers)}")
        for p in payers:
            print(f"  - {p.name}")
        
        # Check rules
        rules = session.query(PayerRule).all()
        print(f"\n✓ Rules in database: {len(rules)}")
        
        if len(rules) == 0:
            print("\n❌ NO RULES FOUND! Need to run scraper or seed data.")
            return False
        
        # Check rules per payer
        print("\nRules per payer:")
        for payer in payers:
            count = session.query(PayerRule).filter_by(payer_id=payer.id).count()
            if count > 0:
                print(f"  - {payer.name}: {count} rules")
        
        # Show sample rule
        sample = session.query(PayerRule).first()
        if sample:
            print(f"\n✓ Sample rule:")
            print(f"  Title: {sample.title}")
            print(f"  Type: {sample.rule_type}")
            print(f"  Content preview: {sample.content[:200] if sample.content else 'No content'}...")
            print(f"  Has embedding: {sample.embedding is not None}")
        
        # Check embeddings
        rules_with_embeddings = session.query(PayerRule).filter(
            PayerRule.embedding.isnot(None)
        ).count()
        print(f"\n✓ Rules with embeddings: {rules_with_embeddings}/{len(rules)}")
        
        if rules_with_embeddings == 0:
            print("\n❌ NO EMBEDDINGS! Need to generate them.")
            return False
        
        print("\n✓ Database looks good!")
        return True
        
    finally:
        session.close()

if __name__ == "__main__":
    check_database()
