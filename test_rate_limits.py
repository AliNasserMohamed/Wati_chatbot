#!/usr/bin/env python3
"""
Test script to check OpenAI rate limiting configuration
Run this to verify your settings work with your OpenAI plan
"""

import asyncio
import time
import os
from dotenv import load_dotenv
from openai import AsyncOpenAI

# Load environment variables
load_dotenv()

async def test_rate_limits():
    """Test current rate limiting configuration"""
    
    # Get OpenAI client
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not found in .env file")
        return
    
    client = AsyncOpenAI(api_key=api_key)
    
    # Get rate limiting settings
    min_interval = float(os.getenv("OPENAI_MIN_REQUEST_INTERVAL", "0.5"))
    max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "3"))
    base_delay = float(os.getenv("OPENAI_BASE_DELAY", "1"))
    
    print(f"🔧 Testing with configuration:")
    print(f"   - Min interval: {min_interval}s")
    print(f"   - Max retries: {max_retries}")
    print(f"   - Base delay: {base_delay}s")
    print()
    
    # Test multiple rapid requests
    test_requests = 5
    print(f"🧪 Making {test_requests} test requests...")
    
    for i in range(test_requests):
        try:
            start_time = time.time()
            
            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",  # Use cheaper model for testing
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=5
            )
            
            duration = time.time() - start_time
            print(f"✅ Request {i+1}: Success in {duration:.2f}s")
            
            # Apply configured delay
            if i < test_requests - 1:  # Don't delay after last request
                await asyncio.sleep(min_interval)
                
        except Exception as e:
            print(f"❌ Request {i+1}: Failed - {str(e)}")
            
            # If rate limited, apply exponential backoff
            if "429" in str(e):
                delay = base_delay * (2 ** i)
                print(f"   ⏳ Rate limited, waiting {delay:.1f}s...")
                await asyncio.sleep(delay)
    
    print()
    print("🎯 Test completed!")
    print("💡 If you see 429 errors, increase OPENAI_MIN_REQUEST_INTERVAL in your .env file")

if __name__ == "__main__":
    asyncio.run(test_rate_limits()) 