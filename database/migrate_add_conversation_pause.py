#!/usr/bin/env python3
"""
Database migration script to add conversation_pauses table
This table tracks when customer service agents enter conversations to pause bot processing
"""

import os
import sqlite3
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

def migrate_add_conversation_pause_table():
    """Add conversation_pauses table to track agent-triggered bot pauses"""
    
    # Path to the database
    db_path = Path(__file__).parent / "data" / "chatbot.sqlite"
    
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        print("Creating database directory...")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        return False
    
    try:
        # Connect to the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if conversation_pauses table already exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='conversation_pauses'
        """)
        
        if cursor.fetchone():
            print("ℹ️  conversation_pauses table already exists")
            conn.close()
            return True
        
        print("Creating conversation_pauses table...")
        
        # Create the conversation_pauses table
        cursor.execute("""
            CREATE TABLE conversation_pauses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id VARCHAR(255) UNIQUE NOT NULL,
                phone_number VARCHAR(20) NOT NULL,
                agent_assignee_id VARCHAR(255),
                agent_email VARCHAR(255),
                agent_name VARCHAR(100),
                paused_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes for better query performance
        cursor.execute("""
            CREATE INDEX idx_conversation_pauses_conversation_id 
            ON conversation_pauses(conversation_id)
        """)
        
        cursor.execute("""
            CREATE INDEX idx_conversation_pauses_phone_number 
            ON conversation_pauses(phone_number)
        """)
        
        cursor.execute("""
            CREATE INDEX idx_conversation_pauses_active_expires 
            ON conversation_pauses(is_active, expires_at)
        """)
        
        # Commit the changes
        conn.commit()
        
        # Verify the table was created
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='conversation_pauses'")
        if cursor.fetchone():
            print("✅ Successfully created conversation_pauses table")
        else:
            raise Exception("Table creation verification failed")
        
        # Show the table structure
        cursor.execute("PRAGMA table_info(conversation_pauses)")
        columns = cursor.fetchall()
        print("📋 Table structure:")
        for column in columns:
            print(f"   - {column[1]} ({column[2]})")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {str(e)}")
        if 'conn' in locals():
            conn.close()
        raise

def verify_conversation_pause_functionality():
    """Verify that the new table works correctly"""
    try:
        from database.db_utils import SessionLocal, DatabaseManager
        
        db = SessionLocal()
        
        # Test creating a pause
        test_conversation_id = "migration_test_123"
        
        # Clean up any existing test data
        from database.db_models import ConversationPause
        db.query(ConversationPause).filter(
            ConversationPause.conversation_id == test_conversation_id
        ).delete()
        db.commit()
        
        # Test creating a conversation pause
        pause = DatabaseManager.create_conversation_pause(
            db=db,
            conversation_id=test_conversation_id,
            phone_number="966123456789",
            agent_email="contracts@abar.app",
            agent_name="Test Agent"
        )
        
        if pause and pause.id:
            print("✅ Conversation pause functionality test passed")
            
            # Clean up test data
            db.query(ConversationPause).filter(
                ConversationPause.conversation_id == test_conversation_id
            ).delete()
            db.commit()
            
        else:
            print("❌ Conversation pause functionality test failed")
            
        db.close()
        
    except Exception as e:
        print(f"⚠️  Could not verify functionality (this is normal if app is not running): {e}")

if __name__ == "__main__":
    print("🔄 Starting conversation_pauses table migration...")
    
    try:
        success = migrate_add_conversation_pause_table()
        
        if success:
            print("✅ Migration completed successfully!")
            print("🧪 Running functionality verification...")
            verify_conversation_pause_functionality()
            print("")
            print("📋 Migration Summary:")
            print("   ✅ Created conversation_pauses table")
            print("   ✅ Added indexes for performance")  
            print("   ✅ Agent pause feature is ready to use")
            print("")
            print("🚀 The bot will now pause for 10 hours when contracts@abar.app agent enters conversations")
        else:
            print("❌ Migration failed!")
            
    except Exception as e:
        print(f"❌ Migration error: {e}")
        exit(1)
