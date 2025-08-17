#!/usr/bin/env python3

import sys
import os
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add parent directory to Python path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_utils import DATABASE_URL
from database.db_models import Base, District, DataSyncLog
from database.district_utils import DistrictLookup

def normalize_district_city_names():
    """
    Normalize city names in districts table by removing hamza characters
    """
    
    print("🔧 Starting city name normalization migration...")
    
    try:
        # Create database engine
        engine = create_engine(DATABASE_URL, echo=False)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        print(f"🗃️  Connected to database successfully")
        
        # Start logging the sync
        sync_log = DataSyncLog(
            sync_type='districts_normalize',
            status='running',
            started_at=datetime.utcnow()
        )
        session.add(sync_log)
        session.commit()
        
        # Get all districts
        print(f"📊 Getting all districts...")
        all_districts = session.query(District).all()
        print(f"   Found {len(all_districts)} districts to process")
        
        # Track changes
        updated_count = 0
        unchanged_count = 0
        city_name_changes = {}  # Track which city names changed
        
        print(f"🔄 Processing districts...")
        
        for i, district in enumerate(all_districts):
            original_city_name = district.city_name
            normalized_city_name = DistrictLookup.normalize_city_name(original_city_name)
            
            if original_city_name != normalized_city_name:
                # Update the city name
                district.city_name = normalized_city_name
                updated_count += 1
                
                # Track the change
                if original_city_name not in city_name_changes:
                    city_name_changes[original_city_name] = normalized_city_name
                
                if updated_count % 100 == 0:
                    print(f"   ✅ Updated {updated_count} districts...")
                    session.commit()
            else:
                unchanged_count += 1
        
        # Final commit
        session.commit()
        
        # Update sync log
        sync_log.status = 'success'
        sync_log.records_processed = updated_count
        sync_log.completed_at = datetime.utcnow()
        session.commit()
        
        print(f"\n🎉 City name normalization completed:")
        print(f"   - Updated: {updated_count}")
        print(f"   - Unchanged: {unchanged_count}")
        print(f"   - Total processed: {len(all_districts)}")
        
        if city_name_changes:
            print(f"\n📋 City Name Changes Applied:")
            for original, normalized in city_name_changes.items():
                district_count = session.query(District).filter_by(city_name=normalized).count()
                print(f"   '{original}' -> '{normalized}' ({district_count} districts)")
        
        # Test the normalization with a few examples
        print(f"\n🧪 Testing normalization results:")
        
        test_cases = [
            "الأحساء",  # Should find districts
            "الاحساء",  # Should find same districts (normalized)
        ]
        
        for test_city in test_cases:
            normalized = DistrictLookup.normalize_city_name(test_city)
            district_count = session.query(District).filter_by(city_name=normalized).count()
            print(f"   '{test_city}' (normalized to '{normalized}') -> {district_count} districts")
        
        session.close()
        return True
        
    except Exception as e:
        print(f"❌ Error during normalization: {str(e)}")
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

def test_city_matching():
    """
    Test city matching after normalization
    """
    print(f"\n🧪 Testing City Matching After Normalization...")
    
    try:
        engine = create_engine(DATABASE_URL, echo=False)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Import here to avoid circular imports  
        from services.data_api import data_api
        
        # Get system cities
        system_cities = data_api.get_all_cities(session)
        print(f"📡 System cities: {len(system_cities)}")
        
        # Test specific cases
        test_districts = [
            "الحمراء الأول",
            "اليرموك",
            "المعلمين",
            "النزهة"
        ]
        
        for district_name in test_districts:
            # Step 1: Get city from district
            city_from_district = DistrictLookup.get_city_by_district(district_name, session)
            print(f"\n   🏘️ District '{district_name}' -> City: '{city_from_district}'")
            
            if city_from_district:
                # Step 2: Check if city is in system (with normalization)
                normalized_district_city = DistrictLookup.normalize_city_name(city_from_district)
                
                found_in_system = False
                for city in system_cities:
                    system_city_name = city.get('name', '').strip()
                    normalized_system_city = DistrictLookup.normalize_city_name(system_city_name)
                    
                    if normalized_system_city == normalized_district_city:
                        print(f"      ✅ Found match in system: '{system_city_name}' (ID: {city['id']})")
                        found_in_system = True
                        break
                
                if not found_in_system:
                    print(f"      ❌ No match found in system")
        
        session.close()
        
    except Exception as e:
        print(f"❌ Error during testing: {str(e)}")

if __name__ == "__main__":
    print(f"🚀 Starting districts city name normalization...")
    success = normalize_district_city_names()
    
    if success:
        test_city_matching()
        print(f"\n✅ City name normalization completed successfully!")
    else:
        print(f"\n❌ City name normalization failed!")
        sys.exit(1) 