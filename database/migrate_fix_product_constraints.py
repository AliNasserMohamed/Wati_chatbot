#!/usr/bin/env python3
"""
Migration script to fix product constraints to allow same product 
in multiple brands/cities with different prices
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text, inspect
from database.db_utils import SessionLocal, DATABASE_URL
import sqlite3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_fix_product_constraints():
    """Fix product constraints to allow same product in multiple brands"""
    logger.info("🔄 Starting product constraints migration...")
    
    # Connect directly to SQLite database
    db_path = "database/data/chatbot.sqlite"
    
    try:
        # Create backup first
        logger.info("📋 Creating backup of products table...")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create backup table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products_backup AS 
            SELECT * FROM products
        """)
        
        # Get current data
        cursor.execute("SELECT COUNT(*) FROM products")
        count_before = cursor.fetchone()[0]
        logger.info(f"📊 Found {count_before} products in original table")
        
        # Drop the original table
        logger.info("🗑️ Dropping original products table...")
        cursor.execute("DROP TABLE products")
        
        # Create new products table without unique constraint on external_id
        logger.info("🏗️ Creating new products table with correct constraints...")
        cursor.execute("""
            CREATE TABLE products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id INTEGER NOT NULL,
                brand_id INTEGER NOT NULL,
                title VARCHAR(200) NOT NULL,
                title_en VARCHAR(200),
                packing VARCHAR(200),
                market_price FLOAT,
                contract_price FLOAT,
                barcode VARCHAR(50),
                image_url TEXT,
                meta_keywords_ar TEXT,
                meta_keywords_en TEXT,
                meta_description_ar TEXT,
                meta_description_en TEXT,
                description_rich_text_ar TEXT,
                description_rich_text_en TEXT,
                created_at DATETIME,
                updated_at DATETIME,
                FOREIGN KEY(brand_id) REFERENCES brands (id),
                UNIQUE (external_id, brand_id)
            )
        """)
        
        # Restore data without duplicates (keep one per external_id, brand_id combination)
        logger.info("📥 Restoring data with deduplication...")
        cursor.execute("""
            INSERT INTO products (
                external_id, brand_id, title, title_en, packing, 
                market_price, contract_price, barcode, image_url,
                meta_keywords_ar, meta_keywords_en, meta_description_ar, meta_description_en,
                description_rich_text_ar, description_rich_text_en, created_at, updated_at
            )
            SELECT DISTINCT
                external_id, brand_id, title, title_en, packing,
                market_price, contract_price, barcode, image_url,
                meta_keywords_ar, meta_keywords_en, meta_description_ar, meta_description_en,
                description_rich_text_ar, description_rich_text_en, created_at, updated_at
            FROM products_backup
            GROUP BY external_id, brand_id
        """)
        
        # Get final count
        cursor.execute("SELECT COUNT(*) FROM products")
        count_after = cursor.fetchone()[0]
        logger.info(f"📊 Restored {count_after} unique products (removed {count_before - count_after} duplicates)")
        
        # Commit changes
        conn.commit()
        
        # Drop backup table
        logger.info("🧹 Cleaning up backup table...")
        cursor.execute("DROP TABLE products_backup")
        conn.commit()
        
        conn.close()
        
        logger.info("🎉 Product constraints migration completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {str(e)}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        raise

def main():
    """Main migration function"""
    try:
        success = migrate_fix_product_constraints()
        if success:
            print("\n✅ Migration completed successfully!")
            print("📝 Summary of changes:")
            print("1. ❌ Removed UNIQUE constraint on external_id")
            print("2. ✅ Added composite UNIQUE constraint on (external_id, brand_id)")
            print("3. ✅ Changed id to AUTOINCREMENT instead of using external_id")
            print("4. 🧹 Deduplicated existing products")
            print("\n🔄 Now you can run the scraper without constraint violations!")
        return success
    except Exception as e:
        print(f"\n❌ Migration failed: {str(e)}")
        return False

if __name__ == "__main__":
    success = main()
    if not success:
        sys.exit(1) 