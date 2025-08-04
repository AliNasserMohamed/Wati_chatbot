#!/usr/bin/env python3

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.db_utils import SessionLocal
from services.data_api import data_api

def test_products_by_brand(brand_id: int = 1288):
    """Test get_products_by_brand function with specified brand ID"""
    
    # Create database session
    db = SessionLocal()
    
    try:
        print(f"🔍 Testing data_api.get_products_by_brand(db, {brand_id})")
        print("=" * 60)
        
        # Call the function
        products = data_api.get_products_by_brand(db, brand_id)
        
        print(f"✅ Found {len(products)} products for brand ID {brand_id}")
        
        if products:
            print(f"\n📦 Products for brand ID {brand_id}:")
            print("-" * 60)
            for i, product in enumerate(products, 1):
                print(f"{i:2d}. {product['product_title']}")
                print(f"    📏 Packing: {product['product_packing']}")
                print(f"    💰 Price: {product['product_contract_price']} SAR")
                print(f"    🆔 Product ID: {product['product_id']}")
                print(f"    🔗 External ID: {product['external_id']}")
                print()
        else:
            print(f"⚠️ No products found for brand ID {brand_id}")
            
            # Let's check if the brand exists
            brand_info = data_api.get_brand_by_id(db, brand_id)
            if brand_info:
                print(f"ℹ️ Brand exists: {brand_info['title']}")
                print("   But it has no products associated with it.")
            else:
                print(f"❌ Brand ID {brand_id} does not exist in the database.")
        
        print("=" * 60)
        print("🎉 Test completed!")
        
    except Exception as e:
        print(f"❌ Error during testing: {str(e)}")
        import traceback
        traceback.print_exc()
        
    finally:
        db.close()

if __name__ == "__main__":
    # 🔧 CHANGE THE BRAND ID HERE:
    BRAND_ID = 1288  # ← Modify this value to test different brands
    
    test_products_by_brand(BRAND_ID) 