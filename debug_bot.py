#!/usr/bin/env python3
"""
Debug script to test bot behavior and identify constant reply issues
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.db_utils import get_db, DatabaseManager
from database.db_models import UserMessage, BotReply
from sqlalchemy.orm import sessionmaker

def check_recent_messages(phone_number="201142765209"):
    """Check recent messages and replies for a specific phone number"""
    print(f"🔍 Checking recent activity for phone number: {phone_number}")
    
    # Get database session
    from database.db_utils import SessionLocal
    db = SessionLocal()
    
    try:
        # Get user
        user = DatabaseManager.get_user_by_phone(db, phone_number)
        if not user:
            print(f"❌ No user found for phone number {phone_number}")
            return
        
        print(f"👤 Found user ID: {user.id}")
        
        # Get recent messages (last 10)
        recent_messages = db.query(UserMessage).filter(
            UserMessage.user_id == user.id
        ).order_by(
            UserMessage.timestamp.desc()
        ).limit(10).all()
        
        print(f"📱 Found {len(recent_messages)} recent messages:")
        
        for i, msg in enumerate(recent_messages, 1):
            print(f"\n{i}. Message ID: {msg.id}")
            print(f"   Content: {msg.content[:50]}...")
            print(f"   Timestamp: {msg.timestamp}")
            print(f"   Wati Message ID: {msg.wati_message_id}")
            print(f"   Language: {msg.language}")
            
            # Check replies for this message
            replies = db.query(BotReply).filter_by(message_id=msg.id).all()
            print(f"   Bot Replies: {len(replies)}")
            
            for j, reply in enumerate(replies, 1):
                print(f"     Reply {j}: {reply.content[:50]}...")
                print(f"     Reply Timestamp: {reply.timestamp}")
                print(f"     Reply Language: {reply.language}")
        
        # Check for potential duplicates
        print(f"\n🔍 Checking for duplicate Wati message IDs:")
        wati_ids = [msg.wati_message_id for msg in recent_messages if msg.wati_message_id]
        duplicates = [id for id in wati_ids if wati_ids.count(id) > 1]
        
        if duplicates:
            print(f"⚠️  Found duplicate Wati message IDs: {duplicates}")
        else:
            print(f"✅ No duplicate Wati message IDs found")
            
        # Check for messages with multiple replies
        print(f"\n🔍 Checking for messages with multiple replies:")
        multi_reply_count = 0
        for msg in recent_messages:
            reply_count = db.query(BotReply).filter_by(message_id=msg.id).count()
            if reply_count > 1:
                multi_reply_count += 1
                print(f"⚠️  Message {msg.id} has {reply_count} replies")
        
        if multi_reply_count == 0:
            print(f"✅ No messages with multiple replies found")
        
    except Exception as e:
        print(f"❌ Error checking messages: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

def simulate_duplicate_check(wati_message_id="test_message_123"):
    """Test the duplicate message checking function"""
    print(f"\n🧪 Testing duplicate message checking for ID: {wati_message_id}")
    
    from database.db_utils import SessionLocal
    db = SessionLocal()
    
    try:
        # First check
        is_duplicate_1 = DatabaseManager.check_message_already_processed(db, wati_message_id)
        print(f"First check - Is duplicate: {is_duplicate_1}")
        
        # Create a test message with this ID
        if not is_duplicate_1:
            user = DatabaseManager.get_user_by_phone(db, "201142765209")
            if user:
                test_message = DatabaseManager.create_message(
                    db, user.id, "Test message", wati_message_id
                )
                print(f"Created test message with ID: {test_message.id}")
        
        # Second check
        is_duplicate_2 = DatabaseManager.check_message_already_processed(db, wati_message_id)
        print(f"Second check - Is duplicate: {is_duplicate_2}")
        
        db.commit()
        
    except Exception as e:
        print(f"❌ Error in duplicate check test: {str(e)}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("🔧 Bot Debug Tool")
    print("=" * 50)
    
    # Check recent messages
    check_recent_messages()
    
    # Test duplicate checking
    simulate_duplicate_check()
    
    print("\n" + "=" * 50)
    print("�� Debug complete") 