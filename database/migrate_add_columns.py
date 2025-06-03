#!/usr/bin/env python3
"""
Migration script to add missing columns to user_messages and bot_replies tables
"""

import sqlite3
import os
from pathlib import Path
import enum

class MessageType(enum.Enum):
    SERVICE_REQUEST = "Service Request"
    INQUIRY = "Inquiry" 
    COMPLAINT = "Complaint"
    SUGGESTION = "Suggestion or Note"
    GREETING = "Greeting or Random Messages"

def migrate_database():
    """Add missing columns to user_messages and bot_replies tables"""
    
    # Path to the database
    db_path = Path(__file__).parent / "data" / "chatbot.sqlite"
    
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return False
    
    try:
        # Connect to the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if message_type column exists
        cursor.execute("PRAGMA table_info(user_messages)")
        columns = [column[1] for column in cursor.fetchall()]
        
        print(f"Current columns in user_messages: {columns}")
        
        # Add message_type column if it doesn't exist
        if 'message_type' not in columns:
            print("Adding message_type column...")
            cursor.execute("""
                ALTER TABLE user_messages 
                ADD COLUMN message_type TEXT NULL
            """)
            print("✓ Added message_type column")
        else:
            print("message_type column already exists")
        
        # Add language column if it doesn't exist
        if 'language' not in columns:
            print("Adding language column...")
            cursor.execute("""
                ALTER TABLE user_messages 
                ADD COLUMN language TEXT DEFAULT 'ar'
            """)
            print("✓ Added language column")
        else:
            print("language column already exists")
        
        # Commit changes
        conn.commit()
        
        # Verify the changes
        cursor.execute("PRAGMA table_info(user_messages)")
        new_columns = [column[1] for column in cursor.fetchall()]
        print(f"Updated columns in user_messages: {new_columns}")
        
        conn.close()
        print("✓ Migration completed successfully!")
        return True
        
    except Exception as e:
        print(f"Migration failed: {str(e)}")
        return False

if __name__ == "__main__":
    migrate_database() 