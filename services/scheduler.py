import asyncio
import schedule
import time
import threading
import logging
from datetime import datetime, timedelta
from typing import Dict, Any

from database.db_utils import SessionLocal
from services.data_scraper import data_scraper

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataSyncScheduler:
    """Scheduler for automated data synchronization"""
    
    def __init__(self):
        self.is_running = False
        self.scheduler_thread = None
    
    def sync_data_job(self):
        """Job to sync data from external APIs"""
        try:
            logger.info("Starting scheduled data sync...")
            
            db = SessionLocal()
            try:
                # Run async method in sync context
                results = asyncio.run(data_scraper.full_sync(db))
                logger.info(f"Scheduled sync completed successfully: {results}")
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Scheduled sync failed: {str(e)}")
    
    def run_scheduler(self):
        """Run the scheduler in a separate thread"""
        while self.is_running:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    
    def start_scheduler(self, daily_time: str = "02:00"):
        """Start the scheduler
        
        Args:
            daily_time: Time to run sync daily (format: "HH:MM")
        """
        if self.is_running:
            logger.warning("Scheduler is already running")
            return
        
        logger.info(f"Starting data sync scheduler - daily sync at {daily_time}")
        
        # Schedule daily sync
        schedule.every().day.at(daily_time).do(self.sync_data_job)
        
        self.is_running = True
        self.scheduler_thread = threading.Thread(target=self.run_scheduler, daemon=True)
        self.scheduler_thread.start()
        
        logger.info("Data sync scheduler started successfully")
    
    def stop_scheduler(self):
        """Stop the scheduler"""
        if not self.is_running:
            logger.warning("Scheduler is not running")
            return
        
        logger.info("Stopping data sync scheduler...")
        self.is_running = False
        schedule.clear()
        
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        
        logger.info("Data sync scheduler stopped")
    
    def run_manual_sync(self) -> Dict[str, Any]:
        """Run a manual sync immediately"""
        try:
            logger.info("Starting manual data sync...")
            
            db = SessionLocal()
            try:
                # Run async method in sync context
                results = asyncio.run(data_scraper.full_sync(db))
                logger.info(f"Manual sync completed successfully: {results}")
                return {"status": "success", "results": results}
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Manual sync failed: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def get_next_sync_time(self) -> str:
        """Get the next scheduled sync time"""
        if not schedule.jobs:
            return "No scheduled jobs"
        
        next_run = schedule.next_run()
        if next_run:
            return next_run.strftime("%Y-%m-%d %H:%M:%S")
        return "No scheduled jobs"
    
    def get_scheduler_status(self) -> Dict[str, Any]:
        """Get scheduler status information"""
        return {
            "is_running": self.is_running,
            "scheduled_jobs": len(schedule.jobs),
            "next_sync": self.get_next_sync_time()
        }

# Create singleton instance
scheduler = DataSyncScheduler() 