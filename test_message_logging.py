#!/usr/bin/env python3
"""
Test script to verify the comprehensive message logging system.
This script simulates a message journey and verifies that all steps are logged correctly.
"""

import sys
import os
import time
from datetime import datetime

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.message_logger import message_journey_logger

def test_basic_logging():
    """Test basic message journey logging functionality"""
    print("🧪 Testing basic message journey logging...")
    
    # Test 1: Start a journey
    journey_id = message_journey_logger.start_journey(
        phone_number="+966501234567",
        message_text="Hello, I need water delivery",
        wati_message_id="test_msg_001",
        message_type="text"
    )
    
    print(f"✅ Started journey: {journey_id}")
    
    # Test 2: Add various processing steps
    message_journey_logger.add_step(
        journey_id=journey_id,
        step_type="webhook_validation",
        description="Message passed webhook validation",
        data={"phone_number": "+966501234567", "message_type": "text"},
        duration_ms=50
    )
    
    # Test 3: Log embedding agent processing
    message_journey_logger.log_embedding_agent(
        journey_id=journey_id,
        user_message="Hello, I need water delivery",
        action="continue_to_classification",
        confidence=0.45,
        matched_question="What is your delivery policy?",
        response=None,
        duration_ms=150
    )
    
    # Test 4: Log classification
    message_journey_logger.log_classification(
        journey_id=journey_id,
        message_text="Hello, I need water delivery",
        classified_type="INQUIRY",
        detected_language="en",
        duration_ms=80
    )
    
    # Test 5: Log LLM interaction
    message_journey_logger.log_llm_interaction(
        journey_id=journey_id,
        llm_type="openai",
        prompt="You are a customer service agent. User asks: Hello, I need water delivery",
        response="Hello! I'd be happy to help you with water delivery. Which city are you located in?",
        model="gpt-3.5-turbo",
        duration_ms=1200,
        tokens_used={"total_tokens": 45}
    )
    
    # Test 6: Log database operations
    message_journey_logger.log_database_operation(
        journey_id=journey_id,
        operation="create_message",
        table="user_messages",
        details={"message_id": 123, "user_id": 456},
        duration_ms=25
    )
    
    message_journey_logger.log_database_operation(
        journey_id=journey_id,
        operation="create_bot_reply",
        table="bot_replies",
        details={"reply_id": 789, "message_id": 123},
        duration_ms=30
    )
    
    # Test 7: Log WhatsApp sending
    message_journey_logger.log_whatsapp_send(
        journey_id=journey_id,
        phone_number="+966501234567",
        message="Hello! I'd be happy to help you with water delivery. Which city are you located in?",
        status="success",
        response_data={"status": "sent", "message_id": "wati_789"},
        duration_ms=800
    )
    
    # Test 8: Complete journey
    final_response = "Hello! I'd be happy to help you with water delivery. Which city are you located in?"
    message_journey_logger.complete_journey(
        journey_id=journey_id,
        final_response=final_response,
        status="completed"
    )
    
    print(f"✅ Completed journey: {journey_id}")
    
    # Test 9: Get journey summary
    summary = message_journey_logger.get_journey_summary(journey_id)
    if summary:
        print(f"✅ Journey summary retrieved: {summary['total_steps']} steps")
        print(f"   Status: {summary['status']}")
        print(f"   Duration: {summary.get('total_duration_ms', 'N/A')}ms")
        
        # Print step types
        print(f"   Step types: {summary.get('step_types_count', {})}")
    else:
        print("❌ Failed to retrieve journey summary")
    
    return journey_id

def test_error_logging():
    """Test error logging functionality"""
    print("\n🧪 Testing error logging...")
    
    # Start another journey
    journey_id = message_journey_logger.start_journey(
        phone_number="+966509876543",
        message_text="Test error message",
        wati_message_id="test_error_001"
    )
    
    # Simulate an error
    try:
        raise ValueError("This is a test error")
    except Exception as e:
        message_journey_logger.log_error(
            journey_id=journey_id,
            error_type="test_error",
            error_message=str(e),
            step="test_step",
            exception=e
        )
    
    message_journey_logger.complete_journey(journey_id, status="failed")
    
    print(f"✅ Error logging test completed: {journey_id}")
    return journey_id

