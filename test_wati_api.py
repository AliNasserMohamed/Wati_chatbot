#!/usr/bin/env python3
"""
Standalone script to test the Wati API connection and send a test message
"""
import os
import json
import requests
from dotenv import load_dotenv
import sys
import urllib.parse

# Load environment variables
script_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(script_dir, '.env')
load_dotenv(dotenv_path=env_path)

def test_api_key():
    """Test if the API key is properly loaded"""
    wati_api_key = os.getenv("WATI_API_KEY")
    if not wati_api_key:
        print("❌ WATI_API_KEY not found in environment variables!")
        return False
    
    # Clean the key
    wati_api_key = wati_api_key.strip()
    print(f"✅ WATI_API_KEY found: {wati_api_key[:5]}...{wati_api_key[-5:]}")
    return True

def send_test_message(phone_number):
    """Try to send a test message using the URL parameter approach"""
    wati_api_key = os.getenv("WATI_API_KEY").strip()
    wati_api_url = os.getenv("WATI_API_URL", "https://live-mt-server.wati.io/301269/api/v1").strip()
    
    # Ensure no trailing slash
    base_url = wati_api_url.rstrip('/')
    
    # Make sure the base_url has the correct format with /api/v1
    if not base_url.endswith('/api/v1'):
        if '/api/' not in base_url:
            base_url = f"{base_url}/api/v1"
    
    # Headers based on user's working example
    headers = {
        "Authorization": f"Bearer {wati_api_key}",
        "Content-Type": "application/json",
        "accept": "*/*",
        "accept-language": "en-GB,en;q=0.9,ar-EG;q=0.8,ar;q=0.7,en-US;q=0.6",
        "origin": "https://live.wati.io",
        "referer": "https://live.wati.io/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    }
    
    # Test message
    test_message = "This is a test message from the Abar Chatbot API testing script."
    encoded_message = urllib.parse.quote(test_message)
    
    print("\nTesting Working Approach (URL Parameter):")
    print("-" * 50)
    
    # URL Parameter approach
    url = f"{base_url}/sendSessionMessage/{phone_number}?messageText={encoded_message}"
    payload = {}
    
    print(f"URL: {url}")
    print(f"Method: POST")
    print(f"Headers: Authorization: Bearer [SECRET], other headers included")
    print(f"Empty payload: {payload}")
    
    try:
        response = requests.post(url, headers=headers, data=payload)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code < 400:
            print("✅ URL Parameter approach SUCCESSFUL!")
        else:
            print("❌ URL Parameter approach FAILED!")
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        
    # Now try an alternative URL format just to be thorough
    alt_url = f"{base_url}/sendMessage?whatsappNumber={phone_number}&messageText={encoded_message}"
    
    print("\nTrying Alternative URL Format:")
    print("-" * 50)
    print(f"URL: {alt_url}")
    
    try:
        alt_response = requests.post(alt_url, headers=headers, data=payload)
        print(f"Status Code: {alt_response.status_code}")
        print(f"Response: {alt_response.text}")
        
        if alt_response.status_code < 400:
            print("✅ Alternative URL format SUCCESSFUL!")
        else:
            print("❌ Alternative URL format FAILED!")
    except Exception as e:
        print(f"❌ Error: {str(e)}")

def main():
    print("🔍 Wati API Test Script (URL Parameter Approach)")
    print("=" * 50)
    
    # Check if API key is available
    if not test_api_key():
        sys.exit(1)
    
    # Get phone number from command line or prompt user
    if len(sys.argv) > 1:
        phone_number = sys.argv[1]
    else:
        print("\nEnter the phone number to test (e.g., 201142765209):")
        phone_number = input().strip()
    
    send_test_message(phone_number)

if __name__ == "__main__":
    main() 