#!/usr/bin/env python3
"""
Debug Database Path Issue
Identifies which database files exist and ensures consistent path usage
"""

import os
import sys
from pathlib import Path
from database.db_utils import DATABASE_URL, SessionLocal
from database.db_models import District

def check_database_files():
    """Check all possible database file locations"""
    print("🔍 Checking database file locations:")
    
    # Get current working directory
    cwd = Path.cwd()
    print(f"📂 Current working directory: {cwd}")
    
    # Possible database paths
    possible_paths = [
        cwd / "database/data/chatbot.sqlite",
        cwd / "data/chatbot.sqlite", 
        Path("/root/chatbot/wati_repo/Wati_chatbot/database/data/chatbot.sqlite"),
        Path("/root/chatbot/wati_repo/Wati_chatbot/data/chatbot.sqlite")
    ]
    
    print(f"\n📋 Checking possible database locations:")
    for path in possible_paths:
        if path.exists():
            size = path.stat().st_size
            print(f"   ✅ {path} - Size: {size:,} bytes")
        else:
            print(f"   ❌ {path} - Not found")
    
    return possible_paths

def test_database_connection():
    """Test the current database connection"""
    print(f"\n🔗 Testing current database connection:")
    print(f"   📁 DATABASE_URL: {DATABASE_URL}")
    
    try:
        session = SessionLocal()
        try:
            district_count = session.query(District).count()
            print(f"   📊 Districts in current database: {district_count}")
            
            if district_count > 0:
                # Show some sample districts
                sample_districts = session.query(District).limit(5).all()
                print(f"   📋 Sample districts:")
                for d in sample_districts:
                    print(f"      🏘️ {d.name} -> 🏙️ {d.city_name}")
            
        finally:
            session.close()
            
    except Exception as e:
        print(f"   ❌ Database connection error: {str(e)}")

def get_absolute_database_path():
    """Get the absolute path of the database being used"""
    # Parse the DATABASE_URL to get the actual file path
    if DATABASE_URL.startswith("sqlite:///"):
        relative_path = DATABASE_URL[10:]  # Remove "sqlite:///"
        absolute_path = Path(relative_path).resolve()
        print(f"\n📍 Absolute database path: {absolute_path}")
        return absolute_path
    return None

def find_populated_database():
    """Find which database file has districts data"""
    print(f"\n🔍 Searching for populated database:")
    
    possible_paths = [
        Path("database/data/chatbot.sqlite"),
        Path("data/chatbot.sqlite"),
        Path("/root/chatbot/wati_repo/Wati_chatbot/database/data/chatbot.sqlite"),
    ]
    
    for path in possible_paths:
        if path.exists():
            try:
                # Create a temporary connection to this specific file
                import sqlite3
                conn = sqlite3.connect(str(path))
                cursor = conn.cursor()
                
                # Check if districts table exists and has data
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='districts'")
                table_exists = cursor.fetchone() is not None
                
                district_count = 0
                if table_exists:
                    cursor.execute("SELECT COUNT(*) FROM districts")
                    district_count = cursor.fetchone()[0]
                
                conn.close()
                
                print(f"   📁 {path}")
                print(f"      📊 Districts: {district_count}")
                
                if district_count > 0:
                    print(f"      ✅ POPULATED DATABASE FOUND!")
                    return path
                    
            except Exception as e:
                print(f"   📁 {path}")
                print(f"      ❌ Error: {str(e)}")
    
    return None

def propose_fix():
    """Propose how to fix the database path issue"""
    print(f"\n🛠️ PROPOSED FIX:")
    
    populated_db = find_populated_database()
    current_db = get_absolute_database_path()
    
    if populated_db:
        print(f"   1. Populated database found at: {populated_db}")
        print(f"   2. Current database path: {current_db}")
        
        if str(populated_db) != str(current_db):
            print(f"   3. ⚠️  MISMATCH DETECTED!")
            print(f"   4. 🔧 Solution: Copy populated database to current location")
            print(f"      Command: cp {populated_db} {current_db}")
        else:
            print(f"   3. ✅ Paths match - investigating other issues")
    else:
        print(f"   ❌ No populated database found")

def main():
    """Main debug function"""
    print("=" * 60)
    print("🔍 DATABASE PATH DEBUG TOOL")
    print("=" * 60)
    
    check_database_files()
    test_database_connection()
    get_absolute_database_path()
    propose_fix()
    
    print("\n" + "=" * 60)
    print("🎯 DEBUG COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main() 