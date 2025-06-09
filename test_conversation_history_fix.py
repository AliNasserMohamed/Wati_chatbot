#!/usr/bin/env python3
"""
Test script to verify conversation history printing is working correctly
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.db_utils import SessionLocal, DatabaseManager
from database.db_models import User, UserMessage, BotReply
from datetime import datetime, timedelta

def test_conversation_history():
    """Test the conversation history retrieval and printing"""
    
    print("🧪 Testing Conversation History Retrieval")
    print("=" * 60)
    
    db = SessionLocal()
    
    try:
        # Find or create a test user
        test_phone = "201142765209"  # Test user
        user = DatabaseManager.get_user_by_phone(db, test_phone)
        
        if not user:
            print(f"📱 Creating test user: {test_phone}")
            user = DatabaseManager.create_user(db, test_phone)
        else:
            print(f"👤 Found existing user: {user.phone_number} (ID: {user.id})")
        
        # Get current conversation history
        print(f"\n📚 Retrieving conversation history for user {user.id}...")
        conversation_history = DatabaseManager.get_user_message_history(db, user.id, limit=5)
        
        print(f"📊 Retrieved {len(conversation_history)} conversation entries")
        
        if conversation_history:
            print(f"\n💬 Complete Conversation History:")
            print(f"   {'='*60}")
            for i, msg in enumerate(conversation_history, 1):
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')
                timestamp = msg.get('timestamp', 'N/A')
                language = msg.get('language', 'N/A')
                print(f"   {i}. [{role.upper()}] ({timestamp}) [{language}]")
                print(f"      Content: {content}")
                print(f"      {'-'*50}")
        else:
            print(f"💬 No conversation history found")
        
        # Test formatted conversation
        print(f"\n🔤 Testing formatted conversation for LLM:")
        formatted_conversation = DatabaseManager.get_formatted_conversation_for_llm(db, user.id, limit=5)
        if formatted_conversation != "No previous conversation history.":
            print(f"📝 Formatted conversation:")
            print(f"   {formatted_conversation}")
            print(f"   {'='*60}")
        else:
            print(f"🔤 No formatted conversation history")
        
        # Check database structure
        print(f"\n🔍 Database structure check:")
        recent_messages = db.query(UserMessage).filter(
            UserMessage.user_id == user.id
        ).order_by(UserMessage.timestamp.desc()).limit(3).all()
        
        for msg in recent_messages:
            print(f"   📝 Message {msg.id}: '{msg.content[:50]}...' (Language: {msg.language})")
            print(f"      Replies: {len(msg.replies)}")
            for reply in msg.replies:
                print(f"         🤖 Reply: '{reply.content[:50]}...' (Language: {reply.language})")
        
        print(f"\n✅ Conversation history test completed!")
        
    except Exception as e:
        print(f"❌ Error testing conversation history: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        db.close()

if __name__ == "__main__":
    test_conversation_history() 