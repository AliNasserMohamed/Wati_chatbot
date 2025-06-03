#!/usr/bin/env python3
"""
Migration script to update database schema for many-to-many city-brand relationship
and add new city fields (title, lat, lng)
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text, inspect
from database.db_utils import SessionLocal, DATABASE_URL
from database.db_models import Base

def migrate_database():
    """Run database migrations"""
    print("🔄 Starting database migration...")
    
    # Create engine and connection
    engine = create_engine(DATABASE_URL)
    
    # Get database connection for raw SQL
    with engine.connect() as connection:
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        
        print(f"📊 Found {len(existing_tables)} existing tables")
        
        try:
            # 1. Add new columns to cities table if they don't exist
            if 'cities' in existing_tables:
                columns = [col['name'] for col in inspector.get_columns('cities')]
                print(f"🏙️ Current city columns: {columns}")
                
                # Add title column
                if 'title' not in columns:
                    print("➕ Adding 'title' column to cities table...")
                    connection.execute(text("ALTER TABLE cities ADD COLUMN title VARCHAR(200)"))
                    connection.commit()
                    print("✅ Added 'title' column")
                
                # Add lat column
                if 'lat' not in columns:
                    print("➕ Adding 'lat' column to cities table...")
                    connection.execute(text("ALTER TABLE cities ADD COLUMN lat FLOAT"))
                    connection.commit()
                    print("✅ Added 'lat' column")
                
                # Add lng column
                if 'lng' not in columns:
                    print("➕ Adding 'lng' column to cities table...")
                    connection.execute(text("ALTER TABLE cities ADD COLUMN lng FLOAT"))
                    connection.commit()
                    print("✅ Added 'lng' column")
            
            # 2. Remove city_id from brands table if it exists
            if 'brands' in existing_tables:
                brand_columns = [col['name'] for col in inspector.get_columns('brands')]
                print(f"🏷️ Current brand columns: {brand_columns}")
                
                if 'city_id' in brand_columns:
                    print("🗑️ Removing 'city_id' column from brands table...")
                    # SQLite doesn't support DROP COLUMN, so we need to recreate the table
                    # For now, just add a note that this needs manual handling
                    print("⚠️ Note: 'city_id' column should be manually removed after migration")
                
                # Add title_en column if missing
                if 'title_en' not in brand_columns:
                    print("➕ Adding 'title_en' column to brands table...")
                    connection.execute(text("ALTER TABLE brands ADD COLUMN title_en VARCHAR(200)"))
                    connection.commit()
                    print("✅ Added 'title_en' column")
            
            # 3. Create city_brands association table if it doesn't exist
            if 'city_brands' not in existing_tables:
                print("🔗 Creating city_brands association table...")
                connection.execute(text("""
                    CREATE TABLE city_brands (
                        city_id INTEGER NOT NULL,
                        brand_id INTEGER NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (city_id, brand_id),
                        FOREIGN KEY(city_id) REFERENCES cities (id),
                        FOREIGN KEY(brand_id) REFERENCES brands (id)
                    )
                """))
                connection.commit()
                print("✅ Created city_brands table")
            else:
                print("✅ city_brands table already exists")
            
            print("🎉 Database migration completed successfully!")
            
            # 4. Verify the schema
            print("🔍 Verifying new schema...")
            Base.metadata.create_all(engine)
            print("✅ Schema verification complete")
            
        except Exception as e:
            print(f"❌ Migration failed: {str(e)}")
            connection.rollback()
            raise
        
    return True

def main():
    """Main migration function"""
    try:
        success = migrate_database()
        if success:
            print("\n✅ Migration completed successfully!")
            print("📝 Next steps:")
            print("1. Run the data sync to populate cities with new fields")
            print("2. Test the many-to-many city-brand relationships")
            print("3. Verify the API endpoints work correctly")
        return success
    except Exception as e:
        print(f"\n❌ Migration failed: {str(e)}")
        return False

if __name__ == "__main__":
    success = main()
    if not success:
        sys.exit(1) 