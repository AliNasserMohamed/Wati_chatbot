#!/usr/bin/env python3
"""
Test script to verify context-aware classification and clean response formatting
"""

import asyncio
import sys
import os

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agents.message_classifier import message_classifier
from agents.query_agent import query_agent
from database.db_utils import DatabaseManager, SessionLocal
from database.db_models import UserMessage

async def test_context_aware_classification():
    print("🧠 Testing Context-Aware Message Classification")
    print("=" * 70)
    
    # Test scenarios that show the importance of context
    test_scenarios = [
        {
            "description": "User asks about brands, then clarifies with city",
            "conversation": [
                {"role": "user", "content": "user: ما هي العلامات التجارية المتاحة؟", "raw_content": "ما هي العلامات التجارية المتاحة؟"},
                {"role": "assistant", "content": "bot: أي مدينة تهتم بها؟", "raw_content": "أي مدينة تهتم بها؟"},
            ],
            "current_message": "الرياض",
            "expected_classification": "This should be classified as INQUIRY (city inquiry) not GREETING"
        },
        {
            "description": "User complains about service, then provides details",
            "conversation": [
                {"role": "user", "content": "user: لدي شكوى", "raw_content": "لدي شكوى"},
                {"role": "assistant", "content": "bot: تفضل، ما هي شكواك؟", "raw_content": "تفضل، ما هي شكواك؟"},
            ],
            "current_message": "التوصيل كان متأخر جداً",
            "expected_classification": "This should be classified as COMPLAINT (complaint details) not UNKNOWN"
        },
        {
            "description": "User asks for prices, then asks follow-up",
            "conversation": [
                {"role": "user", "content": "user: كم سعر مياه هاجر؟", "raw_content": "كم سعر مياه هاجر؟"},
                {"role": "assistant", "content": "bot: لدينا عدة أحجام متاحة", "raw_content": "لدينا عدة أحجام متاحة"},
            ],
            "current_message": "أريد الحجم الكبير",
            "expected_classification": "This should be classified as INQUIRY (product inquiry) not GREETING"
        }
    ]
    
    # Create a temporary database session
    db = SessionLocal()
    
    try:
        for i, scenario in enumerate(test_scenarios, 1):
            print(f"\n{i}. {scenario['description']}")
            print(f"   Expected: {scenario['expected_classification']}")
            print(f"   {'='*50}")
            
            # Create a temporary user message for testing
            temp_user_message = UserMessage(
                user_id=1,
                content=scenario['current_message']
            )
            
            try:
                # Test classification WITHOUT context
                print(f"   🔸 WITHOUT context:")
                classification_no_context, language_no_context = await message_classifier.classify_message(
                    scenario['current_message'], 
                    db, 
                    temp_user_message,
                    conversation_history=[]
                )
                print(f"   Classification: {classification_no_context}")
                
                # Test classification WITH context
                print(f"\n   🔹 WITH context:")
                classification_with_context, language_with_context = await message_classifier.classify_message(
                    scenario['current_message'], 
                    db, 
                    temp_user_message,
                    conversation_history=scenario['conversation']
                )
                print(f"   Classification: {classification_with_context}")
                
                # Show if context made a difference
                if classification_no_context != classification_with_context:
                    print(f"   ✅ Context changed classification: {classification_no_context} → {classification_with_context}")
                else:
                    print(f"   ⚠️  Context didn't change classification")
                    
            except Exception as e:
                print(f"   ❌ Error: {str(e)}")
            
            print(f"   {'-'*50}")
    
    finally:
        db.close()

async def test_response_cleanup():
    print(f"\n🧹 Testing Response Cleanup (Remove 'bot:' prefix)")
    print("=" * 70)
    
    # Test different response formats
    test_responses = [
        "bot: مرحباً! كيف يمكنني مساعدتك؟",
        "bot:نعم نحن نغطي الرياض",
        "لدينا عدة منتجات متوفرة",  # No prefix
        "bot: لدينا عدة منتجات متوفرة من مياه هاجر",
    ]
    
    print("Testing response cleanup logic:")
    for i, response in enumerate(test_responses, 1):
        print(f"\n{i}. Original: '{response}'")
        
        # Simulate cleanup logic
        cleaned_response = response
        if cleaned_response and cleaned_response.startswith("bot: "):
            cleaned_response = cleaned_response[5:]  # Remove "bot: " prefix
        elif cleaned_response and cleaned_response.startswith("bot:"):
            cleaned_response = cleaned_response[4:]  # Remove "bot:" prefix
            
        print(f"   Cleaned:  '{cleaned_response}'")
        
        if response != cleaned_response:
            print(f"   ✅ Cleanup applied")
        else:
            print(f"   ⚪ No cleanup needed")

async def test_query_agent_response_format():
    print(f"\n🤖 Testing Query Agent Response Format")
    print("=" * 70)
    
    try:
        # Test a simple query that might return "bot:" prefix
        response = await query_agent.process_query(
            user_message="هل تغطون الرياض؟",
            conversation_history=[],
            user_language="ar"
        )
        
        print(f"Query Agent Response: '{response[:200]}...'")
        
        if response.startswith("bot:"):
            print("⚠️  Query agent is returning responses with 'bot:' prefix - needs cleanup")
        else:
            print("✅ Query agent response format is clean")
            
    except Exception as e:
        print(f"❌ Error testing query agent: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_context_aware_classification())
    asyncio.run(test_response_cleanup())
    asyncio.run(test_query_agent_response_format()) 