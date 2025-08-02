from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException

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
        """Search cities by name with special Riyadh regions handling - simplified response"""
        query_normalized = query.strip().lower()
        
        # Special handling for Riyadh regions - prioritize exact matches
        riyadh_regions = {
            "شمال الرياض": ["شمال الرياض", "north riyadh", "الرياض الشمالي"],
            "جنوب الرياض": ["جنوب الرياض", "south riyadh", "الرياض الجنوبي"], 
            "غرب الرياض": ["غرب الرياض", "west riyadh", "الرياض الغربي"],
            "شرق الرياض": ["شرق الرياض", "east riyadh", "الرياض الشرقي"],
            "الرياض": ["الرياض", "riyadh", "رياض"]
        }
        
        # Check for Riyadh regions with priority handling
        for region_name, variations in riyadh_regions.items():
            for variation in variations:
                if query_normalized == variation.lower():
                    # Find exact match for this specific region
                    exact_city = db.query(City).filter(City.name == region_name).first()
                    if exact_city:
                        return [{
                            "id": exact_city.id,
                            "external_id": exact_city.external_id,
                            "name": exact_city.name,
                            "name_en": exact_city.name_en or "",
                            "match_type": "exact_region"
                        }]
        
        # If user searches for just "الرياض" or "riyadh", return main Riyadh first, then regions
        if query_normalized in ["الرياض", "riyadh", "رياض"]:
            results = []
            
            # Add main Riyadh first
            main_riyadh = db.query(City).filter(City.name == "الرياض").first()
            if main_riyadh:
                results.append({
                    "id": main_riyadh.id,
                    "external_id": main_riyadh.external_id,
                    "name": main_riyadh.name,
                    "name_en": main_riyadh.name_en or "",
                    "match_type": "main_city"
                })
            
            # Then add Riyadh regions
            riyadh_region_names = ["شمال الرياض", "جنوب الرياض", "غرب الرياض", "شرق الرياض"]
            region_cities = db.query(City).filter(City.name.in_(riyadh_region_names)).all()
            for city in region_cities:
                results.append({
                    "id": city.id,
                    "external_id": city.external_id,
                    "name": city.name,
                    "name_en": city.name_en or "",
                    "match_type": "region"
                })
            
            if results:
                return results
        
        # Regular search for other cities
        cities = db.query(City).filter(
            City.name.ilike(f"%{query}%") | 
            City.name_en.ilike(f"%{query}%") |
            City.title.ilike(f"%{query}%")
        ).all()
        
        # Sort results: exact matches first, then partial matches
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
                "title": brand.title         # Brand name
            }
            for brand in brands
        ]
    
    @staticmethod
    def get_brand_by_id(db: Session, brand_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific brand by ID"""
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

# Singleton instance
data_api = DataAPIService() 