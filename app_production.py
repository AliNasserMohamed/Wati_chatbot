#!/usr/bin/env python3
import os
import sys
import uvicorn
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import the main app
from app import app

if __name__ == "__main__":
    # Starting production server
    
    # Run without auto-reload to prevent restart issues
    uvicorn.run(
        "app:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=False  # Disable auto-reload
    ) 