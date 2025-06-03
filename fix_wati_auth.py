#!/usr/bin/env python3
"""
Script to manually create a valid WATI API token and test sending a message
"""
import os
import requests
import json
from dotenv import load_dotenv

# Load environment variables
script_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(script_dir, '.env')
load_dotenv(dotenv_path=env_path)

def main():
    print("=== WATI API Auth Fix & Test ===")
    
    # Get current token
    current_token = os.getenv("WATI_API_KEY", "").strip()
    print(f"Current token: {current_token[:8]}...{current_token[-8:]}" if current_token else "No token found")
    
    # Ask for new token
    print("\nEnter your WATI API token (leave empty to keep current):")
    new_token = input().strip()
    
    # Update token if provided
    if new_token:
        # Create backup of .env
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                env_content = f.read()
            
            with open(f"{env_path}.bak", 'w') as f:
                f.write(env_content)
                print(f"Backup created: {env_path}.bak")
        
        # Update .env file
        token_to_use = new_token
        
        # Update WATI_API_KEY in .env
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                lines = f.readlines()
            
            with open(env_path, 'w') as f:
                token_found = False
                for line in lines:
                    if line.startswith('WATI_API_KEY='):
                        f.write(f"WATI_API_KEY={token_to_use}\n")
                        token_found = True
                    else:
                        f.write(line)
                
                if not token_found:
                    f.write(f"\nWATI_API_KEY={token_to_use}\n")
            
            print("Token updated in .env file")
    else:
        token_to_use = current_token
    
    # Get WATI API URL
    current_url = os.getenv("WATI_API_URL", "").strip()
    print(f"\nCurrent WATI API URL: {current_url}" if current_url else "No WATI API URL found")
    
    # Ask for new URL
    print("Enter your WATI API URL (leave empty to keep current):")
    new_url = input().strip()
    
    # Update URL if provided
    if new_url:
        # Update WATI_API_URL in .env
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                lines = f.readlines()
            
            with open(env_path, 'w') as f:
                url_found = False
                for line in lines:
                    if line.startswith('WATI_API_URL='):
                        f.write(f"WATI_API_URL={new_url}\n")
                        url_found = True
                    else:
                        f.write(line)
                
                if not url_found:
                    f.write(f"\nWATI_API_URL={new_url}\n")
            
            print("URL updated in .env file")
        url_to_use = new_url
    else:
        url_to_use = current_url if current_url else "https://live-mt-server.wati.io/301269/api/v1"
    
    # Test sending a message
    print("\nWould you like to test sending a WhatsApp message? (y/n)")
    test_response = input().strip().lower()
    
    if test_response == 'y':
        # Ask for phone number
        print("\nEnter recipient phone number (e.g., 201142765209):")
        phone_number = input().strip()
        
        # Ask for message
        print("Enter message to send:")
        message = input().strip()
        
        # Set up proper URL format
        base_url = url_to_use.rstrip('/')
        if not base_url.endswith('/api/v1'):
            if '/api/' not in base_url:
                base_url = f"{base_url}/api/v1"
        
        # Headers with cleaned token
        headers = {
            "Authorization": f"Bearer {token_to_use.strip()}",
            "Content-Type": "application/json"
        }
        
        # Payload
        payload = {"messageText": message}
        
        # Test each endpoint variation
        endpoints = [
            f"{base_url}/sendSessionMessage/{phone_number}",
            f"{base_url}/sendMessage?whatsappNumber={phone_number}",
            f"{base_url}/sendSessionMessage?whatsappNumber={phone_number}",
            f"{base_url.replace('/api/v1', '')}/sendSessionMessage/{phone_number}",
            f"{base_url.replace('/api/v1', '')}/api/v1/sendSessionMessage/{phone_number}"
        ]
        
        for i, endpoint in enumerate(endpoints, 1):
            print(f"\nTrying endpoint #{i}: {endpoint}")
            try:
                print(f"Headers: {json.dumps({k: (v if k != 'Authorization' else '[SECRET]') for k, v in headers.items()})}")
                print(f"Payload: {json.dumps(payload)}")
                
                response = requests.post(endpoint, headers=headers, json=payload)
                print(f"Status code: {response.status_code}")
                
                try:
                    response_data = response.json()
                    print(f"Response: {json.dumps(response_data, indent=2)}")
                except:
                    print(f"Raw response: {response.text}")
                
                if response.status_code < 400:
                    print(f"✅ Endpoint #{i} SUCCESSFUL!")
                    break
            except Exception as e:
                print(f"❌ Error: {str(e)}")
        
        print("\nTest completed. Check your WhatsApp to see if the message was received.")

if __name__ == "__main__":
    main() 