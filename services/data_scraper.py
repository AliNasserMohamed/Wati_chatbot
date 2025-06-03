import requests
import asyncio
import aiohttp
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging
from sqlalchemy.orm import Session

from database.db_utils import DatabaseManager, get_db
from database.db_models import City, Brand, Product, DataSyncLog

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataScraperService:
    """Service to scrape data from external APIs and save to database"""
    
    def __init__(self):
        self.base_url = "http://dev.gulfwells.sa/api/admin/ai"
        self.headers = {
            'ApiToken': '4e7f1b2c-3d5a-4b6c-9f7d-8e0f1b2c3d5a',
            'AccessKey': '1234',
            'Lang': 'ar'
        }
        self.headers_no_token = {
            'AccessKey': '1234'
        }
    
    async def fetch_cities(self) -> Dict[str, Any]:
        """Fetch all cities from external API"""
        url = f"{self.base_url}/get-cities"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=self.headers) as response:
                    response.raise_for_status()
                    data = await response.json()
                    return data
            except Exception as e:
                logger.error(f"Error fetching cities: {str(e)}")
                raise
    
    async def fetch_brands_by_city(self, city_id: int) -> Dict[str, Any]:
        """Fetch brands for a specific city"""
        url = f"{self.base_url}/get-location-brands/{city_id}"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=self.headers) as response:
                    response.raise_for_status()
                    data = await response.json()
                    return data
            except Exception as e:
                logger.error(f"Error fetching brands for city {city_id}: {str(e)}")
                raise
    
    async def fetch_products_by_brand(self, brand_id: int) -> Dict[str, Any]:
        """Fetch products for a specific brand"""
        url = f"{self.base_url}/get-brand-products/{brand_id}"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=self.headers) as response:
                    response.raise_for_status()
                    data = await response.json()
                    return data
            except Exception as e:
                logger.error(f"Error fetching products for brand {brand_id}: {str(e)}")
                raise
    
    async def fetch_brand_details(self) -> Dict[str, Any]:
        """Fetch detailed brand information"""
        url = f"{self.base_url}/get-all-brand-details"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=self.headers_no_token) as response:
                    response.raise_for_status()
                    data = await response.json()
                    return data
            except Exception as e:
                logger.error(f"Error fetching brand details: {str(e)}")
                raise
    
    def sync_cities(self, db: Session) -> int:
        """Sync cities data to database"""
        try:
            logger.info("Starting cities sync...")
            sync_log = DatabaseManager.create_sync_log(db, 'cities', 'started')
            
            # This is a synchronous version - in reality you might need to make it async
            # For now, using requests instead of aiohttp for simplicity
            url = f"{self.base_url}/get-cities"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('key') != 'success':
                raise Exception(f"API error: {data.get('msg', 'Unknown error')}")
            
            cities_data = data.get('data', [])
            processed_count = 0
            
            for city_data in cities_data:
                city_id = city_data.get('id')
                city_name = city_data.get('name', city_data.get('city_name', ''))
                city_name_en = city_data.get('name_en', city_data.get('city_name_en', ''))
                
                if city_id and city_name:
                    DatabaseManager.upsert_city(
                        db, 
                        external_id=city_id,
                        name=city_name,
                        name_en=city_name_en
                    )
                    processed_count += 1
            
            # Update sync log
            sync_log.status = 'success'
            sync_log.records_processed = processed_count
            sync_log.completed_at = datetime.utcnow()
            db.commit()
            
            logger.info(f"Cities sync completed. Processed {processed_count} cities.")
            return processed_count
            
        except Exception as e:
            logger.error(f"Cities sync failed: {str(e)}")
            sync_log.status = 'failed'
            sync_log.error_message = str(e)
            sync_log.completed_at = datetime.utcnow()
            db.commit()
            raise
    
    def sync_brands_for_city(self, db: Session, city_external_id: int) -> int:
        """Sync brands for a specific city"""
        try:
            logger.info(f"Starting brands sync for city {city_external_id}...")
            
            url = f"{self.base_url}/get-location-brands/{city_external_id}"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('key') != 'success':
                raise Exception(f"API error: {data.get('msg', 'Unknown error')}")
            
            brands_data = data.get('data', [])
            processed_count = 0
            
            # Get the city from database
            city = db.query(City).filter(City.external_id == city_external_id).first()
            city_id = city.id if city else None
            
            for brand_data in brands_data:
                contract_id = brand_data.get('contract_id')
                brand_title = brand_data.get('brand_title', '')
                brand_image = brand_data.get('brand_image', '')
                
                if contract_id and brand_title:
                    DatabaseManager.upsert_brand(
                        db,
                        external_id=contract_id,
                        title=brand_title,
                        image_url=brand_image,
                        city_id=city_id
                    )
                    processed_count += 1
            
            logger.info(f"Brands sync completed for city {city_external_id}. Processed {processed_count} brands.")
            return processed_count
            
        except Exception as e:
            logger.error(f"Brands sync failed for city {city_external_id}: {str(e)}")
            raise
    
    def sync_all_brands(self, db: Session) -> int:
        """Sync brands for all cities"""
        try:
            logger.info("Starting full brands sync...")
            sync_log = DatabaseManager.create_sync_log(db, 'brands', 'started')
            
            cities = DatabaseManager.get_all_cities(db)
            total_processed = 0
            
            for city in cities:
                try:
                    count = self.sync_brands_for_city(db, city.external_id)
                    total_processed += count
                except Exception as e:
                    logger.error(f"Failed to sync brands for city {city.external_id}: {str(e)}")
                    continue
            
            # Update sync log
            sync_log.status = 'success'
            sync_log.records_processed = total_processed
            sync_log.completed_at = datetime.utcnow()
            db.commit()
            
            logger.info(f"Full brands sync completed. Processed {total_processed} brands.")
            return total_processed
            
        except Exception as e:
            logger.error(f"Full brands sync failed: {str(e)}")
            sync_log.status = 'failed'
            sync_log.error_message = str(e)
            sync_log.completed_at = datetime.utcnow()
            db.commit()
            raise
    
    def sync_brand_details(self, db: Session) -> int:
        """Sync detailed brand information with products"""
        try:
            logger.info("Starting brand details sync...")
            sync_log = DatabaseManager.create_sync_log(db, 'brand_details', 'started')
            
            url = f"{self.base_url}/get-all-brand-details"
            response = requests.get(url, headers=self.headers_no_token)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('key') != 'success':
                raise Exception(f"API error: {data.get('msg', 'Unknown error')}")
            
            brands_data = data.get('data', [])
            processed_brands = 0
            processed_products = 0
            
            for brand_data in brands_data:
                brand_id = brand_data.get('brand_id')
                brand_title = brand_data.get('brand_title', '')
                brand_image = brand_data.get('brand_image', '')
                mounting_rate_image = brand_data.get('brand_mounting_rate_image', '')
                meta_keywords = brand_data.get('brand_meta_keywords', '')
                meta_description = brand_data.get('brand_meta_description', '')
                
                if brand_id and brand_title:
                    # Update or create brand with additional details
                    brand = DatabaseManager.upsert_brand(
                        db,
                        external_id=brand_id,
                        title=brand_title,
                        image_url=brand_image,
                        mounting_rate_image=mounting_rate_image,
                        meta_keywords=meta_keywords,
                        meta_description=meta_description
                    )
                    processed_brands += 1
                    
                    # Process products for this brand
                    products_data = brand_data.get('products', [])
                    for product_data in products_data:
                        product_id = product_data.get('product_id')
                        product_title = product_data.get('product_title', '')
                        
                        if product_id and product_title:
                            DatabaseManager.upsert_product(
                                db,
                                external_id=product_id,
                                brand_id=brand.id,
                                title=product_title,
                                packing=product_data.get('product_packing', ''),
                                market_price=product_data.get('product_market_price', 0),
                                barcode=product_data.get('product_barcode', ''),
                                image_url=product_data.get('product_image', ''),
                                meta_keywords_ar=product_data.get('meta_keywords_ar'),
                                meta_keywords_en=product_data.get('meta_keywords_en'),
                                meta_description_ar=product_data.get('meta_description_ar'),
                                meta_description_en=product_data.get('meta_description_en'),
                                description_rich_text_ar=product_data.get('description_rich_text_ar'),
                                description_rich_text_en=product_data.get('description_rich_text_en')
                            )
                            processed_products += 1
            
            # Update sync log
            sync_log.status = 'success'
            sync_log.records_processed = processed_brands + processed_products
            sync_log.completed_at = datetime.utcnow()
            db.commit()
            
            logger.info(f"Brand details sync completed. Processed {processed_brands} brands and {processed_products} products.")
            return processed_brands + processed_products
            
        except Exception as e:
            logger.error(f"Brand details sync failed: {str(e)}")
            sync_log.status = 'failed'
            sync_log.error_message = str(e)
            sync_log.completed_at = datetime.utcnow()
            db.commit()
            raise
    
    def full_sync(self, db: Session) -> Dict[str, int]:
        """Perform a full sync of all data"""
        try:
            logger.info("Starting full data sync...")
            
            results = {}
            
            # Step 1: Sync cities
            results['cities'] = self.sync_cities(db)
            
            # Step 2: Sync brands for all cities
            results['brands'] = self.sync_all_brands(db)
            
            # Step 3: Sync brand details and products
            results['brand_details_and_products'] = self.sync_brand_details(db)
            
            logger.info(f"Full sync completed: {results}")
            return results
            
        except Exception as e:
            logger.error(f"Full sync failed: {str(e)}")
            raise

# Create singleton instance
data_scraper = DataScraperService() 