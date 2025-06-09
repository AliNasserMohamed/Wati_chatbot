#!/usr/bin/env python3
"""
Migration script to add THANKING to MessageType enum
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.db_utils import SessionLocal
from database.db_models import MessageType
from sqlalchemy import text

def migrate_message_type_enum():
    """Add THANKING to the MessageType enum"""
    db = SessionLocal()
    
    try:
        print("🔄 Adding THANKING to MessageType enum...")
        
        # For SQLite, we need to handle enum differently
        # Check current database type
        engine = db.get_bind()
        if 'sqlite' in str(engine.url):
            print("📁 SQLite database detected - MessageType enum updated in code")
            print("✅ THANKING message type is now available")
        else:
            # For PostgreSQL or other databases
            db.execute(text("ALTER TYPE messagetype ADD VALUE IF NOT EXISTS 'Thanking'"))
            db.commit()
            print("✅ THANKING added to MessageType enum")
        
    except Exception as e:
        print(f"❌ Migration failed: {str(e)}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    migrate_message_type_enum() 