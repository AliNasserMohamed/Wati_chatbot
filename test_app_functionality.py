#!/usr/bin/env python3
"""
Script to test the app's knowledge management functionality
Tests the API endpoints after cleaning the database
"""

import requests
import json
import time
import sys

# Wait for app to start
time.sleep(3)

BASE_URL = "http://localhost:8000"

def test_api_endpoint(endpoint, method="GET", data=None, description=""):
    """Test an API endpoint"""
    print(f"\n🧪 Testing: {description}")
    print(f"   {method} {endpoint}")
    
    try:
        if method == "GET":
            response = requests.get(f"{BASE_URL}{endpoint}")
        elif method == "POST":
            response = requests.post(f"{BASE_URL}{endpoint}", json=data)
        elif method == "PUT":
            response = requests.put(f"{BASE_URL}{endpoint}", json=data)
        
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"   ✅ Success: {json.dumps(result, ensure_ascii=False, indent=2)}")
            return result
        else:
            print(f"   ❌ Error: {response.text}")
            return None
            
    except requests.exceptions.ConnectionError:
        print(f"   ❌ Connection Error: App not running or not accessible")
        return None
    except Exception as e:
        print(f"   ❌ Exception: {str(e)}")
        return None

def main():
    """Run all API tests"""
    print("🚀 Testing App Functionality After Database Cleanup")
    print("=" * 60)
    
    # Test 1: Check if app is running
    health = test_api_endpoint("/health", "GET", description="Health Check")
    if not health:
        print("❌ App is not running. Please start the app first.")
        return
    
    # Test 2: Get initial knowledge stats (should be empty)
    test_api_endpoint("/knowledge/stats", "GET", description="Initial Knowledge Stats (should be empty)")
    
    # Test 3: List knowledge (should be empty)
    test_api_endpoint("/knowledge/list", "GET", description="List Knowledge (should be empty)")
    
    # Test 4: Add a new question
    new_qa = {
        "question": "ما هو تطبيق ابار؟",
        "answer": "تطبيق ابار هو تطبيق لتوصيل المياه المعبأة من أكثر من 200 علامة تجارية مختلفة للمياه.",
        "metadata": {
            "category": "general_info",
            "source": "test",
            "priority": "high"
        }
    }
    
    add_result = test_api_endpoint("/knowledge/add", "POST", new_qa, 
                                 "Add New Q&A Pair")
    
    # Test 5: Try to add the same question again (should detect duplicate)
    if add_result:
        test_api_endpoint("/knowledge/add", "POST", new_qa, 
                         "Add Duplicate Q&A (should be detected)")
    
    # Test 6: Check duplicate endpoint directly
    duplicate_check = {
        "question": "ما هو تطبيق ابار؟",
        "similarity_threshold": 0.85
    }
    
    test_api_endpoint("/knowledge/check-duplicate", "POST", duplicate_check,
                     "Check Duplicate Question")
    
    # Test 7: Search for the added question
    test_api_endpoint("/knowledge/search?query=ما هو ابار&n_results=3", "GET",
                     description="Search Knowledge Base")
    
    # Test 8: Populate default knowledge
    test_api_endpoint("/knowledge/populate", "POST", description="Populate Default Knowledge")
    
    # Test 9: Check final stats
    test_api_endpoint("/knowledge/stats", "GET", description="Final Knowledge Stats")
    
    # Test 10: List all knowledge after population
    final_list = test_api_endpoint("/knowledge/list", "GET", description="Final Knowledge List")
    
    if final_list:
        total_items = final_list.get("total", 0)
        print(f"\n📊 Final Summary:")
        print(f"   Total Q&A pairs in database: {total_items}")
        print(f"   Vector database properly updated: {'✅' if total_items > 0 else '❌'}")
    
    print("\n" + "=" * 60)
    print("🎉 API Testing Complete!")
    print("\nYou can now:")
    print("1. Open http://localhost:8000/knowledge/admin to test the frontend")
    print("2. Try adding questions through the web interface")
    print("3. Test the 'تحميل البيانات الافتراضية' button")

if __name__ == "__main__":
    main() 