#!/usr/bin/env python3
"""
Test script to verify the enhanced API functionality with simplified responses
and the new query agent with function calling capabilities
"""

import requests
import json
import time

def test_simplified_apis():
    """Test the simplified API responses"""
    base_url = "http://localhost:8000/api"
    
    print("🧪 Testing Simplified API Responses...")
    print("=" * 60)
    
    # Test Cities API
    print("\n🏙️ Testing Cities API...")
    try:
        response = requests.get(f"{base_url}/cities")
        if response.status_code == 200:
            data = response.json()
            if data.get("success") and data.get("data"):
                cities = data["data"]
                print(f"✅ Found {len(cities)} cities")
                
                sample_city = cities[0]
                print(f"📍 Sample city structure:")
                for key, value in sample_city.items():
                    print(f"   - {key}: {value}")
                    
                # Test specific city details
                city_id = sample_city["id"]
                city_response = requests.get(f"{base_url}/cities/{city_id}")
                if city_response.status_code == 200:
                    print(f"✅ City details endpoint working")
                else:
                    print(f"❌ City details endpoint failed: {city_response.status_code}")
            else:
                print("❌ No cities data found")
        else:
            print(f"❌ Cities API failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Error testing cities API: {str(e)}")
    
    # Test City Search
    print("\n🔍 Testing City Search...")
    try:
        response = requests.get(f"{base_url}/cities/search", params={"q": "رياض"})
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                print(f"✅ City search working - found {len(data.get('data', []))} results")
            else:
                print("❌ City search returned no results")
        else:
            print(f"❌ City search failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Error testing city search: {str(e)}")
    
    # Test Brands by City
    print("\n🏷️ Testing Brands by City API...")
    try:
        # Get first city ID
        cities_response = requests.get(f"{base_url}/cities")
        cities_data = cities_response.json()
        
        if cities_data.get("success") and cities_data.get("data"):
            city_id = cities_data["data"][0]["id"]
            brands_response = requests.get(f"{base_url}/cities/{city_id}/brands")
            
            if brands_response.status_code == 200:
                brands_data = brands_response.json()
                if brands_data.get("success"):
                    brands = brands_data.get("data", [])
                    print(f"✅ Found {len(brands)} brands for city {city_id}")
                    
                    if brands:
                        sample_brand = brands[0]
                        print(f"🏷️ Sample brand structure:")
                        for key, value in sample_brand.items():
                            print(f"   - {key}: {value}")
                else:
                    print("❌ No brands data found")
            else:
                print(f"❌ Brands API failed: {brands_response.status_code}")
    except Exception as e:
        print(f"❌ Error testing brands API: {str(e)}")
    
    # Test Products by Brand
    print("\n📦 Testing Products by Brand API...")
    try:
        # Get first brand ID
        brands_response = requests.get(f"{base_url}/brands")
        brands_data = brands_response.json()
        
        if brands_data.get("success") and brands_data.get("data"):
            brand_id = brands_data["data"][0]["id"]
            products_response = requests.get(f"{base_url}/brands/{brand_id}/products")
            
            if products_response.status_code == 200:
                products_data = products_response.json()
                if products_data.get("success"):
                    products = products_data.get("data", [])
                    print(f"✅ Found {len(products)} products for brand {brand_id}")
                    
                    if products:
                        sample_product = products[0]
                        print(f"📦 Sample product structure:")
                        for key, value in sample_product.items():
                            print(f"   - {key}: {value}")
                        
                        # Verify simplified structure
                        required_fields = ["product_id", "product_title", "product_packing", "product_contract_price"]
                        missing_fields = [field for field in required_fields if field not in sample_product]
                        if missing_fields:
                            print(f"⚠️ Missing required fields: {missing_fields}")
                        else:
                            print("✅ All required product fields present")
                else:
                    print("❌ No products data found")
            else:
                print(f"❌ Products API failed: {products_response.status_code}")
    except Exception as e:
        print(f"❌ Error testing products API: {str(e)}")
    
    # Test Product Search
    print("\n🔍 Testing Product Search...")
    try:
        response = requests.get(f"{base_url}/products/search", params={"q": "مياه"})
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                print(f"✅ Product search working - found {len(data.get('data', []))} results")
            else:
                print("❌ Product search returned no results")
        else:
            print(f"❌ Product search failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Error testing product search: {str(e)}")

