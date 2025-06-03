#!/usr/bin/env python3
"""
Script to check if all required environment variables are properly configured
"""

import os
from pathlib import Path

def check_environment():
    """Check if all required environment variables are set"""
    
    # Check if .env file exists
    env_file = Path(".env")
    if not env_file.exists():
        print("❌ .env file not found!")
        print("💡 Please copy env.example to .env and fill in your values:")
        print("   cp env.example .env")
        return False
    
    print("✅ .env file found")
    
    # Required environment variables
    required_vars = {
        "OPENAI_API_KEY": "OpenAI API for AI responses",
        "GEMINI_API_KEY": "Google Gemini API for audio processing", 
        "WATI_API_KEY": "Wati API for WhatsApp messaging",
        "WATI_WEBHOOK_VERIFY_TOKEN": "Wati webhook verification token"
    }
    
    # Special handling for Wati URL (can be either variable name)
    wati_url_vars = ["WATI_API_URL", "WATI_INSTANCE_ID"]
    
    print(f"\n🔍 Checking {len(required_vars)} required environment variables...")
    
    missing_vars = []
    configured_vars = []
    
    for var_name, description in required_vars.items():
        value = os.getenv(var_name)
        if not value:
            missing_vars.append((var_name, description))
            print(f"❌ {var_name}: Not set")
        else:
            configured_vars.append(var_name)
            # Show partial value for security
            if len(value) > 10:
                display_value = f"{value[:8]}...{value[-4:]}"
            else:
                display_value = f"{value[:4]}..."
            print(f"✅ {var_name}: {display_value}")
    
    # Check for Wati URL (either variable name)
    wati_url = None
    wati_url_var = None
    for var_name in wati_url_vars:
        value = os.getenv(var_name)
        if value:
            wati_url = value
            wati_url_var = var_name
            break
    
    if wati_url:
        configured_vars.append("WATI_URL")
        if len(wati_url) > 30:
            display_value = f"{wati_url[:20]}...{wati_url[-10:]}"
        else:
            display_value = wati_url
        print(f"✅ {wati_url_var}: {display_value}")
    else:
        missing_vars.append(("WATI_API_URL or WATI_INSTANCE_ID", "Wati API base URL (e.g., https://live-mt-server.wati.io/YOUR_ACCOUNT_ID/api/v1)"))
        print(f"❌ WATI_API_URL/WATI_INSTANCE_ID: Not set")
    
    # Optional variables
    optional_vars = {
        "HOST": "Server host (defaults to 0.0.0.0)",
        "PORT": "Server port (defaults to 8000)",
        "LOG_LEVEL": "Logging level (defaults to INFO)"
    }
    
    print(f"\n🔍 Checking {len(optional_vars)} optional environment variables...")
    
    for var_name, description in optional_vars.items():
        value = os.getenv(var_name)
        if value:
            print(f"✅ {var_name}: {value}")
        else:
            print(f"⚪ {var_name}: Not set (will use default)")
    
    # Summary
    total_required = len(required_vars) + 1  # +1 for the Wati URL
    configured_count = len(configured_vars)
    
    print(f"\n📊 Configuration Summary:")
    print(f"✅ Configured: {configured_count}/{total_required} required variables")
    
    if missing_vars:
        print(f"❌ Missing: {len(missing_vars)} required variables")
        print(f"\n🔧 Missing Variables:")
        for var_name, description in missing_vars:
            print(f"   • {var_name}: {description}")
        
        print(f"\n💡 To fix this:")
        print(f"   1. Edit your .env file")
        print(f"   2. Add the missing variables with your actual values")
        print(f"   3. Restart your application")
        
        return False
    else:
        print(f"🎉 All required environment variables are configured!")
        return True

if __name__ == "__main__":
    check_environment() 