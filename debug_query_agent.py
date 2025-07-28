#!/usr/bin/env python3

import sys
import os
sys.path.append('.')

# Direct import to avoid agents/__init__.py dependency issues
sys.path.append(os.path.join(os.path.dirname(__file__), 'agents'))

from database.db_utils import get_db
from services.data_api import data_api

def test_query_agent_functions():
    print("=== Testing Query Agent Functions ===")
    
    # Import query agent class directly from the file
    import importlib.util
    spec = importlib.util.spec_from_file_location("query_agent", "agents/query_agent.py")
    query_agent_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(query_agent_module)
    QueryAgent = query_agent_module.QueryAgent
    
    # Create instance
    try:
        agent = QueryAgent()
        print("✅ QueryAgent instance created successfully")
    except Exception as e:
        print(f"❌ Error creating QueryAgent: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n1. Testing get_all_cities...")
    try:
        result = agent.get_all_cities()
        print(f"✅ get_all_cities result: {result}")
    except Exception as e:
        print(f"❌ Error in get_all_cities: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n2. Testing get_city_id_by_name...")
    try:
        result = agent.get_city_id_by_name("الدمام")
        print(f"✅ get_city_id_by_name result: {result}")
    except Exception as e:
        print(f"❌ Error in get_city_id_by_name: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n3. Testing get_brands_by_city...")
    try:
        # First get a city ID
        city_result = agent.get_city_id_by_name("الدمام")
        if city_result.get("success") and city_result.get("city_id"):
            brands_result = agent.get_brands_by_city(city_result["city_id"])
            print(f"✅ get_brands_by_city result: {brands_result}")
        else:
            print(f"❌ Could not get city ID, got: {city_result}")
    except Exception as e:
        print(f"❌ Error in get_brands_by_city: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_query_agent_functions() 