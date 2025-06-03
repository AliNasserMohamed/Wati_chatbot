#!/usr/bin/env python3
"""
Complete Clean Slate Data Sync Script
This will DELETE ALL existing data and sync fresh from external API with ID consistency
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.db_utils import SessionLocal
from services.data_scraper import data_scraper

def main():
    """Run complete clean slate sync"""
    print("🚨 COMPLETE CLEAN SLATE DATA SYNC")
    print("=" * 60)
    print("⚠️  WARNING: This will DELETE ALL existing data!")
    print("⚠️  All cities, brands, and products will be removed!")
    print("⚠️  Fresh data will be synced with external IDs as primary keys!")
    print("=" * 60)
    
    # Ask for confirmation
    while True:
        confirm = input("\n🤔 Are you sure you want to proceed? (type 'YES' to confirm, 'no' to cancel): ").strip()
        if confirm.upper() == 'YES':
            break
        elif confirm.lower() == 'no':
            print("❌ Sync cancelled by user")
            return False
        else:
            print("⚠️ Please type 'YES' to confirm or 'no' to cancel")
    
    print("\n🚀 Starting clean slate sync...")
    
    db = SessionLocal()
    try:
        # Run complete clean slate sync
        results = data_scraper.full_clean_slate_sync(db)
        
        print("\n" + "🎉" * 20)
        print("✅ CLEAN SLATE SYNC COMPLETED SUCCESSFULLY!")
        print("🎉" * 20)
        
        print(f"\n📊 FINAL RESULTS:")
        print(f"   🏙️ Cities synced: {results.get('cities', 0)}")
        print(f"   🏷️ Brands synced: {results.get('brands', 0)}")
        print(f"   📦 Products synced: {results.get('products', 0)}")
        
        print(f"\n✅ All data now uses external IDs as primary keys")
        print(f"✅ Database is consistent with dev.gulfwells.sa")
        print(f"✅ LLM functions will work with internal SQLite database only")
        
        return True
        
    except Exception as e:
        print(f"\n❌ SYNC FAILED: {str(e)}")
        return False
    finally:
        db.close()

if __name__ == "__main__":
    success = main()
    if not success:
        sys.exit(1)
    else:
        print(f"\n🏁 Script completed successfully!")
        print(f"🔍 You can now test the system with unified IDs") 