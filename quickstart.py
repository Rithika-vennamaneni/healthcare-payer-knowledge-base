#!/usr/bin/env python3
"""
Quick Start Script for Healthcare Payer Knowledge Base
Runs all initialization steps in one go
"""

import os
import sys
import subprocess
from pathlib import Path

def print_header(text):
    """Print formatted header"""
    print("\n" + "="*70)
    print(f"  {text}")
    print("="*70 + "\n")

def check_env_file():
    """Check if .env file exists"""
    if not Path(".env").exists():
        print("⚠ .env file not found!")
        print("\nCreating .env from template...")
        
        if Path(".env.example").exists():
            import shutil
            shutil.copy(".env.example", ".env")
            print("✓ Created .env file")
            print("\n⚠ IMPORTANT: Edit .env and add your API keys:")
            print("  - OPENAI_API_KEY (required for embeddings and chatbot)")
            print("  - DATABASE_URL (optional, defaults to SQLite)")
            
            response = input("\nHave you added your API keys? (y/n): ")
            if response.lower() != 'y':
                print("\nPlease edit .env and run this script again.")
                return False
        else:
            print("✗ .env.example not found!")
            return False
    
    return True

def check_dependencies():
    """Check if dependencies are installed"""
    print("Checking dependencies...")
    try:
        import fastapi
        import sqlalchemy
        import openai
        print("✓ Core dependencies installed")
        return True
    except ImportError as e:
        print(f"✗ Missing dependency: {e}")
        print("\nInstalling dependencies...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        return True

def init_database():
    """Initialize database"""
    print("Initializing database...")
    result = subprocess.run([sys.executable, "scripts/init_database.py"])
    return result.returncode == 0

def start_api():
    """Start API server"""
    print("\nStarting API server...")
    print("Access the API at: http://localhost:8000")
    print("API Documentation: http://localhost:8000/docs")
    print("\nPress Ctrl+C to stop the server\n")
    
    try:
        subprocess.run([
            sys.executable, "-m", "uvicorn",
            "api.main:app",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--reload"
        ])
    except KeyboardInterrupt:
        print("\n\nServer stopped.")

def main():
    """Main quick start function"""
    print_header("Healthcare Payer Knowledge Base - Quick Start")
    
    print("This script will:")
    print("1. Check environment configuration")
    print("2. Install dependencies (if needed)")
    print("3. Initialize database")
    print("4. Start API server")
    
    response = input("\nContinue? (y/n): ")
    if response.lower() != 'y':
        print("Aborted.")
        return 1
    
    # Step 1: Check environment
    print_header("Step 1: Environment Configuration")
    if not check_env_file():
        return 1
    
    # Step 2: Check dependencies
    print_header("Step 2: Dependencies")
    if not check_dependencies():
        print("✗ Failed to install dependencies")
        return 1
    
    # Step 3: Initialize database
    print_header("Step 3: Database Initialization")
    if not init_database():
        print("✗ Database initialization failed")
        print("Check the error messages above and try again.")
        return 1
    
    # Step 4: Start API
    print_header("Step 4: Starting API Server")
    start_api()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
