#!/usr/bin/env python3
"""
Migration script to add language column to bot_replies table
"""

import sqlite3
import os
from pathlib import Path

def migrate_bot_replies():
    """Add language column to bot_replies table"""
    
    # Path to the database
    db_path = Path(__file__).parent / "data" / "chatbot.sqlite"
    
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return False
    
    try:
        # Connect to the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("🔄 Starting bot_replies migration...")
        
        # Check bot_replies table structure
        print("\n📋 Checking bot_replies table...")
        cursor.execute("PRAGMA table_info(bot_replies)")
        bot_columns = [column[1] for column in cursor.fetchall()]
        
        print(f"Current columns in bot_replies: {bot_columns}")
        
        # Add language column to bot_replies if it doesn't exist
        if 'language' not in bot_columns:
            print("Adding language column to bot_replies...")
            cursor.execute("""
                ALTER TABLE bot_replies 
                ADD COLUMN language TEXT DEFAULT 'ar'
            """)
            print("✅ Added language column to bot_replies")
        else:
            print("✅ language column already exists in bot_replies")
        
        # Commit changes
        conn.commit()
        
        # Verify changes
        print("\n🔍 Verifying changes...")
        cursor.execute("PRAGMA table_info(bot_replies)")
        new_bot_columns = [column[1] for column in cursor.fetchall()]
        print(f"Updated columns in bot_replies: {new_bot_columns}")
        
        conn.close()
        print("\n✅ Migration completed successfully!")
        print("🎉 bot_replies table now has language column!")
        return True
        
    except Exception as e:
        print(f"\n❌ Migration failed: {str(e)}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False

if __name__ == "__main__":
    migrate_bot_replies() 