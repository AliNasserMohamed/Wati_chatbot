#!/usr/bin/env python3
"""
Test script for the knowledge base admin functionality
"""

import requests
import json
import time
from datetime import datetime

def test_knowledge_api():
    base_url = "http://localhost:8000"
    
    print("🧪 Testing Knowledge Base Admin API")
    print("=" * 50)
    
    # Test data
    test_qa = {
        "question": "كيف يمكنني تسجيل الدخول في تطبيق ابار؟",
        "answer": "يمكنك تسجيل الدخول في تطبيق ابار بإدخال رقم جوالك والضغط على زر تسجيل الدخول، ثم ستصلك رسالة نصية بكود التحقق.",
        "metadata": {
            "category": "support",
            "source": "test",
            "priority": "high",
            "created_at": datetime.now().isoformat()
        }
    }
    
    try:
        # 1. Test adding Q&A
        print("1️⃣ Testing add Q&A...")
        response = requests.post(f"{base_url}/knowledge/add", json=test_qa)
        if response.status_code == 200:
            result = response.json()
            print(f"   ✅ Added Q&A with ID: {result.get('id')}")
            qa_id = result.get('id')
        else:
            print(f"   ❌ Failed to add Q&A: {response.status_code}")
            return
        
        # 2. Test listing Q&A
        print("2️⃣ Testing list Q&A...")
        response = requests.get(f"{base_url}/knowledge/list")
        if response.status_code == 200:
            result = response.json()
            items = result.get('items', [])
            print(f"   ✅ Listed {len(items)} Q&A pairs")
            for item in items[:3]:  # Show first 3
                print(f"      - {item.get('question', 'N/A')[:50]}...")
        else:
            print(f"   ❌ Failed to list Q&A: {response.status_code}")
        
        # 3. Test searching Q&A
        print("3️⃣ Testing search Q&A...")
        response = requests.get(f"{base_url}/knowledge/search?query=تسجيل الدخول&n_results=3")
        if response.status_code == 200:
            result = response.json()
            results = result.get('results', [])
            print(f"   ✅ Found {len(results)} search results")
            for res in results:
                print(f"      - {res.get('document', 'N/A')[:50]}...")
        else:
            print(f"   ❌ Failed to search Q&A: {response.status_code}")
        
        # 4. Test updating Q&A
        if qa_id:
            print("4️⃣ Testing update Q&A...")
            update_data = {
                "id": qa_id,
                "question": "كيف يمكنني تسجيل الدخول في تطبيق ابار؟ (محدث)",
                "answer": "يمكنك تسجيل الدخول في تطبيق ابار بإدخال رقم جوالك، ثم ستصلك رسالة نصية بكود التحقق لتأكيد الدخول. (محدث)",
                "metadata": {
                    "category": "support",
                    "source": "test_updated",
                    "priority": "high",
                    "updated_at": datetime.now().isoformat()
                }
            }
            response = requests.put(f"{base_url}/knowledge/update", json=update_data)
            if response.status_code == 200:
                print(f"   ✅ Updated Q&A successfully")
            else:
                print(f"   ❌ Failed to update Q&A: {response.status_code}")
        
        # 5. Test populating default knowledge
        print("5️⃣ Testing populate default knowledge...")
        response = requests.post(f"{base_url}/knowledge/populate")
        if response.status_code == 200:
            result = response.json()
            print(f"   ✅ Populated default knowledge: {result.get('message')}")
        else:
            print(f"   ❌ Failed to populate default knowledge: {response.status_code}")
        
        # 6. Test deleting Q&A
        if qa_id:
            print("6️⃣ Testing delete Q&A...")
            response = requests.delete(f"{base_url}/knowledge/delete/{qa_id}")
            if response.status_code == 200:
                print(f"   ✅ Deleted Q&A successfully")
            else:
                print(f"   ❌ Failed to delete Q&A: {response.status_code}")
        
        print("\n🎉 All tests completed!")
        print(f"📋 You can now access the admin interface at: {base_url}/knowledge/admin")
        
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to the server. Make sure it's running on http://localhost:8000")
        print("📝 To start the server, run: python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000")
    except Exception as e:
        print(f"❌ Test failed with error: {str(e)}")

def test_direct_knowledge_manager():
    """Test the knowledge manager directly without API"""
    print("\n🔧 Testing Knowledge Manager directly...")
    print("=" * 50)
    
    try:
        # Import the knowledge manager
        from utils.knowledge_manager import knowledge_manager
        
        # Test adding Q&A
        print("1️⃣ Testing direct add Q&A...")
        qa_id = knowledge_manager.add_qa_pair(
            "ما هي ساعات العمل لخدمة العملاء؟",
            "خدمة العملاء متاحة على مدار الساعة طوال أيام الأسبوع لخدمتكم.",
            {"category": "support", "source": "direct_test"}
        )
        print(f"   ✅ Added Q&A with ID: {qa_id}")
        
        # Test searching
        print("2️⃣ Testing direct search...")
        results = knowledge_manager.search_knowledge("ساعات العمل", 3)
        print(f"   ✅ Found {len(results)} results")
        for result in results:
            print(f"      - {result.get('document', 'N/A')[:50]}...")
        
        # Test populating default knowledge
        print("3️⃣ Testing populate default knowledge...")
        ids = knowledge_manager.populate_abar_knowledge()
        print(f"   ✅ Populated {len(ids)} default Q&A pairs")
        
        print("\n✅ Direct knowledge manager tests completed!")
        
    except Exception as e:
        print(f"❌ Direct test failed: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🚀 Knowledge Base Admin Test Suite")
    print("=" * 60)
    
    # Test the knowledge manager directly first
    test_direct_knowledge_manager()
    
    # Then test the API (if server is running)
    print("\n" + "=" * 60)
    test_knowledge_api() 