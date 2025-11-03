#!/usr/bin/env python3
"""Test complete system: database → chatbot → sources"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.connection import get_db
from database.models import Payer, PayerRule, PayerDocument
import requests
import json

def test_system():
    print("\n" + "="*70)
    print("COMPLETE SYSTEM TEST")
    print("="*70)
    
    session = next(get_db())
    
    # 1. Check database
    print("\n[1] DATABASE STATUS")
    payer_count = session.query(Payer).count()
    rule_count = session.query(PayerRule).count()
    
    try:
        doc_count = session.query(PayerDocument).count()
    except:
        doc_count = 0
    
    embeddings_count = session.query(PayerRule).filter(PayerRule.embedding != None).count()
    
    print(f"  Payers: {payer_count}")
    print(f"  Rules: {rule_count}")
    print(f"  Documents: {doc_count}")
    print(f"  Rules with embeddings: {embeddings_count}/{rule_count}")
    
    if rule_count == 0:
        print("\n  ❌ NO DATA! Run: python scripts/seed_now.py")
        return
    
    # 2. Check source URLs
    print("\n[2] SOURCE URL VALIDATION")
    sample_rules = session.query(PayerRule).limit(5).all()
    valid_urls = 0
    for rule in sample_rules:
        is_valid = rule.source_url and rule.source_url.startswith('http')
        status = "✓" if is_valid else "✗"
        print(f"  {status} {rule.title[:50]}")
        print(f"     URL: {rule.source_url}")
        if is_valid:
            valid_urls += 1
    
    print(f"\n  Valid URLs: {valid_urls}/{len(sample_rules)}")
    
    # 3. Test chatbot
    print("\n[3] CHATBOT TEST")
    print("  Testing query: 'What is Aetna timely filing rule?'")
    
    try:
        response = requests.post(
            'http://localhost:8000/chat/query',
            json={'query': 'What is Aetna timely filing rule?', 'include_sources': True},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            
            print(f"\n  ✓ Chatbot responded successfully!")
            print(f"\n  Answer preview:")
            answer = data.get('response', '')
            print(f"  {answer[:200]}...")
            
            sources = data.get('sources', [])
            print(f"\n  Sources returned: {len(sources)}")
            
            if sources:
                print(f"\n  First source:")
                src = sources[0]
                print(f"    Payer: {src.get('payer_name')}")
                print(f"    Title: {src.get('title')}")
                print(f"    Type: {src.get('rule_type')}")
                print(f"    URL: {src.get('source_url')}")
                print(f"    URL valid? {'Yes' if src.get('source_url', '').startswith('http') else 'NO'}")
            
            if 'error' in answer.lower() or 'apologize' in answer.lower():
                print(f"\n  ⚠ Warning: Chatbot returned error message")
            else:
                print(f"\n  ✓ Chatbot working correctly!")
        else:
            print(f"  ✗ API returned status {response.status_code}")
            print(f"  Response: {response.text[:200]}")
    
    except requests.exceptions.ConnectionError:
        print(f"  ✗ Cannot connect to API - is backend running?")
        print(f"  Start with: uvicorn api.main:app --reload")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    
    # 4. Show configured websites
    print("\n[4] CONFIGURED SCRAPING WEBSITES")
    try:
        from scraper.pdf_crawler import PAYER_CONFIGS
        for payer, config in PAYER_CONFIGS.items():
            print(f"\n  {payer}:")
            for url in config['urls']:
                print(f"    - {url}")
    except:
        print("  Could not load scraper config")
    
    # 5. Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    if rule_count > 0 and valid_urls > 0:
        print("\n✓ DATABASE: Working")
    else:
        print("\n✗ DATABASE: Issues found")
    
    if embeddings_count == 0:
        print("⚠ EMBEDDINGS: Missing - chatbot will use keyword search only")
    else:
        print(f"✓ EMBEDDINGS: {embeddings_count} rules embedded")
    
    print("\n" + "="*70)
    print("NEXT STEPS")
    print("="*70)
    
    if embeddings_count == 0:
        print("\n1. Generate embeddings (optional - chatbot works without them):")
        print("   Note: OpenAI quota exceeded, but chatbot uses keyword search fallback")
    
    print("\n2. Test in browser:")
    print("   Open: http://localhost:5173")
    print("   Ask: 'What is Aetna timely filing rule?'")
    
    print("\n3. To scrape real PDFs from payer websites:")
    print("   python scripts/scrape_pdfs.py --payer Aetna")
    print("   (Note: Many payer sites require login or use JavaScript)")
    
    session.close()

if __name__ == '__main__':
    test_system()
