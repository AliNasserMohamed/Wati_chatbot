#!/usr/bin/env python3
"""
Script to fix city-brand many-to-many relationships
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.db_utils import SessionLocal
from database.db_models import City, Brand
from services.data_scraper import data_scraper

def check_current_state():
    """Check current state of city-brand relationships"""
    print("🔍 Checking current city-brand relationships...")
    
    db = SessionLocal()
    try:
        # Get all cities and brands
        cities = db.query(City).all()
        brands = db.query(Brand).all()
        
        print(f"📊 Database Status:")
        print(f"   - Total cities: {len(cities)}")
        print(f"   - Total brands: {len(brands)}")
        
        # Check relationships
        cities_with_brands = 0
        brands_with_cities = 0
        
        for city in cities:
            if len(city.brands) > 0:
                cities_with_brands += 1
                print(f"   - {city.name} ({city.external_id}): {len(city.brands)} brands")
        
        for brand in brands:
            if len(brand.cities) > 0:
                brands_with_cities += 1
        
        print(f"\n📈 Relationship Summary:")
        print(f"   - Cities with brands: {cities_with_brands}/{len(cities)}")
        print(f"   - Brands with cities: {brands_with_cities}/{len(brands)}")
        
        if cities_with_brands == 0:
            print("\n❌ No city-brand relationships found! Need to fix this.")
            return False
        else:
            print("\n✅ City-brand relationships exist.")
            return True
            
    finally:
        db.close()

def fix_relationships():
    """Fix city-brand relationships by re-syncing brands"""
    print("\n🔧 Fixing city-brand relationships...")
    
    db = SessionLocal()
    try:
        # Re-sync brands to create proper relationships
        print("🔄 Re-syncing brands for all cities...")
        result = data_scraper.sync_all_brands(db)
        print(f"✅ Brand sync completed: {result} brands processed")
        
        # Verify the fix
        print("\n🔍 Verifying fix...")
        return check_current_state()
        
    except Exception as e:
        print(f"❌ Error fixing relationships: {str(e)}")
        return False
    finally:
        db.close()

def test_specific_city(city_name="حائل"):
    """Test brands for a specific city"""
    print(f"\n🧪 Testing brands for {city_name}...")
    
    db = SessionLocal()
    try:
        # Find the city
        city = db.query(City).filter(
            (City.name.ilike(f"%{city_name}%")) | 
            (City.name_en.ilike(f"%{city_name}%"))
        ).first()
        
        if city:
            print(f"📍 Found city: {city.name} (ID: {city.id}, External ID: {city.external_id})")
            print(f"🏷️ Brands in this city: {len(city.brands)}")
            
            for brand in city.brands:
                print(f"   - {brand.title} (ID: {brand.id})")
            
            if len(city.brands) == 0:
                print("❌ No brands found for this city!")
                
                # Check if there are any brands at all
                all_brands = db.query(Brand).all()
                print(f"💡 Total brands in database: {len(all_brands)}")
                
                if all_brands:
                    print("🔄 Trying to sync brands for this specific city...")
                    try:
                        result = data_scraper.sync_brands_for_city(db, city.external_id)
                        print(f"✅ Sync result: {result} brands processed")
                        
                        # Check again
                        db.refresh(city)
                        print(f"🔍 After sync - Brands in city: {len(city.brands)}")
                        for brand in city.brands:
                            print(f"   - {brand.title}")
                            
                    except Exception as e:
                        print(f"❌ Sync failed: {str(e)}")
        else:
            print(f"❌ City '{city_name}' not found!")
            
    finally:
        db.close()

def main():
    """Main function"""
    print("🔧 City-Brand Relationship Fixer")
    print("=" * 50)
    
    # Check current state
    relationships_ok = check_current_state()
    
    if not relationships_ok:
        # Try to fix
        print("\n🛠️ Attempting to fix relationships...")
        fix_success = fix_relationships()
        
        if not fix_success:
            print("❌ Failed to fix relationships automatically")
            return False
    
    # Test specific city (Hail)
    test_specific_city("حائل")
    
    print("\n" + "=" * 50)
    print("🎉 Relationship check/fix completed!")
    return True

if __name__ == "__main__":
    success = main()
    if not success:
        sys.exit(1) 