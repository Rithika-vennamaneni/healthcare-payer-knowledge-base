#!/usr/bin/env python3
"""
Example usage of the Healthcare Payer Knowledge Base API
Demonstrates key functionality with Python requests
"""

import requests
import json
from typing import Dict, List

# API base URL
BASE_URL = "http://localhost:8000"


def print_section(title: str):
    """Print formatted section header"""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70 + "\n")


def check_health() -> Dict:
    """Check API health status"""
    print_section("1. Health Check")
    
    response = requests.get(f"{BASE_URL}/health")
    data = response.json()
    
    print(f"Status: {data['status']}")
    print(f"Database: {data['database']}")
    print(f"Chatbot: {data['chatbot']}")
    print(f"Scheduler: {data['scheduler']}")
    
    return data


def list_payers() -> List[Dict]:
    """List all active payers"""
    print_section("2. List Payers")
    
    response = requests.get(f"{BASE_URL}/payers")
    payers = response.json()
    
    print(f"Found {len(payers)} active payers:\n")
    for payer in payers:
        print(f"  • {payer['name']}")
        print(f"    - ID: {payer['id']}")
        print(f"    - Priority: {payer['priority']}")
        print(f"    - Total Rules: {payer['total_rules']}")
        print()
    
    return payers


def query_chatbot(question: str, payer_name: str = None) -> Dict:
    """Query the chatbot"""
    print_section(f"3. Chatbot Query: '{question}'")
    
    payload = {
        "query": question,
        "include_sources": True
    }
    
    if payer_name:
        payload["payer_name"] = payer_name
    
    response = requests.post(
        f"{BASE_URL}/chat/query",
        json=payload
    )
    
    data = response.json()
    
    print(f"Response ({data['response_time_ms']:.0f}ms):\n")
    print(data['response'])
    
    if data['sources']:
        print(f"\n\nSources ({data['num_sources']} found):")
        for i, source in enumerate(data['sources'][:3], 1):
            print(f"\n  {i}. {source['payer_name']} - {source['rule_type']}")
            print(f"     Relevance: {source.get('combined_score', source.get('similarity_score', 0)):.2f}")
            if source.get('source_url'):
                print(f"     URL: {source['source_url']}")
    
    return data


def list_recent_rules(payer_id: int = None, limit: int = 5) -> List[Dict]:
    """List recent rules"""
    print_section("4. Recent Rules")
    
    params = {"limit": limit, "current_only": True}
    if payer_id:
        params["payer_id"] = payer_id
    
    response = requests.get(f"{BASE_URL}/rules", params=params)
    rules = response.json()
    
    print(f"Found {len(rules)} recent rules:\n")
    for rule in rules:
        print(f"  • {rule['payer_name']} - {rule['rule_type']}")
        print(f"    Version: {rule['version']}")
        content_preview = rule['content'][:100] + "..." if len(rule['content']) > 100 else rule['content']
        print(f"    Content: {content_preview}")
        print()
    
    return rules


def trigger_scrape(payer_id: int) -> Dict:
    """Trigger immediate scraping for a payer"""
    print_section(f"5. Trigger Scraping for Payer ID {payer_id}")
    
    response = requests.post(
        f"{BASE_URL}/scrape/trigger",
        json={"payer_id": payer_id}
    )
    
    data = response.json()
    print(f"Status: {data['status']}")
    print(f"Message: {data['message']}")
    print(f"Job ID: {data['job_id']}")
    
    return data


def view_alerts(unread_only: bool = True) -> List[Dict]:
    """View system alerts"""
    print_section("6. System Alerts")
    
    params = {"unread_only": unread_only, "limit": 10}
    response = requests.get(f"{BASE_URL}/alerts", params=params)
    alerts = response.json()
    
    if not alerts:
        print("No alerts found.")
        return []
    
    print(f"Found {len(alerts)} alerts:\n")
    for alert in alerts:
        print(f"  • [{alert['severity'].upper()}] {alert['title']}")
        print(f"    {alert['message']}")
        print(f"    Created: {alert['created_at']}")
        print()
    
    return alerts


def get_statistics() -> Dict:
    """Get system statistics"""
    print_section("7. System Statistics")
    
    response = requests.get(f"{BASE_URL}/stats")
    stats = response.json()
    
    print(f"Total Payers: {stats['total_payers']}")
    print(f"Total Rules: {stats['total_rules']}")
    print(f"Unread Alerts: {stats['unread_alerts']}")
    print(f"Scrape Jobs (Last 7 Days): {stats['scrape_jobs_last_7_days']}")
    
    print("\nRules by Type:")
    for rule_type, count in stats['rules_by_type'].items():
        print(f"  • {rule_type}: {count}")
    
    return stats


def main():
    """Run example usage demonstrations"""
    print("\n" + "="*70)
    print("  Healthcare Payer Knowledge Base - Example Usage")
    print("="*70)
    print("\nMake sure the API server is running at http://localhost:8000")
    print("Start it with: uvicorn api.main:app --reload\n")
    
    input("Press Enter to continue...")
    
    try:
        # 1. Health check
        health = check_health()
        
        if health['status'] != 'healthy':
            print("\n⚠ API is not healthy. Check the server logs.")
            return
        
        # 2. List payers
        payers = list_payers()
        
        if not payers:
            print("\n⚠ No payers found. Run the scraper first:")
            print("  python scripts/run_scraper.py --payer all")
            return
        
        # 3. Query chatbot - General question
        query_chatbot("What is timely filing?")
        
        # 4. Query chatbot - Specific payer
        if payers:
            payer_name = payers[0]['name']
            query_chatbot(
                f"What are the prior authorization requirements?",
                payer_name=payer_name
            )
        
        # 5. List recent rules
        if payers:
            list_recent_rules(payer_id=payers[0]['id'])
        
        # 6. View alerts
        view_alerts()
        
        # 7. Get statistics
        get_statistics()
        
        # Optional: Trigger scraping (commented out to avoid accidental runs)
        # if payers:
        #     trigger_scrape(payers[0]['id'])
        
        print("\n" + "="*70)
        print("  Example Usage Complete!")
        print("="*70)
        print("\nNext steps:")
        print("1. Explore the API docs: http://localhost:8000/docs")
        print("2. Try more chatbot queries")
        print("3. Set up automated scraping schedules")
        print("4. Integrate with your frontend application")
        
    except requests.exceptions.ConnectionError:
        print("\n✗ Could not connect to API server.")
        print("Make sure it's running: uvicorn api.main:app --reload")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