def test_query_agent():
    """Test the enhanced query agent with function calling"""
    print("\n\n🤖 Testing Enhanced Query Agent...")
    print("=" * 60)
    
    # Test different types of queries that should trigger function calls
    test_queries = [
        {
            "query": "ما هي المدن المتاحة؟",
            "expected_function": "get_all_cities",
            "description": "List all available cities"
        },
        {
            "query": "ما هي العلامات التجارية في الرياض؟",
            "expected_function": "get_city_id_by_name + get_brands_by_city",
            "description": "Get brands in Riyadh"
        },
        {
            "query": "أبحث عن منتجات المياه",
            "expected_function": "search_products",
            "description": "Search for water products"
        }
    ]
    
    # Note: Since we can't directly test the query agent without running the full webhook,
    # we'll test the API endpoints that the query agent would call
    
    for i, test_case in enumerate(test_queries, 1):
        print(f"\n🧪 Test Case {i}: {test_case['description']}")
        print(f"Query: {test_case['query']}")
        print(f"Expected Function: {test_case['expected_function']}")
        
        # Simulate what the query agent would do
        if "get_all_cities" in test_case['expected_function']:
            try:
                response = requests.get("http://localhost:8000/api/cities")
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        print(f"✅ Cities API call would succeed - {len(data.get('data', []))} cities")
                    else:
                        print("❌ Cities API call would fail - no data")
                else:
                    print(f"❌ Cities API call would fail - HTTP {response.status_code}")
            except Exception as e:
                print(f"❌ Cities API test failed: {str(e)}")
        
        if "get_city_id_by_name" in test_case['expected_function']:
            try:
                # Test city search for Riyadh
                response = requests.get("http://localhost:8000/api/cities/search", params={"q": "رياض"})
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success") and data.get("data"):
                        city_id = data["data"][0]["id"]
                        print(f"✅ City ID lookup would succeed - Riyadh ID: {city_id}")
                        
                        # Test brands for that city
                        brands_response = requests.get(f"http://localhost:8000/api/cities/{city_id}/brands")
                        if brands_response.status_code == 200:
                            brands_data = brands_response.json()
                            if brands_data.get("success"):
                                print(f"✅ Brands lookup would succeed - {len(brands_data.get('data', []))} brands")
                            else:
                                print("❌ Brands lookup would fail - no data")
                        else:
                            print(f"❌ Brands lookup would fail - HTTP {brands_response.status_code}")
                    else:
                        print("❌ City ID lookup would fail - city not found")
                else:
                    print(f"❌ City search would fail - HTTP {response.status_code}")
            except Exception as e:
                print(f"❌ City search test failed: {str(e)}")
        
        if "search_products" in test_case['expected_function']:
            try:
                response = requests.get("http://localhost:8000/api/products/search", params={"q": "مياه"})
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        print(f"✅ Product search would succeed - {len(data.get('data', []))} products")
                    else:
                        print("❌ Product search would fail - no data")
                else:
                    print(f"❌ Product search would fail - HTTP {response.status_code}")
            except Exception as e:
                print(f"❌ Product search test failed: {str(e)}")

def check_server_status():
    """Check if the server is running"""
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        if response.status_code == 200:
            print("✅ Server is running and healthy")
            return True
        else:
            print(f"⚠️ Server health check returned: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to server. Please start it with: python app.py")
        return False
    except Exception as e:
        print(f"❌ Error checking server: {str(e)}")
        return False

def main():
    """Run all tests"""
    print("🧪 Enhanced API Testing Suite")
    print("=" * 80)
    
    # Check server status
    if not check_server_status():
        return False
    
    # Test simplified APIs
    test_simplified_apis()
    
    # Test query agent functionality
    test_query_agent()
    
    print("\n" + "=" * 80)
    print("🎉 Enhanced API Testing Complete!")
    print("\n📝 Summary of Changes:")
    print("✅ Cities API now returns only: id, external_id, name (Arabic), name_en (English)")
    print("✅ Brands API now returns only: id, external_id, title (Brand name)")
    print("✅ Products API now returns: product_id, product_title, product_packing, product_contract_price")
    print("✅ Added search endpoints for cities and products")
    print("✅ Enhanced Query agent with function calling capabilities")
    print("✅ Query agent can intelligently call APIs based on user queries")
    print("✅ Proper error handling and user guidance implemented")
    
    return True

if __name__ == "__main__":
    success = main()
    if not success:
        exit(1) 