from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException

from database.db_utils import DatabaseManager
from database.db_models import City, Brand, Product

class DataAPIService:
    """Internal API service to fetch data from the database"""
    
    @staticmethod
    def get_all_cities(db: Session) -> List[Dict[str, Any]]:
        """Get all cities from database - simplified response"""
        cities = DatabaseManager.get_all_cities(db)
        return [
            {
                "id": city.id,
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
            "id": city.id,
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
            return city.id
        return None
    
    @staticmethod
    def search_cities(db: Session, query: str) -> List[Dict[str, Any]]:
        """Search cities by name - simplified response"""
        cities = db.query(City).filter(
            City.name.ilike(f"%{query}%") | 
            City.name_en.ilike(f"%{query}%") |
            City.title.ilike(f"%{query}%")
        ).all()
        
        return [
            {
                "id": city.id,
                "external_id": city.external_id,
                "name": city.name,          # Arabic name
                "name_en": city.name_en     # English name
            }
            for city in cities
        ]
    
    @staticmethod
    def get_brands_by_city(db: Session, city_id: int) -> List[Dict[str, Any]]:
        """Get all brands for a specific city using internal city ID - simplified response"""
        brands = DatabaseManager.get_brands_by_city_id(db, city_id)
        return [
            {
                "id": brand.id,
                "external_id": brand.external_id,
                "title": brand.title        # Brand name
            }
            for brand in brands
        ]
    
    @staticmethod
    def get_brands_by_city_external_id(db: Session, city_external_id: int) -> List[Dict[str, Any]]:
        """Get all brands for a specific city using external city ID - simplified response"""
        brands = DatabaseManager.get_brands_by_city(db, city_external_id)
        return [
            {
                "id": brand.id,
                "external_id": brand.external_id,
                "title": brand.title        # Brand name
            }
            for brand in brands
        ]
    
    @staticmethod
    def get_all_brands(db: Session) -> List[Dict[str, Any]]:
        """Get all brands from database - simplified response"""
        brands = db.query(Brand).all()
        return [
            {
                "id": brand.id,
                "external_id": brand.external_id,
                "title": brand.title        # Brand name
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
            "id": brand.id,
            "external_id": brand.external_id,
            "city_id": brand.city_id,
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
                "id": brand.id,
                "external_id": brand.external_id,
                "city_id": brand.city_id,
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
                "product_id": product.id,
                "external_id": product.external_id,
                "product_title": product.title,
                "product_packing": product.packing,
                "product_contract_price": product.market_price  # Using market_price as contract_price
            }
            for product in products
        ]
    
    @staticmethod
    def get_all_products(db: Session) -> List[Dict[str, Any]]:
        """Get all products from database - simplified response"""
        products = db.query(Product).all()
        return [
            {
                "product_id": product.id,
                "external_id": product.external_id,
                "product_title": product.title,
                "product_packing": product.packing,
                "product_contract_price": product.market_price  # Using market_price as contract_price
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
            "product_id": product.id,
            "external_id": product.external_id,
            "product_title": product.title,
            "product_packing": product.packing,
            "product_contract_price": product.market_price  # Using market_price as contract_price
        }
    
    @staticmethod
    def search_products(db: Session, query: str) -> List[Dict[str, Any]]:
        """Search products by title - simplified response"""
        products = db.query(Product).filter(
            Product.title.ilike(f"%{query}%") | 
            Product.title_en.ilike(f"%{query}%") |
            Product.barcode.ilike(f"%{query}%")
        ).all()
        
        return [
            {
                "product_id": product.id,
                "external_id": product.external_id,
                "product_title": product.title,
                "product_packing": product.packing,
                "product_contract_price": product.market_price  # Using market_price as contract_price
            }
            for product in products
        ]
    
    @staticmethod
    def get_brand_with_products(db: Session, brand_id: int) -> Optional[Dict[str, Any]]:
        """Get a brand with all its products"""
        brand = db.query(Brand).filter(Brand.id == brand_id).first()
        if not brand:
            return None
        
        products = DataAPIService.get_products_by_brand(db, brand_id)
        
        return {
            "id": brand.id,
            "external_id": brand.external_id,
            "city_id": brand.city_id,
            "title": brand.title,
            "title_en": brand.title_en,
            "image_url": brand.image_url,
            "mounting_rate_image": brand.mounting_rate_image,
            "meta_keywords": brand.meta_keywords,
            "meta_description": brand.meta_description,
            "created_at": brand.created_at.isoformat() if brand.created_at else None,
            "updated_at": brand.updated_at.isoformat() if brand.updated_at else None,
            "products": products
        }
    
    @staticmethod
    def get_city_with_brands_and_products(db: Session, city_id: int) -> Optional[Dict[str, Any]]:
        """Get a city with all its brands and products"""
        city = db.query(City).filter(City.id == city_id).first()
        if not city:
            return None
        
        brands = DatabaseManager.get_brands_by_city(db, city_id)
        brands_with_products = []
        
        for brand in brands:
            products = DataAPIService.get_products_by_brand(db, brand.id)
            brands_with_products.append({
                "id": brand.id,
                "external_id": brand.external_id,
                "title": brand.title,
                "title_en": brand.title_en,
                "image_url": brand.image_url,
                "products": products
            })
        
        return {
            "id": city.id,
            "external_id": city.external_id,
            "name": city.name,
            "name_en": city.name_en,
            "created_at": city.created_at.isoformat() if city.created_at else None,
            "updated_at": city.updated_at.isoformat() if city.updated_at else None,
            "brands": brands_with_products
        }

# Create singleton instance
data_api = DataAPIService() 