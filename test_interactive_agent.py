#!/usr/bin/env python3
"""
Test script to verify enhanced interactive query agent functionality
"""

import asyncio
import sys
import os

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agents.query_agent import query_agent
from database.db_utils import DatabaseManager, SessionLocal

async def test_interactive_agent():
    print("🤖 Testing Enhanced Interactive Query Agent")
    print("=" * 70)
    
    # Test cases to verify interactive behavior
    test_cases = [
        {
            "message": "ما هي العلامات التجارية المتاحة؟",
            "language": "ar",
            "description": "Vague question about brands (should ask for city)"
        },
        {
            "message": "What products do you have?",
            "language": "en", 
            "description": "Vague question about products (should ask for city/brand)"
        },
        {
            "message": "هل تغطون مدينة الرياض؟",
            "language": "ar",
            "description": "Specific city question (should provide detailed answer)"
        },
        {
            "message": "Do you deliver to Jeddah?",
            "language": "en",
            "description": "Specific city question (should provide detailed answer)"
        }
    ]
    
    # Sample conversation history to test formatting
    sample_history = [
        {"role": "user", "content": "user: مرحبا", "language": "ar"},
        {"role": "assistant", "content": "bot: مرحباً! كيف يمكنني مساعدتك اليوم؟", "language": "ar"},
        {"role": "user", "content": "user: أريد معرفة المدن المتاحة", "language": "ar"},
        {"role": "assistant", "content": "bot: بالطبع! إليك قائمة بالمدن المتاحة...", "language": "ar"}
    ]
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n{i}. Testing: '{case['message']}'")
        print(f"   Language: {case['language']}")
        print(f"   Expected: {case['description']}")
        print(f"   {'='*50}")
        
        try:
            # Test without conversation history
            print(f"   🔸 WITHOUT conversation history:")
            response = await query_agent.process_query(
                user_message=case['message'],
                conversation_history=[],
                user_language=case['language']
            )
            print(f"   Response: {response[:200]}...")
            
            # Test with conversation history
            print(f"\n   🔹 WITH conversation history:")
            response_with_history = await query_agent.process_query(
                user_message=case['message'],
                conversation_history=sample_history,
                user_language=case['language']
            )
            print(f"   Response: {response_with_history[:200]}...")
            
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
        
        print(f"   {'-'*50}")

async def test_conversation_formatting():
    print(f"\n🧪 Testing Conversation History Formatting")
    print("=" * 70)
    
    # Create a test database session
    db = SessionLocal()
    
    try:
        # Test formatted conversation method
        formatted = DatabaseManager.get_formatted_conversation_for_llm(db, user_id=1, limit=3)
        print(f"Formatted conversation for LLM:\n{formatted}")
        
        # Test enhanced history method
        history = DatabaseManager.get_user_message_history(db, user_id=1, limit=3)
        print(f"\nEnhanced history format:")
        for i, msg in enumerate(history, 1):
            print(f"{i}. {msg['content']} (Role: {msg['role']}, Lang: {msg.get('language', 'N/A')})")
            
    except Exception as e:
        print(f"❌ Error testing conversation formatting: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_interactive_agent())
    asyncio.run(test_conversation_formatting()) 