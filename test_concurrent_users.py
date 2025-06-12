#!/usr/bin/env python3
"""
Test script to verify concurrent user processing
This script simulates multiple users sending messages simultaneously
to test if the bot can handle concurrent requests properly.
"""

import asyncio
import aiohttp
import json
import time
from datetime import datetime

# Test configuration
WEBHOOK_URL = "http://localhost:8000/webhook"  # Update if your server runs on different port
TEST_USERS = [
    "201142765209",  # User 1
    "966138686475",  # User 2 
    "966505281144",  # User 3
    "966541794866",  # User 4
    "201003754330",  # User 5
]

TEST_MESSAGES = [
    "السلام عليكم",
    "مرحبا كيف الحال؟", 
    "ما هي المدن المتاحة؟",
    "أريد أسعار المياه",
    "شكرا لكم"
]

async def send_webhook_message(session, user_phone, message, delay=0):
    """Send a message to the webhook as if it came from Wati"""
    if delay > 0:
        await asyncio.sleep(delay)
    
    # Simulate Wati webhook payload
    payload = {
        "waId": user_phone,
        "type": "text",
        "id": f"test_msg_{user_phone}_{int(time.time()*1000)}",
        "text": message,
        "timestamp": int(time.time())
    }
    
    start_time = time.time()
    print(f"📤 [{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] Sending message from {user_phone}: '{message[:30]}...'")
    
    try:
        async with session.post(WEBHOOK_URL, json=payload) as response:
            response_time = time.time() - start_time
            status = response.status
            result = await response.json()
            
            print(f"✅ [{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] Response from {user_phone}: HTTP {status} in {response_time:.3f}s - {result.get('message', 'OK')}")
            return {"user": user_phone, "status": status, "response_time": response_time, "success": status == 200}
            
    except Exception as e:
        response_time = time.time() - start_time
        print(f"❌ [{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] Error from {user_phone}: {str(e)} in {response_time:.3f}s")
        return {"user": user_phone, "status": 0, "response_time": response_time, "success": False, "error": str(e)}

async def test_concurrent_users():
    """Test multiple users sending messages simultaneously"""
    print("🧪 Testing Concurrent User Processing")
    print("=" * 60)
    print(f"Test Users: {len(TEST_USERS)}")
    print(f"Test Messages: {len(TEST_MESSAGES)}")
    print("=" * 60)
    
    async with aiohttp.ClientSession() as session:
        # Test 1: All users send messages at exactly the same time
        print("\n🚀 TEST 1: Simultaneous Messages (No Delay)")
        print("-" * 40)
        
        tasks = []
        for i, user in enumerate(TEST_USERS):
            message = TEST_MESSAGES[i % len(TEST_MESSAGES)]
            task = send_webhook_message(session, user, message, delay=0)
            tasks.append(task)
        
        # Execute all requests simultaneously
        start_time = time.time()
        results1 = await asyncio.gather(*tasks)
        total_time1 = time.time() - start_time
        
        print(f"\n📊 TEST 1 RESULTS:")
        print(f"   Total Time: {total_time1:.3f}s")
        print(f"   Successful Requests: {sum(1 for r in results1 if r['success'])}/{len(results1)}")
        print(f"   Average Response Time: {sum(r['response_time'] for r in results1)/len(results1):.3f}s")
        
        # Wait a bit before next test
        print(f"\n⏳ Waiting 5 seconds before next test...")
        await asyncio.sleep(5)
        
        # Test 2: Staggered messages with small delays
        print("\n🚀 TEST 2: Staggered Messages (0.5s delays)")
        print("-" * 40)
        
        tasks = []
        for i, user in enumerate(TEST_USERS):
            message = f"رسالة رقم {i+1}: {TEST_MESSAGES[i % len(TEST_MESSAGES)]}"
            task = send_webhook_message(session, user, message, delay=i*0.5)
            tasks.append(task)
        
        start_time = time.time()
        results2 = await asyncio.gather(*tasks)
        total_time2 = time.time() - start_time
        
        print(f"\n📊 TEST 2 RESULTS:")
        print(f"   Total Time: {total_time2:.3f}s")
        print(f"   Successful Requests: {sum(1 for r in results2 if r['success'])}/{len(results2)}")
        print(f"   Average Response Time: {sum(r['response_time'] for r in results2)/len(results2):.3f}s")
        
        # Wait a bit before next test  
        print(f"\n⏳ Waiting 5 seconds before next test...")
        await asyncio.sleep(5)
        
        # Test 3: Rapid fire from single user
        print("\n🚀 TEST 3: Rapid Fire from Single User")
        print("-" * 40)
        
        rapid_user = TEST_USERS[0]
        tasks = []
        for i in range(5):
            message = f"رسالة سريعة {i+1}: مرحبا"
            task = send_webhook_message(session, rapid_user, message, delay=i*0.2)
            tasks.append(task)
        
        start_time = time.time()
        results3 = await asyncio.gather(*tasks)
        total_time3 = time.time() - start_time
        
        print(f"\n📊 TEST 3 RESULTS:")
        print(f"   Total Time: {total_time3:.3f}s")
        print(f"   Successful Requests: {sum(1 for r in results3 if r['success'])}/{len(results3)}")
        print(f"   Average Response Time: {sum(r['response_time'] for r in results3)/len(results3):.3f}s")
        
        # Final Summary
        print("\n" + "=" * 60)
        print("🏁 FINAL SUMMARY")
        print("=" * 60)
        
        all_results = results1 + results2 + results3
        total_requests = len(all_results)
        successful_requests = sum(1 for r in all_results if r['success'])
        
        print(f"Total Requests Sent: {total_requests}")
        print(f"Successful Requests: {successful_requests}")
        print(f"Success Rate: {(successful_requests/total_requests)*100:.1f}%")
        print(f"Overall Average Response Time: {sum(r['response_time'] for r in all_results)/len(all_results):.3f}s")
        
        if successful_requests == total_requests:
            print("✅ All tests passed! Concurrent processing is working correctly.")
        else:
            print("⚠️ Some requests failed. Check server logs for details.")
            failed_requests = [r for r in all_results if not r['success']]
            for req in failed_requests:
                print(f"   Failed: {req['user']} - {req.get('error', 'Unknown error')}")

async def main():
    """Main test function"""
    print("🤖 Wati Chatbot Concurrent User Test")
    print("=" * 60)
    print("This script tests if multiple users can send messages")
    print("to the chatbot simultaneously without blocking each other.")
    print("=" * 60)
    print("⚠️  Make sure your chatbot server is running on localhost:8000")
    print("⚠️  Make sure the test phone numbers are in your allowed list")
    print("=" * 60)
    
    input("Press Enter to start the test...")
    
    try:
        await test_concurrent_users()
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Run the test
    asyncio.run(main()) 