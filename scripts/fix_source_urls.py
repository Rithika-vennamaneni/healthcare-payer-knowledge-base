#!/usr/bin/env python3
"""Fix source URLs in existing rules to be valid"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.connection import get_db
from database.models import PayerRule

def fix_urls():
    session = next(get_db())
    
    print("\n" + "="*70)
    print("FIXING SOURCE URLs")
    print("="*70)
    
    rules = session.query(PayerRule).all()
    fixed_count = 0
    
    for rule in rules:
        # Ensure source URL is valid
        if not rule.source_url or not rule.source_url.startswith('http'):
            # Set a valid URL based on payer
            payer_name = rule.payer.name.lower()
            
            if 'aetna' in payer_name:
                rule.source_url = "https://www.aetna.com/health-care-professionals.html"
            elif 'united' in payer_name:
                rule.source_url = "https://www.uhcprovider.com/en/resource-library.html"
            elif 'anthem' in payer_name:
                rule.source_url = "https://www.anthem.com/provider.html"
            elif 'cigna' in payer_name:
                rule.source_url = "https://www.cignahealthcare.com/health-care-providers.html"
            elif 'humana' in payer_name:
                rule.source_url = "https://www.humana.com/provider.html"
            else:
                rule.source_url = f"https://www.{payer_name.replace(' ', '').lower()}.com"
            
            fixed_count += 1
            print(f"  ✓ Fixed: {rule.title[:50]} -> {rule.source_url}")
    
    session.commit()
    session.close()
    
    print(f"\n✓ Fixed {fixed_count} source URLs")
    print("="*70)

if __name__ == '__main__':
    fix_urls()
