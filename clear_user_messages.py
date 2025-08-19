#!/usr/bin/env python3
"""
Utility script to clear/delete all messages for a specific phone number
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from database.db_utils import SessionLocal
from database.db_models import User, UserMessage, BotReply
from typing import Optional

def clear_user_messages_by_phone(phone_number: str, delete_user_record: bool = False) -> dict:
    """
    Clear all messages for a specific phone number
    
    Args:
        phone_number: The phone number to clear messages for
        delete_user_record: Whether to also delete the user record (default: False)
    
    Returns:
        Dictionary with operation results
    """
    db = SessionLocal()
    results = {
        "phone_number": phone_number,
        "user_found": False,
        "bot_replies_deleted": 0,
        "user_messages_deleted": 0,
        "user_deleted": False,
        "success": False,
        "error": None
    }
    
    try:
        print(f"🔍 Searching for user with phone number: {phone_number}")
        
        # Find user by phone number
        user = db.query(User).filter(User.phone_number == phone_number).first()
        
        if not user:
            print(f"❌ No user found with phone number: {phone_number}")
            results["error"] = "User not found"
            return results
            
        results["user_found"] = True
        user_id = user.id
        
        print(f"✅ Found user: ID={user.id}, Name={user.name or 'No name'}")
        print(f"   Created: {user.created_at}")
        print(f"   Updated: {user.updated_at}")
        
        # Get all user messages
        user_messages = db.query(UserMessage).filter(UserMessage.user_id == user_id).all()
        print(f"📝 Found {len(user_messages)} user messages")
        
        # Delete bot replies first (to maintain referential integrity)
        total_bot_replies = 0
        for message in user_messages:
            bot_replies = db.query(BotReply).filter(BotReply.message_id == message.id).all()
            if bot_replies:
                print(f"   Deleting {len(bot_replies)} bot replies for message ID {message.id}")
                for reply in bot_replies:
                    db.delete(reply)
                total_bot_replies += len(bot_replies)
        
        db.commit()
        results["bot_replies_deleted"] = total_bot_replies
        print(f"✅ Deleted {total_bot_replies} bot replies")
        
        # Delete user messages
        messages_deleted = db.query(UserMessage).filter(UserMessage.user_id == user_id).delete()
        db.commit()
        results["user_messages_deleted"] = messages_deleted
        print(f"✅ Deleted {messages_deleted} user messages")
        
        # Optionally delete user record
        if delete_user_record:
            db.delete(user)
            db.commit()
            results["user_deleted"] = True
            print(f"✅ Deleted user record for {phone_number}")
        else:
            print(f"ℹ️  User record kept (user can start fresh conversation)")
            
        results["success"] = True
        print(f"🎉 Successfully cleared all messages for {phone_number}")
        
    except Exception as e:
        print(f"❌ Error clearing messages for {phone_number}: {str(e)}")
        results["error"] = str(e)
        db.rollback()
        
    finally:
        db.close()
        
    return results

def interactive_clear():
    """Interactive mode to clear messages"""
    print("🧹 User Message Cleaner")
    print("=" * 50)
    
    phone_number = input("Enter phone number to clear messages for: ").strip()
    if not phone_number:
        print("❌ Phone number is required")
        return
        
    print(f"\n📞 Phone number: {phone_number}")
    
    # Ask for confirmation
    delete_user = input("Delete user record too? (y/N): ").lower().strip() == 'y'
    
    print(f"\n⚠️  This will delete ALL messages for {phone_number}")
    if delete_user:
        print("⚠️  This will also DELETE the user record completely")
    else:
        print("ℹ️  User record will be kept (user can start fresh)")
        
    confirm = input("\nAre you sure? (yes/y to confirm): ").lower().strip()
    
    if confirm not in ['yes', 'y']:
        print("❌ Operation cancelled")
        return
        
    # Perform the operation
    print(f"\n🔄 Processing...")
    results = clear_user_messages_by_phone(phone_number, delete_user)
    
    # Display results
    print(f"\n📊 Results:")
    print(f"   Phone Number: {results['phone_number']}")
    print(f"   User Found: {results['user_found']}")
    print(f"   Bot Replies Deleted: {results['bot_replies_deleted']}")
    print(f"   User Messages Deleted: {results['user_messages_deleted']}")
    print(f"   User Record Deleted: {results['user_deleted']}")
    print(f"   Success: {results['success']}")
    
    if results['error']:
        print(f"   Error: {results['error']}")
        
    print("\n" + "=" * 50)
    return results

def clear_specific_number():
    """Clear messages for the specific number 201142765209"""
    phone_number = "201142765209"
    print(f"🎯 Clearing messages for specific number: {phone_number}")
    print("=" * 50)
    
    # Ask for confirmation
    delete_user = input("Delete user record too? (y/N): ").lower().strip() == 'y'
    
    print(f"\n⚠️  This will delete ALL messages for {phone_number}")
    if delete_user:
        print("⚠️  This will also DELETE the user record completely")
    else:
        print("ℹ️  User record will be kept (user can start fresh)")
        
    confirm = input(f"\nClear all messages for {phone_number}? (yes/y to confirm): ").lower().strip()
    
    if confirm not in ['yes', 'y']:
        print("❌ Operation cancelled")
        return
        
    # Perform the operation
    print(f"\n🔄 Clearing messages for {phone_number}...")
    results = clear_user_messages_by_phone(phone_number, delete_user)
    
    # Display results
    print(f"\n📊 Final Results:")
    print(f"   Phone Number: {results['phone_number']}")
    print(f"   User Found: {'✅' if results['user_found'] else '❌'}")
    print(f"   Bot Replies Deleted: {results['bot_replies_deleted']}")
    print(f"   User Messages Deleted: {results['user_messages_deleted']}")
    print(f"   User Record Deleted: {'✅' if results['user_deleted'] else '❌'}")
    print(f"   Success: {'✅' if results['success'] else '❌'}")
    
    if results['error']:
        print(f"   Error: ❌ {results['error']}")
    
    if results['success']:
        print(f"\n🎉 Successfully cleared all messages for {phone_number}!")
        print(f"   The user can now start a fresh conversation.")
    else:
        print(f"\n💥 Failed to clear messages. Check the error above.")
        
    return results

if __name__ == "__main__":
    print("🧹 Message Cleaner Utility")
    print("=" * 50)
    
    if len(sys.argv) > 1:
        # Command line mode
        phone_number = sys.argv[1]
        delete_user = len(sys.argv) > 2 and sys.argv[2].lower() in ['true', '1', 'yes', 'y']
        
        print(f"📞 Clearing messages for: {phone_number}")
        results = clear_user_messages_by_phone(phone_number, delete_user)
        
        if results['success']:
            print("✅ Operation completed successfully")
            sys.exit(0)
        else:
            print("❌ Operation failed")
            sys.exit(1)
    else:
        # Interactive mode
        print("1. Clear messages for 201142765209 (specific number)")
        print("2. Clear messages for any phone number (interactive)")
        print("3. Exit")
        
        choice = input("\nSelect option (1-3): ").strip()
        
        if choice == "1":
            clear_specific_number()
        elif choice == "2":
            interactive_clear()
        elif choice == "3":
            print("👋 Goodbye!")
        else:
            print("❌ Invalid choice")
