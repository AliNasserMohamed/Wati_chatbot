from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException

from database.db_utils import DatabaseManager
from database.db_models import City, Brand, Product

class DataAPIService:
    """Internal API service to fetch data from the database"""
    
    @staticmethod
    def get_all_cities(db: Session) -> List[Dict[str, Any]]:
        """Get all cities from database"""
        cities = DatabaseManager.get_all_cities(db)
        return [
            {
                "id": city.id,
                "external_id": city.external_id,
                "name": city.name,
                "name_en": city.name_en,
                "created_at": city.created_at.isoformat() if city.created_at else None,
                "updated_at": city.updated_at.isoformat() if city.updated_at else None
            }
            for city in cities
        ]
    
    @staticmethod
    def get_city_by_id(db: Session, city_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific city by ID"""
        city = db.query(City).filter(City.id == city_id).first()
        if not city:
            return None
        
        return {
            "id": city.id,
            "external_id": city.external_id,
            "name": city.name,
            "name_en": city.name_en,
            "created_at": city.created_at.isoformat() if city.created_at else None,
            "updated_at": city.updated_at.isoformat() if city.updated_at else None
        }
    
    @staticmethod
    def search_cities(db: Session, query: str) -> List[Dict[str, Any]]:
        """Search cities by name"""
        cities = db.query(City).filter(
            City.name.ilike(f"%{query}%") | 
            City.name_en.ilike(f"%{query}%")
        ).all()
        
        return [
            {
                "id": city.id,
                "external_id": city.external_id,
                "name": city.name,
                "name_en": city.name_en,
                "created_at": city.created_at.isoformat() if city.created_at else None,
                "updated_at": city.updated_at.isoformat() if city.updated_at else None
            }
            for city in cities
        ]
    
    @staticmethod
    def get_brands_by_city(db: Session, city_id: int) -> List[Dict[str, Any]]:
        """Get all brands for a specific city"""
        brands = DatabaseManager.get_brands_by_city(db, city_id)
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
    def get_all_brands(db: Session) -> List[Dict[str, Any]]:
        """Get all brands from database"""
        brands = db.query(Brand).all()
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
        """Get all products for a specific brand"""
        products = DatabaseManager.get_products_by_brand(db, brand_id)
        return [
            {
                "id": product.id,
                "external_id": product.external_id,
                "brand_id": product.brand_id,
                "title": product.title,
                "title_en": product.title_en,
                "packing": product.packing,
                "market_price": product.market_price,
                "barcode": product.barcode,
                "image_url": product.image_url,
                "meta_keywords_ar": product.meta_keywords_ar,
                "meta_keywords_en": product.meta_keywords_en,
                "meta_description_ar": product.meta_description_ar,
                "meta_description_en": product.meta_description_en,
                "description_rich_text_ar": product.description_rich_text_ar,
                "description_rich_text_en": product.description_rich_text_en,
                "created_at": product.created_at.isoformat() if product.created_at else None,
                "updated_at": product.updated_at.isoformat() if product.updated_at else None
            }
            for product in products
        ]
    
    @staticmethod
    def get_all_products(db: Session) -> List[Dict[str, Any]]:
        """Get all products from database"""
        products = db.query(Product).all()
        return [
            {
                "id": product.id,
                "external_id": product.external_id,
                "brand_id": product.brand_id,
                "title": product.title,
                "title_en": product.title_en,
                "packing": product.packing,
                "market_price": product.market_price,
                "barcode": product.barcode,
                "image_url": product.image_url,
                "meta_keywords_ar": product.meta_keywords_ar,
                "meta_keywords_en": product.meta_keywords_en,
                "meta_description_ar": product.meta_description_ar,
                "meta_description_en": product.meta_description_en,
                "description_rich_text_ar": product.description_rich_text_ar,
                "description_rich_text_en": product.description_rich_text_en,
                "created_at": product.created_at.isoformat() if product.created_at else None,
                "updated_at": product.updated_at.isoformat() if product.updated_at else None
            }
            for product in products
        ]
    
    @staticmethod
    def get_product_by_id(db: Session, product_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific product by ID"""
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            return None
        
        return {
            "id": product.id,
            "external_id": product.external_id,
            "brand_id": product.brand_id,
            "title": product.title,
            "title_en": product.title_en,
            "packing": product.packing,
            "market_price": product.market_price,
            "barcode": product.barcode,
            "image_url": product.image_url,
            "meta_keywords_ar": product.meta_keywords_ar,
            "meta_keywords_en": product.meta_keywords_en,
            "meta_description_ar": product.meta_description_ar,
            "meta_description_en": product.meta_description_en,
            "description_rich_text_ar": product.description_rich_text_ar,
            "description_rich_text_en": product.description_rich_text_en,
            "created_at": product.created_at.isoformat() if product.created_at else None,
            "updated_at": product.updated_at.isoformat() if product.updated_at else None
        }
    
    @staticmethod
    def search_products(db: Session, query: str) -> List[Dict[str, Any]]:
        """Search products by title"""
        products = db.query(Product).filter(
            Product.title.ilike(f"%{query}%") | 
            Product.title_en.ilike(f"%{query}%") |
            Product.barcode.ilike(f"%{query}%")
        ).all()
        
        return [
            {
                "id": product.id,
                "external_id": product.external_id,
                "brand_id": product.brand_id,
                "title": product.title,
                "title_en": product.title_en,
                "packing": product.packing,
                "market_price": product.market_price,
                "barcode": product.barcode,
                "image_url": product.image_url,
                "meta_keywords_ar": product.meta_keywords_ar,
                "meta_keywords_en": product.meta_keywords_en,
                "meta_description_ar": product.meta_description_ar,
                "meta_description_en": product.meta_description_en,
                "description_rich_text_ar": product.description_rich_text_ar,
                "description_rich_text_en": product.description_rich_text_en,
                "created_at": product.created_at.isoformat() if product.created_at else None,
                "updated_at": product.updated_at.isoformat() if product.updated_at else None
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