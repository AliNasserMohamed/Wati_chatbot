#!/usr/bin/env python3
"""
Test script to verify the improved classification system with business context
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agents.message_classifier import message_classifier
from database.db_utils import SessionLocal, DatabaseManager
from database.db_models import MessageType, UserMessage

async def test_enhanced_classification():
    """Test the enhanced classification with business context"""
    
    print("🧪 Testing Enhanced Message Classification")
    print("=" * 60)
    
    test_cases = [
        {
            "message": "السلام عليكم",
            "expected": MessageType.GREETING,
            "description": "Direct greeting"
        },
        {
            "message": "مرحبا، كيف حالكم؟",
            "expected": MessageType.GREETING,
            "description": "Greeting with question"
        },
        {
            "message": "شكراً لكم على الخدمة الممتازة",
            "expected": MessageType.SUGGESTION,
            "description": "Positive feedback"
        },
        {
            "message": "أريد طلب مياه للمنزل",
            "expected": MessageType.SERVICE_REQUEST,
            "description": "Water delivery request"
        },
        {
            "message": "هل تغطون مدينة الرياض؟",
            "expected": MessageType.INQUIRY,
            "description": "City coverage inquiry"
        },
        {
            "message": "التوصيل متأخر والمياه ما وصلت",
            "expected": MessageType.COMPLAINT,
            "description": "Delivery complaint"
        },
        {
            "message": "كيف حالكم اليوم؟",
            "expected": MessageType.OTHERS,
            "description": "General question (not greeting)"
        },
        {
            "message": "1",
            "expected": MessageType.TEMPLATE_REPLY,
            "description": "Number response (template reply)"
        },
        {
            "message": "نعم",
            "expected": MessageType.TEMPLATE_REPLY,
            "description": "Yes/No response (template reply)"
        },
        {
            "message": "ما هي أسعار التوصيل؟",
            "expected": MessageType.INQUIRY,
            "description": "Pricing inquiry"
        },
        {
            "message": "اضافة احمد محمد",
            "expected": MessageType.OTHERS,
            "description": "General message"
        },
        {
            "message": "غير راضي عن الخدمة",
            "expected": MessageType.COMPLAINT,
            "description": "Service complaint"
        }
    ]
    
    db = SessionLocal()
    
    try:
        # Create a test user
        user = DatabaseManager.get_user_by_phone(db, "966501234567")
        if not user:
            user = DatabaseManager.create_user(db, "966501234567")
        
        correct_classifications = 0
        total_tests = len(test_cases)
        
        for i, case in enumerate(test_cases, 1):
            print(f"\n{i}. Testing: '{case['message']}'")
            print(f"   Expected: {case['expected'].value}")
            print(f"   Context: {case['description']}")
            
            # Create a temporary message
            temp_message = UserMessage(
                user_id=user.id,
                content=case['message']
            )
            
            try:
                # Test classification
                classified_type, detected_language = await message_classifier.classify_message(
                    case['message'], 
                    db, 
                    temp_message,
                    conversation_history=[]
                )
                
                if classified_type:
                    print(f"   🤖 Classified as: {classified_type.value}")
                    print(f"   🌐 Language: {detected_language}")
                    
                    if classified_type == case['expected']:
                        print(f"   ✅ CORRECT classification!")
                        correct_classifications += 1
                    else:
                        print(f"   ❌ INCORRECT! Expected: {case['expected'].value}")
                else:
                    print(f"   ❌ Classification FAILED (returned None)")
                    
            except Exception as e:
                print(f"   ❌ Error: {str(e)}")
            
            print(f"   {'-'*50}")
        
        # Summary
        accuracy = (correct_classifications / total_tests) * 100
        print(f"\n📊 CLASSIFICATION RESULTS:")
        print(f"   ✅ Correct: {correct_classifications}/{total_tests}")
        print(f"   📈 Accuracy: {accuracy:.1f}%")
        
        if accuracy >= 80:
            print(f"   🎉 EXCELLENT classification performance!")
        elif accuracy >= 60:
            print(f"   👍 GOOD classification performance!")
        else:
            print(f"   ⚠️  NEEDS IMPROVEMENT")
            
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

async def test_template_reply_detection():
    """Test template reply detection with conversation context"""
    
    print(f"\n🧪 Testing Template Reply Detection")
    print("=" * 60)
    
    # Simulate conversation history with bot sending interactive message
    conversation_history = [
        {
            "role": "user",
            "content": "user: أريد طلب مياه",
            "timestamp": "2024-01-01 10:00:00",
            "language": "ar",
            "raw_content": "أريد طلب مياه"
        },
        {
            "role": "assistant",
            "content": "bot: اختر المدينة:\n1. الرياض\n2. جدة\n3. الدمام",
            "timestamp": "2024-01-01 10:00:01", 
            "language": "ar",
            "raw_content": "اختر المدينة:\n1. الرياض\n2. جدة\n3. الدمام"
        }
    ]
    
    template_replies = [
        "1",
        "2", 
        "3",
        "الرياض",
        "نعم",
        "لا",
        "موافق"
    ]
    
    db = SessionLocal()
    
    try:
        user = DatabaseManager.get_user_by_phone(db, "966501234567")
        if not user:
            user = DatabaseManager.create_user(db, "966501234567")
        
        correct_template_detections = 0
        
        for i, reply in enumerate(template_replies, 1):
            print(f"\n{i}. Testing template reply: '{reply}'")
            
            temp_message = UserMessage(
                user_id=user.id,
                content=reply
            )
            
            try:
                classified_type, detected_language = await message_classifier.classify_message(
                    reply,
                    db,
                    temp_message,
                    conversation_history=conversation_history
                )
                
                if classified_type:
                    print(f"   🤖 Classified as: {classified_type.value}")
                    
                    if classified_type == MessageType.TEMPLATE_REPLY:
                        print(f"   ✅ CORRECTLY detected as template reply!")
                        correct_template_detections += 1
                    else:
                        print(f"   ⚠️  Classified as {classified_type.value} (may be acceptable)")
                else:
                    print(f"   ❌ Classification failed")
                    
            except Exception as e:
                print(f"   ❌ Error: {str(e)}")
        
        template_accuracy = (correct_template_detections / len(template_replies)) * 100
        print(f"\n📊 TEMPLATE REPLY DETECTION:")
        print(f"   ✅ Detected: {correct_template_detections}/{len(template_replies)}")
        print(f"   📈 Accuracy: {template_accuracy:.1f}%")
        
    except Exception as e:
        print(f"❌ Template test failed: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_enhanced_classification())
    asyncio.run(test_template_reply_detection()) 