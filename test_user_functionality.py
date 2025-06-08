#!/usr/bin/env python3
"""
Test script to verify test vs regular user functionality
"""

import asyncio
import sys
import os

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.db_models import MessageType
from agents.query_agent import query_agent
from utils.language_utils import language_handler

async def test_functionality():
    print("🧪 Testing User Functionality")
    print("=" * 60)
    
    # Test data
    test_cases = [
        {
            "message": "هل تغطون مدينة الرياض؟",
            "type": MessageType.INQUIRY,
            "language": "ar"
        },
        {
            "message": "Do you deliver to Riyadh?",
            "type": MessageType.INQUIRY, 
            "language": "en"
        },
        {
            "message": "لدي شكوى",
            "type": MessageType.COMPLAINT,
            "language": "ar"
        }
    ]
    
    allowed_numbers = ["201142765209", "966138686475", "966505281144"]
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n{i}. Testing: '{case['message']}'")
        print(f"   Type: {case['type']}")
        print(f"   Language: {case['language']}")
        
        # Test user response (should get real bot response)
        print(f"\n   🧪 TEST USER (201142765209):")
        try:
            if case['type'] in [MessageType.GREETING, MessageType.SUGGESTION]:
                test_response = "Standard response"
            else:
                # This is what test users should get - real bot response
                test_response = await query_agent.process_query(
                    user_message=case['message'],
                    conversation_history=[],
                    user_language=case['language']
                )
            print(f"   Response: {test_response[:100]}...")
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
        
        # Regular user response (should get team response)
        print(f"\n   👤 REGULAR USER (966501234567):")
        responses = language_handler.get_default_responses(case['language'])
        if case['type'] == MessageType.GREETING:
            regular_response = "Standard greeting"
        elif case['type'] == MessageType.SUGGESTION:
            regular_response = "Standard suggestion response"
        elif case['type'] == MessageType.COMPLAINT:
            regular_response = responses['COMPLAINT']
        elif case['type'] == MessageType.INQUIRY:
            regular_response = responses['INQUIRY_TEAM_REPLY']
        else:
            regular_response = responses['TEAM_WILL_REPLY']
        
        print(f"   Response: {regular_response}")
        print(f"   " + "-" * 50)

if __name__ == "__main__":
    asyncio.run(test_functionality()) 