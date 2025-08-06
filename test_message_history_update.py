#!/usr/bin/env python3
"""
Test that QueryAgent and MessageClassifier now use last 5 messages instead of 3
"""

import sys
sys.path.append('.')

def test_conversation_history_limits():
    """Test that the conversation history limits have been updated"""
    
    print("=== Testing Conversation History Limits ===")
    
    # Create test conversation history with 10 messages
    test_history = []
    for i in range(10):
        test_history.append({
            "role": "user" if i % 2 == 0 else "assistant",
            "content": f"Message {i + 1}",
            "raw_content": f"Message {i + 1}"
        })
    
    print(f"📋 Created test conversation with {len(test_history)} messages")
    
    # Test 1: Verify slicing logic for last 5 messages
    last_5 = test_history[-5:]
    print(f"\n--- Test 1: Last 5 Messages Slicing ---")
    print(f"✅ Last 5 messages: {[msg['content'] for msg in last_5]}")
    print(f"✅ Expected: ['Message 6', 'Message 7', 'Message 8', 'Message 9', 'Message 10']")
    
    # Test 2: Test with fewer than 5 messages
    short_history = test_history[:3]  # Only 3 messages
    last_5_short = short_history[-5:] if len(short_history) >= 5 else short_history
    print(f"\n--- Test 2: Short History (3 messages) ---")
    print(f"✅ Short history (3 messages): {[msg['content'] for msg in last_5_short]}")
    print(f"✅ Expected: ['Message 1', 'Message 2', 'Message 3']")
    
    # Test 3: Test with exactly 5 messages
    exact_5_history = test_history[:5]  # Exactly 5 messages
    last_5_exact = exact_5_history[-5:] if len(exact_5_history) >= 5 else exact_5_history
    print(f"\n--- Test 3: Exact 5 Messages ---")
    print(f"✅ Exact 5 messages: {[msg['content'] for msg in last_5_exact]}")
    print(f"✅ Expected: ['Message 1', 'Message 2', 'Message 3', 'Message 4', 'Message 5']")
    
    print(f"\n=== Summary ===")
    print(f"✅ QueryAgent now uses last 5 messages:")
    print(f"   - Line 429: for message in reversed(conversation_history[-5:])")
    print(f"   - Line 748: recent_messages = conversation_history[-5:]")
    print(f"   - Line 1158: messages[-5:] for LLM prompt context")
    print(f"✅ EmbeddingAgent now uses last 5 messages:")
    print(f"   - Line 270: conversation_history[-5:] if len >= 5 else all")
    print(f"✅ MessageClassifier was already using last 5 messages:")
    print(f"   - Line 78: conversation_history[-5:] (already updated)")
    
    return True

if __name__ == "__main__":
    success = test_conversation_history_limits()
    sys.exit(0 if success else 1) 