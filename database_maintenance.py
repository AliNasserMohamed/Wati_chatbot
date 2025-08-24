#!/usr/bin/env python3
"""
Database maintenance and backup utility
Prevents corruption and provides regular backups
"""

import sqlite3
import os
import shutil
import schedule
import time
from datetime import datetime, timedelta
from pathlib import Path

class DatabaseMaintenance:
    def __init__(self):
        self.db_paths = [
            "database/data/chatbot.sqlite",
            "database/data/chatbot.sqlite3",
            "vectorstore/data/chroma.sqlite3"
        ]
        self.backup_dir = "database/backups"
        os.makedirs(self.backup_dir, exist_ok=True)
    
    def check_database_health(self):
        """Check database integrity"""
        print(f"🔍 {datetime.now()}: Checking database health...")
        
        for db_path in self.db_paths:
            if not os.path.exists(db_path):
                continue
                
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                # Integrity check
                cursor.execute("PRAGMA integrity_check;")
                result = cursor.fetchone()
                
                if result and result[0] == 'ok':
                    print(f"   ✅ {db_path}: HEALTHY")
                else:
                    print(f"   ⚠️ {db_path}: Issues found - {result}")
                    self.alert_corruption(db_path, result)
                
                # Optimize database
                cursor.execute("PRAGMA optimize;")
                
                conn.close()
                
            except Exception as e:
                print(f"   ❌ {db_path}: CORRUPTED - {str(e)}")
                self.alert_corruption(db_path, str(e))
    
    def create_backup(self):
        """Create database backup"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        print(f"💾 {datetime.now()}: Creating database backup...")
        
        for db_path in self.db_paths:
            if not os.path.exists(db_path):
                continue
                
            try:
                # Create backup filename
                db_name = Path(db_path).stem
                backup_filename = f"{db_name}_{timestamp}.sqlite"
                backup_path = os.path.join(self.backup_dir, backup_filename)
                
                # Use SQLite backup API for safe backup
                source_conn = sqlite3.connect(db_path)
                backup_conn = sqlite3.connect(backup_path)
                source_conn.backup(backup_conn)
                source_conn.close()
                backup_conn.close()
                
                print(f"   ✅ Backed up: {db_path} → {backup_path}")
                
            except Exception as e:
                print(f"   ❌ Backup failed for {db_path}: {str(e)}")
    
    def cleanup_old_backups(self, keep_days=7):
        """Remove backups older than specified days"""
        cutoff_date = datetime.now() - timedelta(days=keep_days)
        
        for backup_file in os.listdir(self.backup_dir):
            if backup_file.endswith('.sqlite'):
                backup_path = os.path.join(self.backup_dir, backup_file)
                file_time = datetime.fromtimestamp(os.path.getctime(backup_path))
                
                if file_time < cutoff_date:
                    os.remove(backup_path)
                    print(f"🗑️ Removed old backup: {backup_file}")
    
    def alert_corruption(self, db_path, error):
        """Alert about database corruption"""
        alert_msg = f"""
🚨 DATABASE CORRUPTION DETECTED! 🚨
Database: {db_path}
Error: {error}
Time: {datetime.now()}
Action Required: Check database immediately!
"""
        print(alert_msg)
        
        # Write to alert file
        with open("database_alerts.log", "a") as f:
            f.write(alert_msg + "\n")
    
    def run_maintenance(self):
        """Run complete maintenance routine"""
        print("🔧 Starting database maintenance...")
        self.check_database_health()
        self.create_backup()
        self.cleanup_old_backups()
        print("✅ Database maintenance completed\n")

def start_maintenance_scheduler():
    """Start the maintenance scheduler"""
    maintenance = DatabaseMaintenance()
    
    # Schedule maintenance tasks
    schedule.every(6).hours.do(maintenance.check_database_health)  # Health check every 6 hours
    schedule.every().day.at("02:00").do(maintenance.create_backup)  # Daily backup at 2 AM
    schedule.every().week.do(maintenance.cleanup_old_backups)  # Weekly cleanup
    
    print("📅 Database maintenance scheduler started")
    print("   - Health checks: Every 6 hours")
    print("   - Backups: Daily at 2:00 AM")
    print("   - Cleanup: Weekly")
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "schedule":
        start_maintenance_scheduler()
    else:
        # Run one-time maintenance
        maintenance = DatabaseMaintenance()
        maintenance.run_maintenance()