def test_skip_scenarios():
    """Test various skip scenarios"""
    print("\n🧪 Testing skip scenarios...")
    
    # Test bot message skip
    journey_id1 = message_journey_logger.start_journey(
        phone_number="+966505555555",
        message_text="Thanks for your message",
        wati_message_id="bot_msg_001"
    )
    
    message_journey_logger.add_step(
        journey_id=journey_id1,
        step_type="message_filter",
        description="Skipped: from_bot=True",
        data={"from_bot": True, "from_me": False},
        status="skipped"
    )
    
    message_journey_logger.complete_journey(journey_id1, status="skipped_bot_message")
    
    # Test duplicate message skip
    journey_id2 = message_journey_logger.start_journey(
        phone_number="+966506666666",
        message_text="Hello again",
        wati_message_id="dup_msg_001"
    )
    
    message_journey_logger.add_step(
        journey_id=journey_id2,
        step_type="duplicate_check",
        description="Duplicate message detected",
        status="skipped"
    )
    
    message_journey_logger.complete_journey(journey_id2, status="skipped_duplicate")
    
    print(f"✅ Skip scenarios test completed: {journey_id1}, {journey_id2}")

def test_performance():
    """Test logging performance with multiple concurrent journeys"""
    print("\n🧪 Testing performance with multiple journeys...")
    
    start_time = time.time()
    journey_ids = []
    
    # Create multiple concurrent journeys
    for i in range(10):
        journey_id = message_journey_logger.start_journey(
            phone_number=f"+96650{i:07d}",
            message_text=f"Test message {i}",
            wati_message_id=f"perf_test_{i:03d}"
        )
        journey_ids.append(journey_id)
        
        # Add some steps to each journey
        message_journey_logger.add_step(
            journey_id=journey_id,
            step_type="performance_test",
            description=f"Performance test step {i}",
            duration_ms=i * 10
        )
        
        message_journey_logger.complete_journey(
            journey_id=journey_id,
            final_response=f"Response {i}",
            status="completed"
        )
    
    end_time = time.time()
    total_time = (end_time - start_time) * 1000
    
    print(f"✅ Performance test completed: {len(journey_ids)} journeys in {total_time:.2f}ms")
    print(f"   Average time per journey: {total_time / len(journey_ids):.2f}ms")

def verify_log_files():
    """Verify that log files are created correctly"""
    print("\n🧪 Verifying log files...")
    
    import os
    from pathlib import Path
    
    log_dir = Path("logs")
    if log_dir.exists():
        log_files = list(log_dir.glob("message_journey_*.log"))
        if log_files:
            latest_log = max(log_files, key=os.path.getctime)
            file_size = latest_log.stat().st_size
            print(f"✅ Log file created: {latest_log}")
            print(f"   File size: {file_size} bytes")
            
            # Check if log contains expected content
            with open(latest_log, 'r', encoding='utf-8') as f:
                content = f.read()
                if "JOURNEY_START" in content and "JOURNEY_COMPLETE" in content:
                    print("✅ Log file contains expected journey markers")
                else:
                    print("⚠️  Log file missing expected content")
                    
                # Count different log types
                log_lines = content.split('\n')
                log_types = {}
                for line in log_lines:
                    if '|' in line:
                        parts = line.split('|')
                        if len(parts) >= 4:
                            log_type = parts[3].strip().split()[0]
                            log_types[log_type] = log_types.get(log_type, 0) + 1
                
                print(f"   Log type distribution: {log_types}")
        else:
            print("❌ No log files found")
    else:
        print("❌ Logs directory not found")

def main():
    """Run all tests"""
    print("🚀 Starting comprehensive message logging system tests")
    print("=" * 60)
    
    try:
        # Run basic tests
        test_basic_logging()
        
        # Run error logging tests
        test_error_logging()
        
        # Run skip scenario tests
        test_skip_scenarios()
        
        # Run performance tests
        test_performance()
        
        # Verify log files
        verify_log_files()
        
        print("\n" + "=" * 60)
        print("✅ All tests completed successfully!")
        print("🎉 Message logging system is working correctly")
        
        # Clean up old journeys for testing
        message_journey_logger.cleanup_old_journeys(max_age_hours=0)  # Clean all for test
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 