#!/usr/bin/env python3
"""
Emergency script to fix corrupted SQLite database
This script will attempt to recover data and recreate the database
"""

import sqlite3
import os
import shutil
from datetime import datetime
from pathlib import Path

def diagnose_database_corruption():
    """Check the state of database files and attempt diagnosis"""
    print("🔍 Diagnosing Database Corruption")
    print("="*50)
    
    db_paths = [
        "database/data/chatbot.sqlite",
        "database/data/chatbot.sqlite3", 
        "database/data/chatbot.db",
        "vectorstore/data/chroma.sqlite3"
    ]
    
    for db_path in db_paths:
        if os.path.exists(db_path):
            print(f"\n📁 Found database: {db_path}")
            file_size = os.path.getsize(db_path)
            print(f"   Size: {file_size:,} bytes")
            
            # Try to check integrity
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("PRAGMA integrity_check;")
                result = cursor.fetchone()
                if result and result[0] == 'ok':
                    print(f"   Status: ✅ HEALTHY")
                else:
                    print(f"   Status: ❌ CORRUPTED - {result}")
                conn.close()
            except Exception as e:
                print(f"   Status: ❌ SEVERELY CORRUPTED - {str(e)}")
        else:
            print(f"\n📁 Missing: {db_path}")

def backup_corrupted_database():
    """Backup the corrupted database before attempting fixes"""
    print("\n💾 Creating Backup of Corrupted Database")
    print("="*50)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    db_paths = [
        "database/data/chatbot.sqlite",
        "database/data/chatbot.sqlite3", 
        "database/data/chatbot.db"
    ]
    
    for db_path in db_paths:
        if os.path.exists(db_path):
            backup_path = f"{db_path}.corrupted_backup_{timestamp}"
            shutil.copy2(db_path, backup_path)
            print(f"✅ Backed up: {db_path} → {backup_path}")

def recreate_database():
    """Recreate the database from scratch"""
    print("\n🏗️ Recreating Database from Scratch")
    print("="*50)
    
    # Remove corrupted database files
    db_paths = [
        "database/data/chatbot.sqlite",
        "database/data/chatbot.sqlite3", 
        "database/data/chatbot.db"
    ]
    
    for db_path in db_paths:
        if os.path.exists(db_path):
            os.remove(db_path)
            print(f"   🗑️ Removed corrupted: {db_path}")
    
    print("\n📋 Next Steps:")
    print("1. Run the application - it will auto-create fresh database")
    print("2. Run data scraping to repopulate cities/brands/products")
    print("3. User conversation history will be lost (backed up above)")
    
def main():
    print("🚨 SQLite Database Corruption Recovery Tool")
    print("="*60)
    print("⚠️  IMPORTANT: Stop the application before running this script!")
    print("="*60)
    
    input("Press Enter to continue after stopping the application...")
    
    # Step 1: Diagnose
    diagnose_database_corruption()
    
    # Step 2: Backup
    backup_corrupted_database()
    
    # Step 3: Recreate
    confirm = input("\n⚠️ Recreate database from scratch? This will delete current data. (y/N): ")
    if confirm.lower() == 'y':
        recreate_database()
        print("\n✅ Database recreation complete!")
        print("🔄 You can now restart your application")
    else:
        print("\n⏸️ Database recreation cancelled")
        print("🔧 Manual intervention required")

if __name__ == "__main__":
    main()
