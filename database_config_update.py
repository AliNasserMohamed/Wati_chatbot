#!/usr/bin/env python3
"""
Update database configuration to prevent corruption
Adds proper SQLite settings for production use
"""

import sqlite3
import os

def configure_sqlite_for_production(db_path):
    """Configure SQLite with production-safe settings"""
    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path, timeout=30.0)
        cursor = conn.cursor()
        
        print(f"🔧 Configuring {db_path} for production safety...")
        
        # Enable WAL mode (Write-Ahead Logging) for better concurrency
        cursor.execute("PRAGMA journal_mode=WAL;")
        result = cursor.fetchone()
        print(f"   ✅ WAL mode: {result[0]}")
        
        # Set synchronous mode to FULL for maximum data safety
        cursor.execute("PRAGMA synchronous=FULL;")
        result = cursor.fetchone()
        print(f"   ✅ Synchronous mode: {result[0]}")
        
        # Set reasonable timeout
        cursor.execute("PRAGMA busy_timeout=30000;")  # 30 seconds
        
        # Enable foreign key constraints
        cursor.execute("PRAGMA foreign_keys=ON;")
        result = cursor.fetchone()
        print(f"   ✅ Foreign keys: {result[0]}")
        
        # Set cache size (negative means KB)
        cursor.execute("PRAGMA cache_size=-64000;")  # 64MB cache
        result = cursor.fetchone()
        print(f"   ✅ Cache size: {abs(result[0])} KB")
        
        # Enable automatic index optimization
        cursor.execute("PRAGMA optimize;")
        print(f"   ✅ Database optimized")
        
        conn.close()
        print(f"   ✅ Configuration complete for {db_path}")
        return True
        
    except Exception as e:
        print(f"   ❌ Configuration failed for {db_path}: {str(e)}")
        return False

def update_db_utils_config():
    """Update db_utils.py to include production-safe SQLite settings"""
    db_utils_path = "database/db_utils.py"
    
    if not os.path.exists(db_utils_path):
        print(f"❌ db_utils.py not found at {db_utils_path}")
        return
    
    print("🔧 Updating db_utils.py with production-safe SQLite settings...")
    
    # Read current content
    with open(db_utils_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Add SQLite configuration function
    sqlite_config_code = '''

def configure_sqlite_connection(connection, connection_record):
    """Configure SQLite connection with production-safe settings"""
    if 'sqlite' in str(connection.engine.url):
        with connection.begin():
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL") 
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=30000")
            connection.execute("PRAGMA cache_size=-64000")
'''
    
    # Check if the configuration is already added
    if "configure_sqlite_connection" not in content:
        # Add the configuration function
        content += sqlite_config_code
        
        # Update engine creation to use the configuration
        if "create_engine" in content and "@event.listens_for" not in content:
            event_listener_code = '''
# Configure SQLite for production safety
from sqlalchemy import event
event.listens_for(engine, "connect", configure_sqlite_connection)
'''
            # Insert after engine creation
            content = content.replace(
                "engine = create_engine(",
                event_listener_code + "\nengine = create_engine("
            )
        
        # Write updated content
        with open(db_utils_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("   ✅ db_utils.py updated with SQLite production settings")
    else:
        print("   ℹ️ SQLite configuration already exists in db_utils.py")

def main():
    print("🔧 SQLite Production Configuration Tool")
    print("="*50)
    
    # Configure existing databases
    db_paths = [
        "database/data/chatbot.sqlite",
        "database/data/chatbot.sqlite3",
        "vectorstore/data/chroma.sqlite3"
    ]
    
    for db_path in db_paths:
        if os.path.exists(db_path):
            configure_sqlite_for_production(db_path)
        else:
            print(f"⏭️ Skipping non-existent: {db_path}")
    
    # Update db_utils.py
    update_db_utils_config()
    
    print("\n✅ SQLite production configuration complete!")
    print("🔄 Restart your application to apply new connection settings")

if __name__ == "__main__":
    main()
