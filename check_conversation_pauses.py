#!/usr/bin/env python3
"""
Utility script to check and monitor conversation pause status
"""

import sys
import os
from datetime import datetime, timedelta

# Add the current directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def check_active_pauses():
    """Check all currently active conversation pauses"""
    try:
        from database.db_utils import SessionLocal, DatabaseManager
        from database.db_models import ConversationPause
        
        db = SessionLocal()
        current_time = datetime.utcnow()
        
        # Get all active pauses
        active_pauses = db.query(ConversationPause).filter(
            ConversationPause.is_active == 1
        ).all()
        
        print(f"🔍 Conversation Pause Status Report ({current_time.strftime('%Y-%m-%d %H:%M:%S')} UTC)")
        print("=" * 80)
        
        if not active_pauses:
            print("✅ No active conversation pauses found")
            return
        
        expired_count = 0
        active_count = 0
        
        for pause in active_pauses:
            time_remaining = pause.expires_at - current_time
            is_expired = time_remaining.total_seconds() <= 0
            
            if is_expired:
                expired_count += 1
                status = "🔴 EXPIRED"
                time_display = f"Expired {abs(time_remaining.total_seconds()/3600):.1f} hours ago"
            else:
                active_count += 1
                status = "🟡 ACTIVE"
                hours_remaining = time_remaining.total_seconds() / 3600
                time_display = f"{hours_remaining:.1f} hours remaining"
            
            print(f"\n📞 Conversation: {pause.conversation_id}")
            print(f"   📱 Phone: {pause.phone_number}")
            print(f"   👤 Agent: {pause.agent_name} ({pause.agent_email})")
            print(f"   ⏰ Paused at: {pause.paused_at.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            print(f"   ⏳ Expires at: {pause.expires_at.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            print(f"   {status}: {time_display}")
        
        print(f"\n📊 Summary:")
        print(f"   🟡 Active pauses: {active_count}")
        print(f"   🔴 Expired pauses: {expired_count}")
        print(f"   📊 Total records: {len(active_pauses)}")
        
        # Clean up expired pauses if any
        if expired_count > 0:
            cleaned = DatabaseManager.cleanup_expired_pauses(db)
            print(f"   🧹 Cleaned up {cleaned} expired pauses")
        
        db.close()
        
    except Exception as e:
        print(f"❌ Error checking pauses: {e}")

def check_specific_conversation(conversation_id):
    """Check pause status for a specific conversation"""
    try:
        from database.db_utils import SessionLocal, DatabaseManager
        
        db = SessionLocal()
        
        print(f"🔍 Checking pause status for conversation: {conversation_id}")
        print("-" * 60)
        
        is_paused = DatabaseManager.is_conversation_paused(db, conversation_id)
        pause_info = DatabaseManager.get_conversation_pause_info(db, conversation_id)
        
        if is_paused and pause_info:
            print(f"🚫 CONVERSATION IS PAUSED")
            print(f"   👤 Agent: {pause_info['agent_name']} ({pause_info['agent_email']})")
            print(f"   ⏰ Paused at: {pause_info['paused_at']}")
            print(f"   ⏳ Expires at: {pause_info['expires_at']}")
            print(f"   🕒 Time remaining: {pause_info['hours_remaining']:.1f} hours")
        else:
            print(f"✅ CONVERSATION IS NOT PAUSED")
            print(f"   Bot will respond to messages normally")
        
        db.close()
        
    except Exception as e:
        print(f"❌ Error checking specific conversation: {e}")

def monitor_expiring_pauses(hours_ahead=1):
    """Monitor pauses that will expire in the next X hours"""
    try:
        from database.db_utils import SessionLocal
        from database.db_models import ConversationPause
        
        db = SessionLocal()
        current_time = datetime.utcnow()
        future_time = current_time + timedelta(hours=hours_ahead)
        
        # Get pauses that will expire in the next X hours
        expiring_pauses = db.query(ConversationPause).filter(
            ConversationPause.is_active == 1,
            ConversationPause.expires_at > current_time,
            ConversationPause.expires_at <= future_time
        ).all()
        
        print(f"⏰ Pauses expiring in the next {hours_ahead} hour(s):")
        print("-" * 60)
        
        if not expiring_pauses:
            print(f"✅ No pauses expiring in the next {hours_ahead} hour(s)")
        else:
            for pause in expiring_pauses:
                time_to_expiry = pause.expires_at - current_time
                minutes_remaining = time_to_expiry.total_seconds() / 60
                
                print(f"📞 Conversation: {pause.conversation_id}")
                print(f"   👤 Agent: {pause.agent_name} ({pause.agent_email})")
                print(f"   ⏳ Expires in: {minutes_remaining:.0f} minutes")
                print("")
        
        db.close()
        
    except Exception as e:
        print(f"❌ Error monitoring expiring pauses: {e}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Check conversation pause status")
    parser.add_argument("--conversation", "-c", help="Check specific conversation ID")
    parser.add_argument("--expiring", "-e", type=int, default=1, help="Check pauses expiring in X hours")
    parser.add_argument("--monitor", "-m", action="store_true", help="Monitor expiring pauses")
    
    args = parser.parse_args()
    
    try:
        if args.conversation:
            check_specific_conversation(args.conversation)
        elif args.monitor:
            monitor_expiring_pauses(args.expiring)
        else:
            check_active_pauses()
            
    except KeyboardInterrupt:
        print("\n👋 Monitoring stopped")
    except Exception as e:
        print(f"❌ Script error: {e}")
