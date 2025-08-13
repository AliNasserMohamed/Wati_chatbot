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
            else:
                city_data["match_type"] = "partial"
                partial_matches.append(city_data)
        
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
        """Search brands by name within a specific city only (not global search)"""
        # Find the city first
        city = db.query(City).filter(
            or_(
                City.name.ilike(f"%{city_name}%"),
                City.name_en.ilike(f"%{city_name}%"),
                City.title.ilike(f"%{city_name}%")
            )
        ).first()
        
        if not city:
            return []
        
        # Search brands only within this city
        matching_brands = []
        for brand in city.brands:
            if (brand.title and brand_name.lower() in brand.title.lower()) or \
               (brand.title_en and brand_name.lower() in brand.title_en.lower()):
                matching_brands.append({
                    "id": brand.id,
                    "external_id": brand.external_id,
                    "title": brand.title,
                    "title_en": brand.title_en,
                    "image_url": brand.image_url,
                    "city_id": city.id,
                    "city_name": city.name,
                    "city_name_en": city.name_en
                })
        
        return matching_brands
    
    @staticmethod 
    def get_products_by_brand_and_city_name(db: Session, brand_name: str, city_name: str) -> List[Dict[str, Any]]:
        """Get products by brand name and city name with fuzzy matching"""
        # Find the brand in the specified city
        brand = (db.query(Brand)
                .join(City.brands)
                .filter(
                    or_(
                        Brand.title.ilike(f"%{brand_name}%"),
                        Brand.title_en.ilike(f"%{brand_name}%")
                    ),
                    or_(
                        City.name.ilike(f"%{city_name}%"),
                        City.name_en.ilike(f"%{city_name}%"),
                        City.title.ilike(f"%{city_name}%")
                    )
                ).first())
        
        if not brand:
            return []
        
        # Get the city information
        city = (db.query(City)
                .join(City.brands)
                .filter(Brand.id == brand.id)
                .filter(
                    or_(
                        City.name.ilike(f"%{city_name}%"),
                        City.name_en.ilike(f"%{city_name}%"),
                        City.title.ilike(f"%{city_name}%")
                    )
                ).first())
        
        # Get products for this brand
        products = DatabaseManager.get_products_by_brand(db, brand.id)
        return [
            {
                "product_id": product.id,
                "external_id": product.external_id,
                "product_title": product.title,
                "product_title_en": product.title_en,
                "product_packing": product.packing,
                "product_contract_price": product.contract_price,
                "brand_id": brand.id,
                "brand_title": brand.title,
                "brand_title_en": brand.title_en,
                "city_id": city.id if city else None,
                "city_name": city.name if city else None,
                "city_name_en": city.name_en if city else None
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
                "error": f" يمكنك تصفح جميع الأصناف والأسعار في التطبيق:\n\n📱 **حمل تطبيق أبار:** https://onelink.to/abar_app\n\n🌐 **أو عن طريق الموقع الإلكتروني:** https://abar.app/en/store/\n\nالتطبيق يعرض لك جميع العلامات التجارية المتوفرة في منطقتك مع الأسعار والعروض الخاصة! 🚚💧",
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
                "error": f"لم أجد منتجات في مدينة '{city_name}'.",
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