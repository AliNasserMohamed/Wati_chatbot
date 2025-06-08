#!/usr/bin/env python3
"""
Database migration script to add wati_message_id column to user_messages table
This prevents duplicate message processing from Wati webhooks
"""

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Create database directory if it doesn't exist
os.makedirs("database/data", exist_ok=True)

# Database connection
DATABASE_URL = "sqlite:///database/data/chatbot.sqlite"
engine = create_engine(DATABASE_URL)

def migrate_add_wati_message_id():
    """Add wati_message_id column to user_messages table"""
    try:
        with engine.connect() as connection:
            # Check if column already exists
            result = connection.execute(text("PRAGMA table_info(user_messages)"))
            columns = [row[1] for row in result.fetchall()]
            
            if 'wati_message_id' not in columns:
                print("Adding wati_message_id column to user_messages table...")
                connection.execute(text(
                    "ALTER TABLE user_messages ADD COLUMN wati_message_id VARCHAR(255)"
                ))
                connection.commit()
                print("✅ Successfully added wati_message_id column")
            else:
                print("ℹ️  wati_message_id column already exists")
                
    except Exception as e:
        print(f"❌ Error during migration: {str(e)}")
        raise

if __name__ == "__main__":
    print("🔄 Starting database migration...")
    migrate_add_wati_message_id()
    print("✅ Migration completed successfully!") 