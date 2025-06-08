#!/usr/bin/env python3
"""
Test script to verify that ALL messages now go through the LLM
No more fast replies or fallback mechanisms should exist
"""

import asyncio
import sys
import os

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agents.query_agent import query_agent

async def test_no_fast_replies():
    print("🧪 Testing That ALL Messages Go Through LLM")
    print("=" * 60)
    
    test_messages = [
        {
            "message": "السلام عليكم",
            "language": "ar",
            "description": "Greeting (previously had fast reply)"
        },
        {
            "message": "Hello",
            "language": "en", 
            "description": "English greeting (previously had fast reply)"
        },
        {
            "message": "شكراً لكم",
            "language": "ar",
            "description": "Thank you message (suggestion type)"
        },
        {
            "message": "ما هي العلامات التجارية المتاحة؟",
            "language": "ar",
            "description": "Vague brands question (should ask directly: 'أي مدينة؟')"
        },
        {
            "message": "What products do you have?",
            "language": "en",
            "description": "Vague products question (should ask directly: 'Which city?')"
        }
    ]
    
    for i, test in enumerate(test_messages, 1):
        print(f"\n{i}. Testing: '{test['message']}'")
        print(f"   Language: {test['language']}")
        print(f"   Context: {test['description']}")
        print(f"   {'='*40}")
        
        try:
            # This should ALL go through LLM now
            response = await query_agent.process_query(
                user_message=test['message'],
                conversation_history=[],
                user_language=test['language']
            )
            
            print(f"   🤖 LLM Response: {response[:100]}...")
            
            # Check if it's a direct question as expected
            if test['message'] in ["ما هي العلامات التجارية المتاحة؟", "What products do you have?"]:
                if any(word in response.lower() for word in ["أي مدينة", "which city", "مدينة"]):
                    print(f"   ✅ Direct question style detected!")
                else:
                    print(f"   ⚠️  Response style: {response[:50]}...")
            
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
        
        print(f"   {'-'*40}")

async def test_direct_questioning():
    print(f"\n🎯 Testing Direct Questioning Style")
    print("=" * 60)
    
    # Test conversation flow to see direct questioning
    conversation = []
    
    # First message - vague question
    print(f"\n1. User: 'ما هي العلامات التجارية؟'")
    response1 = await query_agent.process_query(
        user_message="ما هي العلامات التجارية؟",
        conversation_history=conversation,
        user_language="ar"
    )
    print(f"   Bot: {response1}")
    
    # Add to conversation history
    conversation.extend([
        {"role": "user", "content": "ما هي العلامات التجارية؟"},
        {"role": "assistant", "content": response1}
    ])
    
    # Second message - answer with city
    print(f"\n2. User: 'الرياض'")
    response2 = await query_agent.process_query(
        user_message="الرياض",
        conversation_history=conversation,
        user_language="ar"
    )
    print(f"   Bot: {response2[:200]}...")

if __name__ == "__main__":
    print("🔧 Testing Enhanced Query Agent - No Fast Replies")
    print("All messages should now go through the LLM")
    print("=" * 60)
    
    asyncio.run(test_no_fast_replies())
    asyncio.run(test_direct_questioning())
    
    print(f"\n✅ Test Complete!")
    print("If you see LLM responses for all messages above, the fast reply removal was successful!") 