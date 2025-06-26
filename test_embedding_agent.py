#!/usr/bin/env python3
"""
Test script for the new embedding agent
"""

import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import the agent
from agents.embedding_agent import embedding_agent

async def test_embedding_agent():
    """Test the embedding agent with various message types"""
    
    print("🧪 Testing Embedding Agent")
    print("=" * 50)
    
    # Test cases
    test_messages = [
        "السلام عليكم",  # Should find greeting
        "ما هو تطبيق ابار؟",  # Should find app info
        "أوكي",  # Should skip (no reply needed)
        "شكراً",  # Should skip or reply based on knowledge base  
        "كيف يعمل التطبيق؟",  # Similar to existing question
        "أريد طلب مياه",  # Should continue to classification
    ]
    
    for i, message in enumerate(test_messages, 1):
        print(f"\n{i}. Testing message: '{message}'")
        print("-" * 30)
        
        try:
            result = await embedding_agent.process_message(
                user_message=message,
                conversation_history=[],
                user_language='ar'
            )
            
            print(f"Action: {result['action']}")
            print(f"Confidence: {result['confidence']:.3f}")
            print(f"Matched Question: {result['matched_question']}")
            if result['response']:
                print(f"Response: {result['response'][:100]}...")
            else:
                print("Response: None")
                
        except Exception as e:
            print(f"❌ Error testing message '{message}': {str(e)}")
    
    print("\n" + "=" * 50)
    print("🎉 Embedding Agent Test Complete!")

if __name__ == "__main__":
    asyncio.run(test_embedding_agent()) 