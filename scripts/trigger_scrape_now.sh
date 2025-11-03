#!/bin/bash
# Trigger immediate scrape for Aetna

echo "=========================================="
echo "Triggering Aetna Scrape via API"
echo "=========================================="

curl -X POST http://localhost:8000/scrape/trigger \
  -H "Content-Type: application/json" \
  -d '{"payer_id": 3}' | python3 -m json.tool

echo ""
echo "=========================================="
echo "Check status with:"
echo "cd /Users/rithikavennamaneni/Desktop/Knowledge_Base_Demo && PYTHONPATH=/Users/rithikavennamaneni/Desktop/Knowledge_Base_Demo python scripts/check_scraping_status.py"
echo "=========================================="
