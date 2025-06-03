#!/usr/bin/env python3
"""
Script to trigger initial data synchronization
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.db_utils import SessionLocal
from services.data_scraper import data_scraper

def main():
    """Run initial data sync"""
    print("🚀 Starting Initial Data Synchronization...")
    print("=" * 50)
    
    db = SessionLocal()
    try:
        # Run full sync
        print("📥 Fetching data from external APIs...")
        results = data_scraper.full_sync(db)
        
        print(f"\n✅ Synchronization completed successfully!")
        print(f"📊 Results:")
        for sync_type, count in results.items():
            print(f"   • {sync_type}: {count} records")
        
        print(f"\n🎉 Data is now available in your local database!")
        print(f"🌐 View the data at: http://localhost:8000/server/scrapped_data")
        
    except Exception as e:
        print(f"\n❌ Synchronization failed: {str(e)}")
        print(f"💡 Please check your internet connection and external API configuration.")
        return False
    finally:
        db.close()
    
    return True

if __name__ == "__main__":
    success = main()
    if success:
        print(f"\n🚀 Your Wati ChatBot is ready to handle queries about cities, brands, and products!")
    else:
        print(f"\n⚠️  Please fix the synchronization issues before using the chatbot.")
        sys.exit(1) 