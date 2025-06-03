#!/usr/bin/env python3
"""
Environment variable checker script.
Run this script to verify your environment variables are loaded correctly.
"""

import os
import sys
from dotenv import load_dotenv

# Try to load from absolute path
script_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(script_dir, '.env')

print(f"Script directory: {script_dir}")
print(f"Looking for .env at: {env_path}")
print(f".env file exists: {os.path.exists(env_path)}")

# Try loading the .env file
load_dotenv(dotenv_path=env_path)

# Check for critical environment variables
required_vars = [
    "OPENAI_API_KEY",
    "WATI_API_KEY",
    "WATI_API_URL"
]

print("\nEnvironment Variable Check:")
print("=" * 30)

all_vars_present = True
for var in required_vars:
    value = os.getenv(var)
    is_set = value is not None and value != ""
    print(f"{var}: {'✅ Set' if is_set else '❌ NOT SET'}")
    if not is_set:
        all_vars_present = False

print("\n" + "=" * 30)
if all_vars_present:
    print("✅ All required environment variables are set!")
else:
    print("❌ Some environment variables are missing!")
    print("\nMake sure your .env file exists and has the correct format:")
    print("OPENAI_API_KEY=sk-your-key-here")
    print("WATI_API_KEY=your-wati-key")
    print("WATI_API_URL=https://your-wati-url")

# If .env file not found, help create one
if not os.path.exists(env_path):
    print("\nWould you like to create a .env file now? (y/n)")
    response = input().strip().lower()
    if response == 'y':
        print("\nEnter your OpenAI API Key (starts with 'sk-'):")
        openai_key = input().strip()
        
        print("Enter your Wati API Key:")
        wati_key = input().strip()
        
        print("Enter your Wati API URL (press Enter for default):")
        wati_url = input().strip() or "https://live-mt-server.wati.io/301269/api/v1"
        
        with open(env_path, 'w') as f:
            f.write(f"OPENAI_API_KEY={openai_key}\n")
            f.write(f"WATI_API_KEY={wati_key}\n") 
            f.write(f"WATI_API_URL={wati_url}\n")
            f.write("WATI_WEBHOOK_VERIFY_TOKEN=your_verification_token\n")
        
        print(f"\n✅ .env file created at {env_path}") 