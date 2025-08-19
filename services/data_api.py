from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException
from sqlalchemy import or_

from database.db_utils import DatabaseManager
from database.db_models import City, Brand, Product

class DataAPIService:
    """Internal API service to fetch data from the database with unified ID structure"""
    
    @staticmethod
    def get_all_cities(db: Session) -> List[Dict[str, Any]]:
        """Get all cities from database - simplified response"""
        cities = DatabaseManager.get_all_cities(db)
        return [
            {
                "id": city.id,              # Now matches external ID
                "external_id": city.external_id,
                "name": city.name,          # Arabic name
                "name_en": city.name_en     # English name
            }
            for city in cities
        ]
    
    @staticmethod
    def get_city_by_id(db: Session, city_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific city by ID - simplified response"""
        city = db.query(City).filter(City.id == city_id).first()
        if not city:
            return None
        
        return {
            "id": city.id,              # Now matches external ID
            "external_id": city.external_id,
            "name": city.name,          # Arabic name
            "name_en": city.name_en     # English name
        }
    
    @staticmethod
    def get_city_id_by_name(db: Session, city_name: str) -> Optional[int]:
        """Get city ID by name (supports both Arabic and English names)"""
        city = db.query(City).filter(
            (City.name.ilike(f"%{city_name}%")) | 
            (City.name_en.ilike(f"%{city_name}%")) |
            (City.title.ilike(f"%{city_name}%"))
        ).first()
        
        if city:
            return city.id  # Now this is the same as external_id
        return None
    
    @staticmethod
    def search_cities(db: Session, query: str) -> List[Dict[str, Any]]:
        """
        Enhanced city search with exact and partial matching.
        Returns cities ordered by relevance (exact matches first, then partial)
        
        Args:
            db: Database session
            query: Search term (can be Arabic or English)
            
        Returns:
            List of cities with match_type indicating exact or partial match
        """
        if not query or not query.strip():
            return []
        
        query_normalized = query.strip().lower()
        
        # Get all cities for filtering
        cities = db.query(City).all()
        
        exact_matches = []
        partial_matches = []
        
        for city in cities:
            city_name_lower = city.name.lower() if city.name else ""
            city_name_en_lower = city.name_en.lower() if city.name_en else ""
            
            city_data = {
                "id": city.id,
                "external_id": city.external_id,
                "name": city.name,
                "name_en": city.name_en or ""
            }
            
            # Check for exact matches
            if (query_normalized == city_name_lower or 
                query_normalized == city_name_en_lower):
                city_data["match_type"] = "exact"
                exact_matches.append(city_data)
            # Check for partial matches (search term must be contained in city name)
            elif (query_normalized in city_name_lower or 
                  query_normalized in city_name_en_lower):
                city_data["match_type"] = "partial"
                partial_matches.append(city_data)
            # If no match at all, don't include this city
        
        # Return exact matches first, then partial matches
        return exact_matches + partial_matches
    
    @staticmethod
    def get_brands_by_city(db: Session, city_id: int) -> List[Dict[str, Any]]:
        """Get all brands for a specific city using city ID - simplified response"""
        # Since IDs are now unified, we can use the city_id directly
        city = db.query(City).filter(City.id == city_id).first()
        if not city:
            return []
        
        return [
            {
                "id": brand.id,              # Now matches external ID
                "external_id": brand.external_id,
                "title": brand.title         # Brand name
            }
            for brand in city.brands
        ]
    
    @staticmethod
    def get_brands_by_city_name(db: Session, city_name: str) -> List[Dict[str, Any]]:
        """Get all brands for a specific city using city name with fuzzy matching"""
        # First try to find the city by name
        city = db.query(City).filter(
            or_(
                City.name.ilike(f"%{city_name}%"),
                City.name_en.ilike(f"%{city_name}%"),
                City.title.ilike(f"%{city_name}%")
            )
        ).first()
        
        if not city:
            return []
        
        return [
            {
                "id": brand.id,
                "external_id": brand.external_id,
                "title": brand.title,
                "title_en": brand.title_en,
                "image_url": brand.image_url,
                "city_id": city.id,
                "city_name": city.name,
                "city_name_en": city.name_en
            }
            for brand in city.brands
        ]
    
    @staticmethod
    def search_brands_in_city(db: Session, brand_name: str, city_name: str) -> List[Dict[str, Any]]:
        """Search brands by name within a specific city only (not global search)
        Prioritizes exact matches first, then partial matches
        """
        from database.district_utils import DistrictLookup
        
        # Normalize inputs for better matching
        normalized_brand_name = DistrictLookup.normalize_city_name(brand_name).lower()
        normalized_city_name = DistrictLookup.normalize_city_name(city_name).lower()
        
        # Find the city first - prioritize exact matches
        city = None
        
        # Try exact match first (normalized)
        for city_candidate in db.query(City).all():
            city_ar_normalized = DistrictLookup.normalize_city_name(city_candidate.name).lower()
            city_en_normalized = city_candidate.name_en.lower() if city_candidate.name_en else ""
            
            if (city_ar_normalized == normalized_city_name or 
                city_en_normalized == normalized_city_name):
                city = city_candidate
                break
        
        # If no exact match, try partial match
        if not city:
            city = db.query(City).filter(
                or_(
                    City.name.ilike(f"%{city_name}%"),
                    City.name_en.ilike(f"%{city_name}%"),
                    City.title.ilike(f"%{city_name}%")
                )
            ).first()
        
        if not city:
            return []
        
        # Search brands only within this city - PRIORITIZE EXACT MATCHES FIRST
        exact_matches = []
        partial_matches = []
        
        for brand in city.brands:
            if not brand.title:
                continue
                
            # Normalize brand title for comparison
            normalized_brand_title = DistrictLookup.normalize_city_name(brand.title).lower()
            normalized_brand_title_en = brand.title_en.lower() if brand.title_en else ""
            
            brand_info = {
                "id": brand.id,
                "external_id": brand.external_id,
                "title": brand.title,
                "title_en": brand.title_en,
                "image_url": brand.image_url,
                "city_id": city.id,
                "city_name": city.name,
                "city_name_en": city.name_en
            }
            
            # Check for EXACT matches first (normalized)
            if (normalized_brand_title == normalized_brand_name or 
                normalized_brand_title_en == normalized_brand_name):
                exact_matches.append(brand_info)
            # Then check for PARTIAL matches
            elif (normalized_brand_name in normalized_brand_title or 
                  normalized_brand_name in normalized_brand_title_en):
                partial_matches.append(brand_info)
        
        print(f"🔍 Brand search results for '{brand_name}' in '{city_name}':")
        print(f"   ✅ Exact matches: {len(exact_matches)}")
        print(f"   🔍 Partial matches: {len(partial_matches)}")
        
        # Return exact matches first, then partial matches
        return exact_matches + partial_matches
    
    @staticmethod 
    def get_products_by_brand_and_city_name(db: Session, brand_name: str, city_name: str) -> List[Dict[str, Any]]:
        """Get products by brand name and city name with EXACT matching prioritized"""
        from database.district_utils import DistrictLookup
        
        # Normalize inputs for exact matching
        normalized_brand_name = DistrictLookup.normalize_city_name(brand_name).lower()
        normalized_city_name = DistrictLookup.normalize_city_name(city_name).lower()
        
        print(f"🔍 Searching for products: brand='{brand_name}' city='{city_name}'")
        print(f"   Normalized: brand='{normalized_brand_name}' city='{normalized_city_name}'")
        
        # STEP 1: Find the city first with EXACT matching
        target_city = None
        
        # Try exact city match first (normalized)
        for city_candidate in db.query(City).all():
            city_ar_normalized = DistrictLookup.normalize_city_name(city_candidate.name).lower()
            city_en_normalized = city_candidate.name_en.lower() if city_candidate.name_en else ""
            
            if (city_ar_normalized == normalized_city_name or 
                city_en_normalized == normalized_city_name):
                target_city = city_candidate
                print(f"   ✅ Found EXACT city match: '{city_candidate.name}'")
                break
        
        # If no exact city match, try partial match as fallback
        if not target_city:
            target_city = db.query(City).filter(
                or_(
                    City.name.ilike(f"%{city_name}%"),
                    City.name_en.ilike(f"%{city_name}%"),
                    City.title.ilike(f"%{city_name}%")
                )
            ).first()
            if target_city:
                print(f"   🔍 Found PARTIAL city match: '{target_city.name}'")
        
        if not target_city:
            print(f"   ❌ No city found for '{city_name}'")
            return []
        
        # STEP 2: Find the brand in this specific city with EXACT matching
        target_brand = None
        
        # Try exact brand match first (normalized)
        for brand in target_city.brands:
            if not brand.title:
                continue
                
            brand_ar_normalized = DistrictLookup.normalize_city_name(brand.title).lower()
            brand_en_normalized = brand.title_en.lower() if brand.title_en else ""
            
            if (brand_ar_normalized == normalized_brand_name or 
                brand_en_normalized == normalized_brand_name):
                target_brand = brand
                print(f"   ✅ Found EXACT brand match: '{brand.title}'")
                break
        
        # If no exact brand match, try partial match as fallback
        if not target_brand:
            for brand in target_city.brands:
                if not brand.title:
                    continue
                    
                brand_ar_normalized = DistrictLookup.normalize_city_name(brand.title).lower()
                brand_en_normalized = brand.title_en.lower() if brand.title_en else ""
                
                if (normalized_brand_name in brand_ar_normalized or 
                    normalized_brand_name in brand_en_normalized):
                    target_brand = brand
                    print(f"   🔍 Found PARTIAL brand match: '{brand.title}'")
                    break
        
        if not target_brand:
            print(f"   ❌ No brand '{brand_name}' found in city '{target_city.name}'")
            return []
        
        # STEP 3: Get products for this exact brand
        products = DatabaseManager.get_products_by_brand(db, target_brand.id)
        print(f"   📦 Found {len(products)} products for {target_brand.title} in {target_city.name}")
        
        return [
            {
                "product_id": product.id,
                "external_id": product.external_id,
                "product_title": product.title,
                "product_title_en": product.title_en,
                "product_packing": product.packing,
                "product_contract_price": product.contract_price,
                "brand_id": target_brand.id,
                "brand_title": target_brand.title,
                "brand_title_en": target_brand.title_en,
                "city_id": target_city.id,
                "city_name": target_city.name,
                "city_name_en": target_city.name_en
            }
            for product in products
        ]

    @staticmethod
    def get_brands_by_city_external_id(db: Session, city_external_id: int) -> List[Dict[str, Any]]:
        """Get all brands for a specific city using external city ID - now same as get_brands_by_city"""
        return DataAPIService.get_brands_by_city(db, city_external_id)
    
    @staticmethod
    def get_all_brands(db: Session) -> List[Dict[str, Any]]:
        """Get all brands from database - simplified response"""
        brands = db.query(Brand).all()
        return [
            {
                "id": brand.id,              # Now matches external ID
                "external_id": brand.external_id,
                "title": brand.title,
                "title_en": brand.title_en,
                "image_url": brand.image_url,
                "mounting_rate_image": brand.mounting_rate_image,
                "meta_keywords": brand.meta_keywords,
                "meta_description": brand.meta_description,
                "created_at": brand.created_at.isoformat() if brand.created_at else None,
                "updated_at": brand.updated_at.isoformat() if brand.updated_at else None
            }
            for brand in brands
        ]
    
    @staticmethod
    def get_brand_by_id(db: Session, brand_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific brand by ID - simplified response"""
        brand = db.query(Brand).filter(Brand.id == brand_id).first()
        if not brand:
            return None
        
        return {
            "id": brand.id,              # Now matches external ID
            "external_id": brand.external_id,
            "title": brand.title,
            "title_en": brand.title_en,
            "image_url": brand.image_url,
            "mounting_rate_image": brand.mounting_rate_image,
            "meta_keywords": brand.meta_keywords,
            "meta_description": brand.meta_description,
            "created_at": brand.created_at.isoformat() if brand.created_at else None,
            "updated_at": brand.updated_at.isoformat() if brand.updated_at else None
        }
    
    @staticmethod
    def search_brands(db: Session, query: str) -> List[Dict[str, Any]]:
        """Search brands by title"""
        brands = db.query(Brand).filter(
            Brand.title.ilike(f"%{query}%") | 
            Brand.title_en.ilike(f"%{query}%")
        ).all()
        
        return [
            {
                "id": brand.id,              # Now matches external ID
                "external_id": brand.external_id,
                "title": brand.title,
                "title_en": brand.title_en,
                "image_url": brand.image_url,
                "mounting_rate_image": brand.mounting_rate_image,
                "meta_keywords": brand.meta_keywords,
                "meta_description": brand.meta_description,
                "created_at": brand.created_at.isoformat() if brand.created_at else None,
                "updated_at": brand.updated_at.isoformat() if brand.updated_at else None
            }
            for brand in brands
        ]
    
    @staticmethod
    def get_products_by_brand(db: Session, brand_id: int) -> List[Dict[str, Any]]:
        """Get all products for a specific brand - simplified response"""
        products = DatabaseManager.get_products_by_brand(db, brand_id)
        return [
            {
                "product_id": product.id,           # Now matches external ID
                "external_id": product.external_id,
                "product_title": product.title,
                "product_packing": product.packing,
                "product_contract_price": product.contract_price  # Use correct field
            }
            for product in products
        ]
    
    @staticmethod
    def get_all_products(db: Session) -> List[Dict[str, Any]]:
        """Get all products from database - simplified response"""
        products = db.query(Product).all()
        return [
            {
                "product_id": product.id,           # Now matches external ID
                "external_id": product.external_id,
                "product_title": product.title,
                "product_packing": product.packing,
                "product_contract_price": product.contract_price  # Use correct field
            }
            for product in products
        ]
    
    @staticmethod
    def get_product_by_id(db: Session, product_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific product by ID - simplified response"""
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            return None
        
        return {
            "product_id": product.id,           # Now matches external ID
            "external_id": product.external_id,
            "product_title": product.title,
            "product_packing": product.packing,
            "product_contract_price": product.contract_price  # Use correct field
        }
    
    @staticmethod
    def search_products(db: Session, query: str) -> List[Dict[str, Any]]:
        """Search products by title - simplified response"""
        products = db.query(Product).filter(
            Product.title.ilike(f"%{query}%")
        ).all()
        
        return [
            {
                "product_id": product.id,           # Now matches external ID
                "external_id": product.external_id,
                "product_title": product.title,
                "product_packing": product.packing,
                "product_contract_price": product.contract_price  # Use correct field
            }
            for product in products
        ]
    
    @staticmethod
    def get_brand_with_products(db: Session, brand_id: int) -> Optional[Dict[str, Any]]:
        """Get brand with all its products"""
        brand = db.query(Brand).filter(Brand.id == brand_id).first()
        if not brand:
            return None
        
        products = DataAPIService.get_products_by_brand(db, brand_id)
        
        return {
            "id": brand.id,              # Now matches external ID
            "external_id": brand.external_id,
            "title": brand.title,
            "title_en": brand.title_en,
            "image_url": brand.image_url,
            "products": products
        }
    
    @staticmethod
    def get_city_with_brands_and_products(db: Session, city_id: int) -> Optional[Dict[str, Any]]:
        """Get city with all its brands and their products"""
        city = db.query(City).filter(City.id == city_id).first()
        if not city:
            return None
        
        brands_with_products = []
        for brand in city.brands:
            brand_data = DataAPIService.get_brand_with_products(db, brand.id)
            if brand_data:
                brands_with_products.append(brand_data)
        
        return {
            "id": city.id,              # Now matches external ID
            "external_id": city.external_id,
            "name": city.name,
            "name_en": city.name_en,
            "brands": brands_with_products
        }

    @staticmethod
    def get_cheapest_products_by_city_name(db: Session, city_name: str) -> Dict[str, Any]:
        """Get cheapest products in each size for a specific city"""
        # Find the city first
        city = db.query(City).filter(
            or_(
                City.name.ilike(f"%{city_name}%"),
                City.name_en.ilike(f"%{city_name}%"),
                City.title.ilike(f"%{city_name}%")
            )
        ).first()
        
        if not city:
            return {
                "success": False,
                "error": f"بتحصل الاصناف والاسعار في التطبيق وهذا هو الرابط https://onelink.to/abar_app https://abar.app/en/store/ وايضا عن طريق الموقع الالكتروني",
                "original_city": city_name,
                "show_app_links": True
            }
        
        # Get all products from all brands in this city
        all_products = []
        for brand in city.brands:
            products = DatabaseManager.get_products_by_brand(db, brand.id)
            for product in products:
                all_products.append({
                    "product_id": product.id,
                    "product_title": product.title,
                    "product_packing": product.packing,
                    "product_contract_price": float(product.contract_price) if product.contract_price else 0.0,
                    "brand_id": brand.id,
                    "brand_title": brand.title,
                    "brand_title_en": brand.title_en,
                    "city_id": city.id,
                    "city_name": city.name,
                    "city_name_en": city.name_en
                })
        
        if not all_products:
            return {
                "success": False,
                "error": f"بتحصل الاصناف والاسعار في التطبيق وهذا هو الرابط https://onelink.to/abar_app https://abar.app/en/store/ وايضا عن طريق الموقع الالكتروني",
                "city_name": city.name
            }
        
        # Group products by size/packing and find cheapest in each group
        size_groups = {}
        
        for product in all_products:
            packing = product["product_packing"]
            price = product["product_contract_price"]
            
            if price > 0:  # Only consider products with valid prices
                if packing not in size_groups or price < size_groups[packing]["product_contract_price"]:
                    size_groups[packing] = product
        
        # Convert to list and sort by price
        cheapest_products = list(size_groups.values())
        cheapest_products.sort(key=lambda x: x["product_contract_price"])
        
        return {
            "success": True,
            "city_name": city.name,
            "city_name_en": city.name_en,
            "data": cheapest_products,
            "total_sizes": len(cheapest_products),
            "message": f"أرخص المنتجات في كل حجم في مدينة {city.name}"
        }

# Singleton instance
data_api = DataAPIService() 
#data_api.get_products_by_brand(db, 1288)