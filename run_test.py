#!/usr/bin/env python3
"""
Simple script to run the embedding agent test
Usage: python run_test.py
"""

import sys
import os
import asyncio
from pathlib import Path

# Add the current directory to Python path
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# Check for .env file
env_file = current_dir / ".env"
if not env_file.exists():
    print("❌ ERROR: .env file not found!")
    print("Please create a .env file with your OPENAI_API_KEY")
    print("Example:")
    print("OPENAI_API_KEY=your_openai_api_key_here")
    sys.exit(1)

# Import and run the test
try:
    from test_embedding_agent import main
    print("🚀 Starting Abar Embedding Agent Test...")
    asyncio.run(main())
except ImportError as e:
    print(f"❌ Import Error: {e}")
    print("Please make sure all dependencies are installed:")
    print("pip install -r requirements.txt")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error running test: {e}")
    sys.exit(1) 