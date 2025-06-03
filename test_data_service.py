#!/usr/bin/env python3
"""
Test script for the data scraping and API services
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.db_utils import SessionLocal, DatabaseManager
from services.data_scraper import data_scraper
from services.data_api import data_api

def test_data_scraping():
    """Test the data scraping functionality"""
    print("=" * 50)
    print("Testing Data Scraping Service")
    print("=" * 50)
    
    db = SessionLocal()
    try:
        # Test full sync
        print("\n1. Testing full data sync...")
        results = data_scraper.full_sync(db)
        print(f"Sync Results: {results}")
        
        # Test individual syncs
        print("\n2. Testing cities sync...")
        cities_count = data_scraper.sync_cities(db)
        print(f"Cities synced: {cities_count}")
        
        print("\n3. Testing brands sync...")
        brands_count = data_scraper.sync_all_brands(db)
        print(f"Brands synced: {brands_count}")
        
        print("\n4. Testing brand details sync...")
        details_count = data_scraper.sync_brand_details(db)
        print(f"Brand details and products synced: {details_count}")
        
        print("\n✅ Data scraping tests completed successfully!")
        
    except Exception as e:
        print(f"❌ Data scraping test failed: {str(e)}")
    finally:
        db.close()

def test_data_apis():
    """Test the internal data API services"""
    print("\n" + "=" * 50)
    print("Testing Data API Service")
    print("=" * 50)
    
    db = SessionLocal()
    try:
        # Test cities API
        print("\n1. Testing cities API...")
        cities = data_api.get_all_cities(db)
        print(f"Total cities: {len(cities)}")
        if cities:
            print(f"First city: {cities[0]}")
        
        # Test brands API
        print("\n2. Testing brands API...")
        brands = data_api.get_all_brands(db)
        print(f"Total brands: {len(brands)}")
        if brands:
            print(f"First brand: {brands[0]}")
        
        # Test products API
        print("\n3. Testing products API...")
        products = data_api.get_all_products(db)
        print(f"Total products: {len(products)}")
        if products:
            print(f"First product: {products[0]}")
        
        # Test search functionality
        print("\n4. Testing search functionality...")
        search_results = data_api.search_brands(db, "مياه")
        print(f"Brands matching 'مياه': {len(search_results)}")
        
        # Test relationships
        if cities:
            city_id = cities[0]['id']
            print(f"\n5. Testing city-brands relationship for city {city_id}...")
            city_brands = data_api.get_brands_by_city(db, city_id)
            print(f"Brands in city {city_id}: {len(city_brands)}")
        
        if brands:
            brand_id = brands[0]['id']
            print(f"\n6. Testing brand-products relationship for brand {brand_id}...")
            brand_products = data_api.get_products_by_brand(db, brand_id)
            print(f"Products in brand {brand_id}: {len(brand_products)}")
        
        print("\n✅ Data API tests completed successfully!")
        
    except Exception as e:
        print(f"❌ Data API test failed: {str(e)}")
    finally:
        db.close()

def main():
    """Main test function"""
    print("Starting Data Service Tests...")
    
    # Test data scraping
    test_data_scraping()
    
    # Test data APIs
    test_data_apis()
    
    print("\n" + "=" * 50)
    print("All tests completed!")
    print("=" * 50)

if __name__ == "__main__":
    main() 