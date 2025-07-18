import requests
import json
import time

# Test data
test_data = {
    "question": "test question",
    "answer": "test answer",
    "metadata": {
        "category": "general",
        "source": "admin",
        "priority": "normal"
    }
}

print("=" * 50)
print("Testing /knowledge/add endpoint...")
print("=" * 50)

# Test 1: Check if server is running
server_urls = [
    "http://localhost:8000/health",
    "http://127.0.0.1:8000/health",
    "http://0.0.0.0:8000/health"
]

server_working = False
working_url = None

for url in server_urls:
    try:
        print(f"1. Testing server connection to {url}...")
        response = requests.get(url, timeout=5)
        print(f"   ✅ Server is running (status: {response.status_code})")
        if response.status_code == 200:
            health_data = response.json()
            print(f"   Server health: {health_data}")
            server_working = True
            working_url = url.replace("/health", "")
            break
    except Exception as e:
        print(f"   ❌ Server connection failed: {e}")
        continue

if not server_working:
    print("❌ Unable to connect to server on any address")
    exit(1)

# Test 2: Test the add endpoint
try:
    print("\n2. Testing /knowledge/add endpoint...")
    print(f"   Data: {json.dumps(test_data, indent=2)}")
    
    start_time = time.time()
    response = requests.post(
        f"{working_url}/knowledge/add",
        json=test_data,
        headers={"Content-Type": "application/json"},
        timeout=30
    )
    end_time = time.time()
    
    print(f"   Request took: {end_time - start_time:.2f} seconds")
    print(f"   Status code: {response.status_code}")
    print(f"   Response headers: {dict(response.headers)}")
    print(f"   Response body: {response.text}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"   ✅ Success: {result}")
    else:
        print(f"   ❌ Error: {response.text}")
        
except requests.exceptions.Timeout:
    print("   ❌ Request timed out (30 seconds)")
except Exception as e:
    print(f"   ❌ Error testing endpoint: {e}")

print("\n" + "=" * 50)
print("Test completed")
print("=" * 50)