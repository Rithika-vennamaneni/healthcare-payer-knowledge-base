#!/usr/bin/env python3
"""
Initialize database and migrate existing data
Run this script to set up the database for the first time
"""

import sys
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.connection import init_database, get_db_manager
from database.migrations import migrate_existing_data
from rag.embeddings import EmbeddingGenerator, embed_rules

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Initialize database and migrate data"""
    print("=" * 60)
    print("Healthcare Payer Knowledge Base - Database Initialization")
    print("=" * 60)
    
    # Get database URL from environment or use SQLite default
    database_url = os.getenv("DATABASE_URL", "sqlite:///payer_knowledge_base.db")
    print(f"\nDatabase URL: {database_url}")
    
    # Step 1: Create database tables
    print("\n[1/4] Creating database tables...")
    try:
        init_database(database_url=database_url, drop_existing=False)
        print("✓ Database tables created successfully")
    except Exception as e:
        print(f"✗ Error creating tables: {e}")
        return 1
    
    # Step 2: Migrate payer CSV
    print("\n[2/4] Migrating payer information...")
    csv_file = "payer_companies.csv"
    if Path(csv_file).exists():
        try:
            migrate_existing_data(
                json_files=None,
                csv_file=csv_file,
                database_url=database_url
            )
            print(f"✓ Migrated payers from {csv_file}")
        except Exception as e:
            print(f"✗ Error migrating CSV: {e}")
    else:
        print(f"⚠ CSV file not found: {csv_file}")
    
    # Step 3: Migrate existing JSON crawl results
    print("\n[3/4] Migrating existing crawl results...")
    json_files = list(Path(".").glob("crawl_results_*.json"))
    
    if json_files:
        print(f"Found {len(json_files)} JSON files to migrate")
        try:
            migrate_existing_data(
                json_files=[str(f) for f in json_files],
                csv_file=None,
                database_url=database_url
            )
            print(f"✓ Migrated data from {len(json_files)} files")
        except Exception as e:
            print(f"✗ Error migrating JSON files: {e}")
    else:
        print("⚠ No crawl result JSON files found")
    
    # Step 4: Generate embeddings (optional)
    print("\n[4/4] Generating embeddings (optional)...")
    
    if os.getenv("OPENAI_API_KEY"):
        try:
            print("Initializing embedding generator...")
            embedding_generator = EmbeddingGenerator(provider="openai")
            
            db_manager = get_db_manager(database_url=database_url)
            with db_manager.session_scope() as session:
                count = embed_rules(session, embedding_generator, batch_size=50)
                print(f"✓ Generated embeddings for {count} rules")
        except Exception as e:
            print(f"⚠ Could not generate embeddings: {e}")
            print("  You can generate embeddings later using the API endpoint")
    else:
        print("⚠ OPENAI_API_KEY not set, skipping embeddings")
        print("  Set the API key and run: POST /embeddings/generate")
    
    print("\n" + "=" * 60)
    print("Database initialization complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Start the API server: python api/main.py")
    print("2. Or use: uvicorn api.main:app --reload")
    print("3. Access API docs at: http://localhost:8000/docs")
    print("4. Set up scraping schedules via API or scheduler")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
