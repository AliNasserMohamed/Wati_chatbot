#!/usr/bin/env python3

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.scheduler import scheduler
from datetime import datetime

def check_scheduler_status():
    """Check the current status of the data sync scheduler"""
    
    print("🔍 SCHEDULER STATUS CHECK")
    print("=" * 50)
    
    # Get scheduler status
    status = scheduler.get_scheduler_status()
    
    print(f"📊 Scheduler Status:")
    print(f"   🔄 Is Running: {'✅ YES' if status['is_running'] else '❌ NO'}")
    print(f"   📅 Scheduled Jobs: {status['scheduled_jobs']}")
    print(f"   ⏰ Next Sync: {status['next_sync']}")
    
    # Show current time for reference
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"   🕐 Current Time: {current_time}")
    
    print("\n" + "=" * 50)
    
    if status['is_running']:
        print("✅ SCHEDULER IS ACTIVE")
        print("🕐 Data will be automatically updated every day at 2:00 AM")
        
        if status['scheduled_jobs'] > 0:
            print(f"📅 Next automatic sync: {status['next_sync']}")
        else:
            print("⚠️ No scheduled jobs found - this might be an issue")
    else:
        print("❌ SCHEDULER IS NOT RUNNING")
        print("🚨 Data will NOT be automatically updated!")
        print("\n💡 To fix this:")
        print("   1. Restart the application (app.py)")
        print("   2. Or manually start the scheduler via API:")
        print("      POST /data/sync/start")
    
    print("\n🔧 Available Scheduler Management:")
    print("   • Manual sync: POST /data/sync")
    print("   • Check status: GET /data/sync/status") 
    print("   • Start scheduler: POST /data/sync/start")
    print("   • Stop scheduler: POST /data/sync/stop")

def manual_sync_test():
    """Test manual sync to ensure the data scraper is working"""
    
    print("\n" + "=" * 50)
    print("🧪 MANUAL SYNC TEST")
    print("=" * 50)
    
    try:
        print("🚀 Starting manual data sync test...")
        result = scheduler.run_manual_sync()
        
        if result['status'] == 'success':
            print("✅ Manual sync completed successfully!")
            if 'results' in result:
                results = result['results']
                print(f"📊 Sync Results:")
                print(f"   🏙️ Cities: {results.get('cities', 'N/A')}")
                print(f"   🏷️ Brands: {results.get('brands', 'N/A')}")
                print(f"   📦 Products: {results.get('products', 'N/A')}")
        else:
            print(f"❌ Manual sync failed: {result.get('message', 'Unknown error')}")
            
    except Exception as e:
        print(f"❌ Error during manual sync test: {str(e)}")

if __name__ == "__main__":
    # Check scheduler status
    check_scheduler_status()
    
    # Ask user if they want to run a manual sync test
    print("\n" + "=" * 50)
    user_input = input("🤔 Do you want to run a manual sync test? (y/N): ").lower().strip()
    
    if user_input in ['y', 'yes']:
        manual_sync_test()
    else:
        print("ℹ️ Manual sync test skipped.")
    
    print("\n🎉 Status check completed!") 