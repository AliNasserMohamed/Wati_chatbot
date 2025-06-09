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
        },
        {
            "message": "راضي تماماً",
            "expected": MessageType.TEMPLATE_REPLY,
            "description": "Satisfaction response (template reply)"
        },
        {
            "message": "شكراً لكم",
            "expected": MessageType.TEMPLATE_REPLY,
            "description": "Thank you message (template reply)"
        },
        {
            "message": "ممتاز",
            "expected": MessageType.TEMPLATE_REPLY,
            "description": "Excellent response (template reply)"
        },
        {
            "message": "ايش",
            "expected": MessageType.OTHERS,
            "description": "Unclear question word"
        },
        {
            "message": "بدي",
            "expected": MessageType.OTHERS,
            "description": "Vague want statement"
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
            
            # Save the message to get an ID
            db.add(temp_message)
            db.commit()
            db.refresh(temp_message)
            
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

async def test_unclear_message_detection():
    """Test unclear message detection functionality"""
    
    print(f"\n🧪 Testing Unclear Message Detection")
    print("=" * 60)
    
    test_cases = [
        {"message": "ايش", "should_be_unclear": True, "description": "Single question word"},
        {"message": "وش", "should_be_unclear": True, "description": "Single question word (dialect)"},
        {"message": "بدي", "should_be_unclear": True, "description": "I want (without object)"},
        {"message": "نعم", "should_be_unclear": True, "description": "Yes (without context)"},
        {"message": "1", "should_be_unclear": True, "description": "Number only (without context)"},
        {"message": "أريد طلب مياه", "should_be_unclear": False, "description": "Clear request"},
        {"message": "هل تغطون الرياض؟", "should_be_unclear": False, "description": "Clear question"},
        {"message": "السلام عليكم", "should_be_unclear": False, "description": "Clear greeting"},
        {"message": "شكراً لكم على الخدمة", "should_be_unclear": False, "description": "Clear thank you"},
        {"message": "ايش أسعار التوصيل؟", "should_be_unclear": False, "description": "Question with context"},
    ]
    
    correct_detections = 0
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n{i}. Testing: '{case['message']}'")
        print(f"   Should be unclear: {case['should_be_unclear']}")
        print(f"   Context: {case['description']}")
        
        try:
            is_unclear = await message_classifier.is_message_unclear(
                case['message'], 
                conversation_history=[]
            )
            
            print(f"   🤖 Detected as unclear: {is_unclear}")
            
            if is_unclear == case['should_be_unclear']:
                print(f"   ✅ CORRECT detection!")
                correct_detections += 1
            else:
                expected = "unclear" if case['should_be_unclear'] else "clear"
                actual = "unclear" if is_unclear else "clear"
                print(f"   ❌ INCORRECT! Expected: {expected}, Got: {actual}")
                
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
    
    accuracy = (correct_detections / len(test_cases)) * 100
    print(f"\n📊 UNCLEAR MESSAGE DETECTION:")
    print(f"   ✅ Correct: {correct_detections}/{len(test_cases)}")
    print(f"   📈 Accuracy: {accuracy:.1f}%")

async def test_wati_template_detection():
    """Test WATI template reply detection and skipping"""
    
    print(f"\n🧪 Testing WATI Template Reply Detection")
    print("=" * 60)
    
    # Mock webhook data examples
    test_cases = [
        {
            "name": "Button Reply",
            "webhook_data": {
                "id": "684704bdf80d7781b4b38929",
                "type": "button",
                "text": "راضي تماماً",
                "waId": "966537631543",
                "buttonReply": {
                    "payload": "{\"ButtonIndex\":0,\"CarouselCardIndex\":null}",
                    "text": "راضي تماماً"
                }
            },
            "should_skip": True
        },
        {
            "name": "List Reply",
            "webhook_data": {
                "id": "684704bdf80d7781b4b38930",
                "type": "list",
                "text": "الرياض",
                "waId": "966537631543",
                "listReply": {
                    "id": "city_riyadh",
                    "title": "الرياض"
                }
            },
            "should_skip": True
        },
        {
            "name": "Interactive Button Reply",
            "webhook_data": {
                "id": "684704bdf80d7781b4b38931",
                "type": "interactive",
                "text": "نعم",
                "waId": "966537631543",
                "interactiveButtonReply": {
                    "id": "confirm_yes",
                    "title": "نعم"
                }
            },
            "should_skip": True
        },
        {
            "name": "Regular Text Message",
            "webhook_data": {
                "id": "684704bdf80d7781b4b38932",
                "type": "text",
                "text": "السلام عليكم",
                "waId": "966537631543"
            },
            "should_skip": False
        }
    ]
    
    print("Testing WATI template detection logic:")
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n{i}. Testing: {case['name']}")
        print(f"   Should skip: {case['should_skip']}")
        
        data = case['webhook_data']
        
        # Extract the same fields as in app.py
        message_type = data.get("type", "text")
        button_reply = data.get("buttonReply")
        list_reply = data.get("listReply") 
        interactive_button_reply = data.get("interactiveButtonReply")
        
        # Apply the same logic as in app.py
        should_skip = (button_reply or list_reply or interactive_button_reply or message_type == "button")
        
        print(f"   🔍 Detected:")
        print(f"      Type: {message_type}")
        print(f"      Button Reply: {'Yes' if button_reply else 'No'}")
        print(f"      List Reply: {'Yes' if list_reply else 'No'}")
        print(f"      Interactive Button Reply: {'Yes' if interactive_button_reply else 'No'}")
        print(f"   🤖 Will skip processing: {should_skip}")
        
        if should_skip == case['should_skip']:
            print(f"   ✅ CORRECT detection!")
        else:
            print(f"   ❌ INCORRECT! Expected skip: {case['should_skip']}, Got: {should_skip}")
    
    print(f"\n📊 WATI template detection test completed!")

async def test_allowed_user_filtering():
    """Test that only allowed users get processed"""
    
    print(f"\n🧪 Testing Allowed User Filtering")
    print("=" * 60)
    
    # Define allowed numbers (same as in app.py)
    allowed_numbers = [
        "201142765209",
        "966138686475",
        "966505281144"
    ]
    
    test_cases = [
        {
            "phone": "201142765209",
            "normalized": "201142765209",
            "should_be_allowed": True,
            "description": "Test user 1"
        },
        {
            "phone": "966138686475",
            "normalized": "966138686475", 
            "should_be_allowed": True,
            "description": "Test user 2"
        },
        {
            "phone": "966505281144",
            "normalized": "966505281144",
            "should_be_allowed": True,
            "description": "Test user 3"
        },
        {
            "phone": "966501234567",
            "normalized": "966501234567",
            "should_be_allowed": False,
            "description": "Random user 1"
        },
        {
            "phone": "201234567890",
            "normalized": "201234567890",
            "should_be_allowed": False,
            "description": "Random user 2"
        },
        {
            "phone": "+966 50 123 4567",
            "normalized": "966501234567",
            "should_be_allowed": False,
            "description": "Random user 3 (with formatting)"
        }
    ]
    
    print("Testing allowed user filtering logic:")
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n{i}. Testing: {case['phone']}")
        print(f"   Description: {case['description']}")
        print(f"   Should be allowed: {case['should_be_allowed']}")
        
        # Apply the same normalization logic as in app.py
        normalized_phone = "".join(char for char in str(case['phone']) if char.isdigit())
        print(f"   Normalized: {normalized_phone}")
        
        # Check if allowed
        is_allowed = normalized_phone in allowed_numbers
        print(f"   🤖 Is allowed: {is_allowed}")
        
        if is_allowed == case['should_be_allowed']:
            print(f"   ✅ CORRECT filtering!")
        else:
            print(f"   ❌ INCORRECT! Expected: {case['should_be_allowed']}, Got: {is_allowed}")
    
    print(f"\n📊 Allowed user filtering test completed!")

if __name__ == "__main__":
    asyncio.run(test_enhanced_classification())
    asyncio.run(test_template_reply_detection())
    asyncio.run(test_unclear_message_detection())
    asyncio.run(test_wati_template_detection())
    asyncio.run(test_allowed_user_filtering()) 