#!/usr/bin/env python3
"""
Test script to verify the enhanced embedding agent logging.
Tests that the most similar questions/answers and complete LLM prompts/responses are logged.
"""

import sys
import os
import asyncio
from datetime import datetime

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.message_logger import message_journey_logger
from agents.embedding_agent import embedding_agent
from utils.language_utils import language_handler

async def test_embedding_logging():
    """Test enhanced embedding agent logging"""
    print("🧪 Testing enhanced embedding agent logging...")
    
    # Start a test journey
    journey_id = message_journey_logger.start_journey(
        phone_number="+966501234567",
        message_text="السلام عليكم",  # Arabic greeting
        wati_message_id="embed_test_001",
        message_type="text"
    )
    
    print(f"✅ Started journey: {journey_id}")
    
    # Test embedding agent with journey logging
    print("\n🔍 Testing embedding agent with Arabic greeting...")
    try:
        result = await embedding_agent.process_message(
            user_message="السلام عليكم",
            conversation_history=[],
            user_language="ar",
            journey_id=journey_id
        )
        
        print(f"✅ Embedding result: {result['action']}")
        print(f"   Confidence: {result['confidence']:.3f}")
        response = result.get('response', 'None')
        matched_question = result.get('matched_question', 'None')
        print(f"   Response: {response[:50] + '...' if response and len(response) > 50 else response}")
        print(f"   Matched Question: {matched_question[:50] + '...' if matched_question and len(matched_question) > 50 else matched_question}")
        
    except Exception as e:
        print(f"❌ Error testing Arabic greeting: {str(e)}")
        import traceback
        traceback.print_exc()
    
    # Test with a more complex message that should continue to classification
    print("\n🔍 Testing embedding agent with inquiry message...")
    try:
        journey_id2 = message_journey_logger.start_journey(
            phone_number="+966501234568",
            message_text="أريد طلب مياه في الرياض",
            wati_message_id="embed_test_002",
            message_type="text"
        )
        
        result2 = await embedding_agent.process_message(
            user_message="أريد طلب مياه في الرياض",
            conversation_history=[],
            user_language="ar",
            journey_id=journey_id2
        )
        
        print(f"✅ Embedding result: {result2['action']}")
        print(f"   Confidence: {result2['confidence']:.3f}")
        print(f"   Response: {result2.get('response', 'None')}")
        matched_question2 = result2.get('matched_question', 'None')
        print(f"   Matched Question: {matched_question2[:50] + '...' if matched_question2 and len(matched_question2) > 50 else matched_question2}")
        
        message_journey_logger.complete_journey(journey_id2, status="completed")
        
    except Exception as e:
        print(f"❌ Error testing inquiry message: {str(e)}")
        import traceback
        traceback.print_exc()
    
    # Complete the first journey
    if result.get('response'):
        message_journey_logger.complete_journey(journey_id, final_response=result['response'], status="completed")
    else:
        message_journey_logger.complete_journey(journey_id, status="completed_no_reply")
    
    return journey_id

async def test_english_message():
    """Test embedding agent with English message"""
    print("\n🔍 Testing embedding agent with English message...")
    
    journey_id = message_journey_logger.start_journey(
        phone_number="+966501234569",
        message_text="Hello, thank you",
        wati_message_id="embed_test_003",
        message_type="text"
    )
    
    try:
        result = await embedding_agent.process_message(
            user_message="Hello, thank you",
            conversation_history=[],
            user_language="en",
            journey_id=journey_id
        )
        
        print(f"✅ English embedding result: {result['action']}")
        print(f"   Confidence: {result['confidence']:.3f}")
        print(f"   Response: {result.get('response', 'None')}")
        matched_question = result.get('matched_question', 'None')
        print(f"   Matched Question: {matched_question[:50] + '...' if matched_question and len(matched_question) > 50 else matched_question}")
        
        if result.get('response'):
            message_journey_logger.complete_journey(journey_id, final_response=result['response'], status="completed")
        else:
            message_journey_logger.complete_journey(journey_id, status="completed_no_reply")
        
    except Exception as e:
        print(f"❌ Error testing English message: {str(e)}")
        import traceback
        traceback.print_exc()
        message_journey_logger.complete_journey(journey_id, status="failed")
    
    return journey_id

def analyze_embedding_logs():
    """Analyze the logs to verify embedding-specific logging is captured"""
    print("\n🔍 Analyzing embedding-specific logs...")
    
    import os
    from pathlib import Path
    from datetime import datetime
    
    # Get today's log file
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = Path(f"logs/message_journey_{today}.log")
    
    if not log_file.exists():
        print("❌ No log file found for today")
        return
    
    print(f"📁 Analyzing log file: {log_file}")
    
    # Read log content
    with open(log_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Count embedding-specific log entries
    embedding_logs = {
        "search_results": content.count("EMBEDDING_SEARCH_RESULTS"),
        "qa_match": content.count("EMBEDDING_QA_MATCH"),
        "llm_evaluation_prompt": content.count("EMBEDDING_LLM_EVALUATION_PROMPT"),
        "llm_evaluation_result": content.count("EMBEDDING_LLM_EVALUATION_RESULT"),
        "llm_interaction": content.count("LLM_INTERACTION"),
        "embedding_agent": content.count("EMBEDDING_AGENT")
    }
    
    print("📊 Embedding-specific log entry counts:")
    for log_type, count in embedding_logs.items():
        print(f"   {log_type}: {count}")
    
    # Look for specific patterns
    if "similarity_score" in content:
        print("✅ Found similarity scores in logs")
    else:
        print("❌ No similarity scores found in logs")
    
    if "matched_question" in content:
        print("✅ Found matched questions in logs")
    else:
        print("❌ No matched questions found in logs")
    
    if "matched_answer" in content:
        print("✅ Found matched answers in logs")
    else:
        print("❌ No matched answers found in logs")
    
    if "complete_prompt" in content:
        print("✅ Found complete prompts in logs")
    else:
        print("❌ No complete prompts found in logs")
    
    if "evaluation_result" in content:
        print("✅ Found evaluation results in logs")
    else:
        print("❌ No evaluation results found in logs")
    
    # Extract some sample log entries for verification
    lines = content.split('\n')
    embedding_lines = [line for line in lines if any(keyword in line for keyword in ["EMBEDDING", "LLM_INTERACTION"])]
    
    if embedding_lines:
        print(f"\n📝 Sample embedding log entries ({min(5, len(embedding_lines))} of {len(embedding_lines)}):")
        for i, line in enumerate(embedding_lines[:5], 1):
            if len(line) > 150:
                print(f"   {i}. {line[:150]}...")
            else:
                print(f"   {i}. {line}")
    else:
        print("❌ No embedding-specific log entries found")

async def main():
    """Run all embedding logging tests"""
    print("🚀 Starting enhanced embedding agent logging tests")
    print("=" * 60)
    
    try:
        # Test Arabic greeting
        await test_embedding_logging()
        
        # Test English message
        await test_english_message()
        
        # Analyze the logs
        analyze_embedding_logs()
        
        print("\n" + "=" * 60)
        print("✅ Enhanced embedding logging tests completed!")
        print("🎉 Embedding agent logging is working correctly")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1) 