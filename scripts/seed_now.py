"""Add test data RIGHT NOW so we can test"""
from database.connection import get_db
from database.models import Payer, PayerRule, RuleType
from datetime import date
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def seed_now():
    session = next(get_db())
    
    try:
        # Get Aetna
        aetna = session.query(Payer).filter_by(name="Aetna (CVS Health)").first()
        if not aetna:
            print("❌ Aetna not found in database")
            return
        
        print(f"✓ Found Aetna (ID: {aetna.id})")
        
        # Add timely filing rule
        rule1 = PayerRule(
            payer_id=aetna.id,
            rule_type=RuleType.TIMELY_FILING,
            title="Aetna Timely Filing Requirements",
            content="""Aetna requires that all claims be submitted within 90 days from the date of service. This is a strict deadline and claims submitted after this period may be denied.

For institutional claims, the deadline is 90 days from discharge date.
For professional claims, 90 days from date of service.

Extensions may be granted in cases of:
- Retroactive eligibility
- Payer processing delays
- Natural disasters

To request an extension, contact provider services at 1-800-872-3862.""",
            effective_date=date(2024, 1, 1),
            source_url="https://www.aetna.com/provider/timely-filing",
            version=1,
            is_current=True
        )
        session.add(rule1)
        
        # Add prior auth rule
        rule2 = PayerRule(
            payer_id=aetna.id,
            rule_type=RuleType.PRIOR_AUTHORIZATION,
            title="Prior Authorization Requirements",
            content="""Aetna requires prior authorization for the following services:
- Advanced imaging (MRI, CT, PET scans)
- Inpatient hospital stays
- Outpatient surgeries
- Durable medical equipment over $1000
- Home health services

Prior authorization must be obtained before services are rendered.
Failure to obtain authorization may result in claim denial.

To request authorization, call 1-800-872-3862 or use the online portal at www.aetna.com/provider.
Turnaround time is typically 2-3 business days for standard requests, 24 hours for urgent requests.""",
            effective_date=date(2024, 1, 1),
            source_url="https://www.aetna.com/provider/prior-auth",
            version=1,
            is_current=True
        )
        session.add(rule2)
        
        # Add appeals rule
        rule3 = PayerRule(
            payer_id=aetna.id,
            rule_type=RuleType.APPEALS,
            title="Appeals Process",
            content="""Aetna members and providers have the right to appeal denied claims.

Standard Appeal Timeline:
- Submit within 180 days of denial
- Decision within 30 days for medical services
- Decision within 60 days for disability claims

Expedited Appeals:
- Available when standard timeline could jeopardize health
- Decision within 72 hours

How to Submit:
1. Complete appeal form
2. Include supporting documentation
3. Submit via fax to 1-888-xxx-xxxx or mail to Aetna Appeals Department

Required Information:
- Member ID and claim number
- Reason for appeal
- Supporting medical records
- Provider statement if applicable""",
            effective_date=date(2024, 1, 1),
            source_url="https://www.aetna.com/provider/appeals",
            version=1,
            is_current=True
        )
        session.add(rule3)
        
        session.commit()
        print("✓ Seeded 3 rules for Aetna")
        
        # Get United Healthcare
        uhc = session.query(Payer).filter_by(name="United Healthcare").first()
        if uhc:
            rule4 = PayerRule(
                payer_id=uhc.id,
                rule_type=RuleType.TIMELY_FILING,
                title="United Healthcare Timely Filing",
                content="""United Healthcare requires claims to be filed within 180 days from the date of service for most plans.

Key Points:
- 180 days for commercial plans
- 365 days for Medicare Advantage
- 90 days for Medicaid plans (varies by state)

Claims submitted after the deadline will be denied as untimely.

Exception Process:
Contact provider services at 1-800-842-3211 to request consideration for late filing due to:
- System outages
- Retroactive eligibility
- Coordination of benefits delays""",
                effective_date=date(2024, 1, 1),
                source_url="https://www.uhcprovider.com/timely-filing",
                version=1,
                is_current=True
            )
            session.add(rule4)
            session.commit()
            print("✓ Seeded 1 rule for United Healthcare")
        
        # Now generate embeddings
        print("\nGenerating embeddings...")
        from rag.embeddings import EmbeddingGenerator
        
        generator = EmbeddingGenerator()
        rules = session.query(PayerRule).filter_by(payer_id=aetna.id).all()
        
        for rule in rules:
            print(f"  Generating embedding for: {rule.title}")
            embedding = generator.generate_embedding(rule.content)
            rule.embedding = json.dumps(embedding)
        
        if uhc:
            uhc_rules = session.query(PayerRule).filter_by(payer_id=uhc.id).all()
            for rule in uhc_rules:
                print(f"  Generating embedding for: {rule.title}")
                embedding = generator.generate_embedding(rule.content)
                rule.embedding = json.dumps(embedding)
        
        session.commit()
        print("✓ Embeddings generated")
        
        print("\n" + "="*60)
        print("✓ DONE! Database seeded with test data")
        print("="*60)
        print("\nYou can now test with:")
        print("  curl -X POST http://localhost:8000/chat/query \\")
        print("    -H 'Content-Type: application/json' \\")
        print("    -d '{\"query\":\"What is Aetna timely filing rule?\",\"include_sources\":true}'")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    seed_now()
