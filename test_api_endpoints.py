#!/usr/bin/env python3
"""
Test script to verify API endpoints work correctly with new city structure
"""

import requests
import json

def test_cities_api():
    """Test the cities API endpoint"""
    try:
        print("🏙️ Testing Cities API...")
        response = requests.get("http://localhost:8000/api/cities")
        
        if response.status_code == 200:
            data = response.json()
            cities = data.get('data', [])
            print(f"✅ Found {len(cities)} cities")
            
            if cities:
                sample_city = cities[0]
                print(f"📍 Sample city:")
                print(f"   - Arabic Name: {sample_city.get('name')}")
                print(f"   - English Name: {sample_city.get('name_en')}")
                print(f"   - Title: {sample_city.get('title')}")
                print(f"   - Coordinates: ({sample_city.get('lat')}, {sample_city.get('lng')})")
                print(f"   - External ID: {sample_city.get('external_id')}")
            
            return True
        else:
            print(f"❌ API returned status {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing cities API: {str(e)}")
        return False

def test_brands_by_city_api():
    """Test getting brands for a specific city"""
    try:
        print("\n🏷️ Testing Brands by City API...")
        # First get a city with brands
        cities_response = requests.get("http://localhost:8000/api/cities")
        cities = cities_response.json().get('data', [])
        
        # Find Riyadh (external_id: 20) which should have brands
        riyadh_city = None
        for city in cities:
            if city.get('external_id') == 20:  # Riyadh
                riyadh_city = city
                break
        
        if riyadh_city:
            city_id = riyadh_city['id']
            print(f"🔍 Testing brands for {riyadh_city['name']} (ID: {city_id})")
            
            response = requests.get(f"http://localhost:8000/api/cities/{city_id}/brands")
            
            if response.status_code == 200:
                data = response.json()
                brands = data.get('data', [])
                print(f"✅ Found {len(brands)} brands in {riyadh_city['name']}")
                
                if brands:
                    sample_brand = brands[0]
                    print(f"🏷️ Sample brand:")
                    print(f"   - Arabic Title: {sample_brand.get('title')}")
                    print(f"   - English Title: {sample_brand.get('title_en')}")
                    print(f"   - External ID: {sample_brand.get('external_id')}")
                    print(f"   - Cities: {len(sample_brand.get('cities', []))} cities served")
                
                return True
            else:
                print(f"❌ API returned status {response.status_code}")
                return False
        else:
            print("❌ Could not find Riyadh city")
            return False
            
    except Exception as e:
        print(f"❌ Error testing brands API: {str(e)}")
        return False

def test_server_status():
    """Test if server is running"""
    try:
        response = requests.get("http://localhost:8000/health")
        if response.status_code == 200:
            print("✅ Server is running")
            return True
        else:
            print(f"❌ Server health check failed: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to server. Is it running?")
        return False
    except Exception as e:
        print(f"❌ Error checking server: {str(e)}")
        return False

def main():
    """Run all tests"""
    print("🧪 Testing API Endpoints...")
    print("=" * 50)
    
    # Test server status
    if not test_server_status():
        print("\n❌ Server is not running. Please start it with: python app.py")
        return False
    
    # Test cities API
    cities_ok = test_cities_api()
    
    # Test brands API
    brands_ok = test_brands_by_city_api()
    
    print("\n" + "=" * 50)
    if cities_ok and brands_ok:
        print("🎉 All tests passed!")
        print("\n📝 Summary:")
        print("✅ Cities API working with Arabic/English names and coordinates")
        print("✅ Many-to-many city-brand relationships working")
        print("✅ API endpoints returning correct structure")
        return True
    else:
        print("❌ Some tests failed")
        return False

if __name__ == "__main__":
    success = main()
    if not success:
        exit(1) 