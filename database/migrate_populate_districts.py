import pandas as pd
import os
import sys
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Add parent directory to Python path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_utils import DATABASE_URL
from database.db_models import Base, District, DataSyncLog

def populate_districts_from_excel():
    """
    Read districts from Suadi_Districts.xlsx and populate the districts table
    """
    
    # Get the Excel file path (relative to project root)
    excel_file = "../Suadi_Districts.xlsx"
    if not os.path.exists(excel_file):
        # Try from current directory
        excel_file = "Suadi_Districts.xlsx"
        if not os.path.exists(excel_file):
            print(f"❌ Excel file not found in expected locations")
            return False
    
    try:
        # Create database engine
        engine = create_engine(DATABASE_URL, echo=False)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        print(f"🗃️  Connected to database successfully")
        
        # Create the districts table if it doesn't exist
        print(f"📋 Creating districts table if not exists...")
        Base.metadata.create_all(engine, tables=[District.__table__])
        
        # Read Excel file
        print(f"📁 Reading districts from {excel_file}...")
        df = pd.read_excel(excel_file)
        
        print(f"📊 Found {len(df)} district-city mappings")
        print(f"   - Columns: {list(df.columns)}")
        print(f"   - Unique cities: {df['المدينة'].nunique()}")
        print(f"   - Unique districts: {df['حي'].nunique()}")
        
        # Check if data already exists
        existing_count = session.query(District).count()
        if existing_count > 0:
            print(f"⚠️  Found {existing_count} existing districts in database")
            response = input("Do you want to clear existing data and reload? (y/N): ")
            if response.lower() == 'y':
                print(f"🗑️  Clearing existing district data...")
                session.query(District).delete()
                session.commit()
                print(f"✅ Existing data cleared")
            else:
                print(f"ℹ️  Keeping existing data, will skip duplicates")
        
        # Start logging the sync
        sync_log = DataSyncLog(
            sync_type='districts',
            status='running',
            started_at=datetime.utcnow()
        )
        session.add(sync_log)
        session.commit()
        
        # Process and insert districts
        print(f"📝 Processing districts...")
        
        inserted_count = 0
        skipped_count = 0
        error_count = 0
        
        for index, row in df.iterrows():
            try:
                city_name = str(row['المدينة']).strip()
                district_name = str(row['حي']).strip()
                
                # Skip empty values
                if not city_name or city_name == 'nan' or not district_name or district_name == 'nan':
                    skipped_count += 1
                    continue
                
                # Check if this district-city combination already exists
                existing = session.query(District).filter_by(
                    name=district_name, 
                    city_name=city_name
                ).first()
                
                if existing:
                    skipped_count += 1
                    continue
                
                # Create new district entry
                district = District(
                    name=district_name,
                    city_name=city_name
                )
                
                session.add(district)
                inserted_count += 1
                
                # Commit in batches of 100
                if inserted_count % 100 == 0:
                    session.commit()
                    print(f"   ✅ Inserted {inserted_count} districts...")
                
            except Exception as e:
                error_count += 1
                print(f"   ❌ Error processing row {index}: {str(e)}")
                continue
        
        # Final commit
        session.commit()
        
        # Update sync log
        sync_log.status = 'success' if error_count == 0 else 'partial'
        sync_log.records_processed = inserted_count
        sync_log.completed_at = datetime.utcnow()
        if error_count > 0:
            sync_log.error_message = f"Processed with {error_count} errors"
        
        session.commit()
        
        print(f"\n🎉 Districts migration completed:")
        print(f"   - Inserted: {inserted_count}")
        print(f"   - Skipped (duplicates/empty): {skipped_count}")
        print(f"   - Errors: {error_count}")
        print(f"   - Total in database: {session.query(District).count()}")
        
        # Show some examples
        print(f"\n📋 Sample district mappings in database:")
        sample_districts = session.query(District).limit(10).all()
        for district in sample_districts:
            print(f"   {district.name} -> {district.city_name}")
        
        session.close()
        return True
        
    except Exception as e:
        print(f"❌ Error during migration: {str(e)}")
        try:
            session.rollback()
            sync_log.status = 'failed'
            sync_log.error_message = str(e)
            sync_log.completed_at = datetime.utcnow()
            session.commit()
            session.close()
        except:
            pass
        return False

def test_district_lookup():
    """
    Test the district lookup functionality
    """
    try:
        engine = create_engine(DATABASE_URL, echo=False)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        print(f"\n🔍 Testing district lookup functionality:")
        
        # Test some common district names
        test_districts = ["الحمراء الأول", "اليرموك", "المعلمين", "النزهة"]
        
        for district_name in test_districts:
            result = session.query(District).filter_by(name=district_name).first()
            if result:
                print(f"   ✅ {district_name} -> {result.city_name}")
            else:
                print(f"   ❌ {district_name} -> Not found")
        
        session.close()
        
    except Exception as e:
        print(f"❌ Error during testing: {str(e)}")

if __name__ == "__main__":
    print(f"🚀 Starting districts migration...")
    success = populate_districts_from_excel()
    
    if success:
        test_district_lookup()
        print(f"\n✅ Districts migration completed successfully!")
    else:
        print(f"\n❌ Districts migration failed!")
        sys.exit(1) 