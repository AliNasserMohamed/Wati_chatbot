import requests
import asyncio
import aiohttp
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging
import random
from sqlalchemy.orm import Session
from sqlalchemy import text

from database.db_utils import DatabaseManager, get_db
from database.db_models import City, Brand, Product, DataSyncLog

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataScraperService:
    """Service to scrape data from external APIs and save to database with ID consistency"""
    
    def __init__(self):
        self.base_url = "https://gulfwells.sa/api/admin/ai"
        self.headers_ar = {
            'AccessKey': '4e7f1b2c-3d5a-4b6c-9f7d-8e0f1b2c3d5a',
            'Lang': 'ar'
        }
        self.headers_en = {
            'AccessKey': '4e7f1b2c-3d5a-4b6c-9f7d-8e0f1b2c3d5a',
            'Lang': 'en'
        }
        
        # Cities to exclude from scraping (specific Riyadh regions)
        self.excluded_city_ids = {6, 7, 8, 9}  # شمال، جنوب، غرب، شرق الرياض
    
    def _clean_and_normalize_brand_name(self, brand_name: str) -> str:
        """
        Clean and normalize brand names during scraping:
        1. Remove Arabic water prefixes ('مياه', 'موية', 'مياة', 'ميه')
        2. Remove English water prefixes/suffixes ('Water', 'WATER', 'water')
        3. Apply Arabic text normalization
        """
        from database.district_utils import DistrictLookup
        
        if not brand_name or not brand_name.strip():
            return brand_name
            
        cleaned_name = brand_name.strip()
        
        # STEP 1: Remove Arabic water prefixes
        arabic_water_prefixes = ["مياه", "موية", "مياة", "ميه"]
        for prefix in arabic_water_prefixes:
            # Check if brand name starts with the prefix followed by space
            if cleaned_name.startswith(prefix + " "):
                cleaned_name = cleaned_name[len(prefix):].strip()
                break
            # Check if brand name starts with the prefix without space
            elif cleaned_name.startswith(prefix) and len(cleaned_name) > len(prefix):
                # Make sure it's actually a prefix, not part of the brand name
                next_char_idx = len(prefix)
                if next_char_idx < len(cleaned_name) and cleaned_name[next_char_idx] in [' ', '\u0020']:
                    cleaned_name = cleaned_name[next_char_idx:].strip()
                    break
        
        # STEP 2: Remove English water prefixes and suffixes
        english_water_words = ["Water", "WATER", "water"]
        
        for water_word in english_water_words:
            # Remove as prefix: "Water Brand" -> "Brand"
            if cleaned_name.startswith(water_word + " "):
                cleaned_name = cleaned_name[len(water_word):].strip()
                break
            # Remove as suffix: "Brand Water" -> "Brand"  
            elif cleaned_name.endswith(" " + water_word):
                cleaned_name = cleaned_name[:-len(water_word)].strip()
                break
            # Handle cases where Water is the whole word after/before spaces
            elif " " + water_word + " " in cleaned_name:
                # Replace middle occurrence: "Brand Water Company" -> "Brand Company"
                cleaned_name = cleaned_name.replace(" " + water_word + " ", " ").strip()
                break
        
        # STEP 3: Apply normalization
        normalized_name = DistrictLookup.normalize_city_name(cleaned_name)
        
        return normalized_name
    
    def _normalize_scraped_name(self, name: str) -> str:
        """
        Normalize city/brand names during scraping using our normalization function
        """
        from database.district_utils import DistrictLookup
        
        if not name or not name.strip():
            return name
            
        return DistrictLookup.normalize_city_name(name)
    
    async def make_api_request_with_retry(
        self, 
        session: aiohttp.ClientSession, 
        url: str, 
        headers: dict, 
        max_retries: int = 3, 
        base_delay: float = 1.0,
        backoff_factor: float = 2.0,
        jitter: bool = True
    ) -> Dict[str, Any]:
        """
        Make an API request with exponential backoff retry logic
        
        Args:
            session: aiohttp session
            url: URL to request
            headers: Request headers
            max_retries: Maximum number of retry attempts
            base_delay: Base delay in seconds
            backoff_factor: Exponential backoff multiplier
            jitter: Add random jitter to prevent thundering herd
        """
        for attempt in range(max_retries + 1):  # +1 because first attempt is not a retry
            try:
                # Add delay before request (except first attempt)
                if attempt > 0:
                    delay = base_delay * (backoff_factor ** (attempt - 1))
                    if jitter:
                        delay *= (0.5 + random.random())  # Add 50-150% jitter
                    logger.info(f"🔄 Retrying request (attempt {attempt + 1}/{max_retries + 1}) after {delay:.2f}s delay")
                    await asyncio.sleep(delay)
                else:
                    # Small delay even on first attempt to be respectful to API
                    await asyncio.sleep(0.5)
                
                async with session.get(url, headers=headers) as response:
                    response.raise_for_status()
                    data = await response.json()
                    
                    # Log successful request
                    if attempt > 0:
                        logger.info(f"✅ Request succeeded after {attempt + 1} attempts")
                    
                    return data
                    
            except aiohttp.ClientResponseError as e:
                error_msg = f"HTTP {e.status} error: {e.message}"
                
                # Check if this is a retryable error
                is_retryable = e.status in [429, 502, 503, 504] or (500 <= e.status < 600)
                
                if e.status == 400:
                    logger.error(f"❌ 400 Bad Request (not retryable): {url}")
                    logger.error(f"   Headers: {headers}")
                    # 400 errors are client errors - don't retry
                    raise
                elif e.status == 404:
                    logger.warning(f"⚠️ 404 Not Found: {url}")
                    # 404 might mean the resource doesn't exist - don't retry
                    raise
                elif not is_retryable:
                    logger.error(f"❌ Non-retryable error {e.status}: {url}")
                    raise
                
                if attempt == max_retries:  # Last attempt
                    logger.error(f"💥 Request failed after {max_retries + 1} attempts: {error_msg}")
                    raise
                else:
                    logger.warning(f"⚠️ Retryable error (attempt {attempt + 1}): {error_msg}")
                    
            except Exception as e:
                if attempt == max_retries:  # Last attempt
                    logger.error(f"💥 Request failed after {max_retries + 1} attempts: {str(e)}")
                    raise
                else:
                    logger.warning(f"⚠️ Unexpected error (attempt {attempt + 1}): {str(e)}")
        
        # This should never be reached
        raise Exception("Unexpected end of retry loop")
    
    async def make_product_api_request_with_retry(
        self, 
        session: aiohttp.ClientSession, 
        url: str, 
        headers: dict, 
        brand_id: int,
        language: str = 'ar',
        max_retries: int = 3, 
        base_delay: float = 1.0,
        backoff_factor: float = 2.0,
        jitter: bool = True
    ) -> Dict[str, Any]:
        """
        Make a product API request with retry logic that retries even 400 Bad Request errors
        
        Args:
            session: aiohttp session
            url: URL to request
            headers: Request headers
            brand_id: Brand ID for logging purposes
            language: Language for logging (ar/en)
            max_retries: Maximum number of retry attempts
            base_delay: Base delay in seconds
            backoff_factor: Exponential backoff multiplier
            jitter: Add random jitter to prevent thundering herd
        """
        for attempt in range(max_retries + 1):  # +1 because first attempt is not a retry
            try:
                # Add delay before request (except first attempt)
                if attempt > 0:
                    delay = base_delay * (backoff_factor ** (attempt - 1))
                    if jitter:
                        delay *= (0.5 + random.random())  # Add 50-150% jitter
                    logger.info(f"🔄 Retrying product request for brand {brand_id} ({language}) - attempt {attempt + 1}/{max_retries + 1} after {delay:.2f}s delay")
                    await asyncio.sleep(delay)
                else:
                    # Small delay even on first attempt to be respectful to API
                    await asyncio.sleep(0.5)
                    logger.info(f"📡 Making product API request for brand {brand_id} ({language}) - attempt {attempt + 1}")
                
                async with session.get(url, headers=headers) as response:
                    response.raise_for_status()
                    data = await response.json()
                    
                    # Log successful request
                    if attempt > 0:
                        logger.info(f"✅ Product request for brand {brand_id} ({language}) succeeded after {attempt + 1} attempts")
                    else:
                        logger.info(f"✅ Product request for brand {brand_id} ({language}) succeeded on first attempt")
                    
                    return data
                    
            except aiohttp.ClientResponseError as e:
                error_msg = f"HTTP {e.status} error: {e.message}"
                
                if e.status == 400:
                    logger.warning(f"⚠️ 400 Bad Request for brand {brand_id} ({language}) - attempt {attempt + 1}: {url}")
                    logger.warning(f"   Headers: {headers}")
                    if attempt == max_retries:  # Last attempt
                        logger.error(f"💥 Product request for brand {brand_id} ({language}) failed after {max_retries + 1} attempts with 400 Bad Request")
                        raise
                    else:
                        logger.info(f"🔄 Will retry 400 Bad Request for brand {brand_id} ({language}) - {max_retries - attempt} attempts remaining")
                elif e.status == 404:
                    logger.warning(f"⚠️ 404 Not Found for brand {brand_id} ({language}): {url}")
                    if attempt == max_retries:  # Last attempt
                        logger.error(f"💥 Product request for brand {brand_id} ({language}) failed after {max_retries + 1} attempts with 404 Not Found")
                        raise
                    else:
                        logger.info(f"🔄 Will retry 404 Not Found for brand {brand_id} ({language}) - {max_retries - attempt} attempts remaining")
                else:
                    # All other HTTP errors
                    if attempt == max_retries:  # Last attempt
                        logger.error(f"💥 Product request for brand {brand_id} ({language}) failed after {max_retries + 1} attempts: {error_msg}")
                        raise
                    else:
                        logger.warning(f"⚠️ HTTP error for brand {brand_id} ({language}) attempt {attempt + 1}: {error_msg}")
                        logger.info(f"🔄 Will retry HTTP error for brand {brand_id} ({language}) - {max_retries - attempt} attempts remaining")
                    
            except Exception as e:
                if attempt == max_retries:  # Last attempt
                    logger.error(f"💥 Product request for brand {brand_id} ({language}) failed after {max_retries + 1} attempts: {str(e)}")
                    raise
                else:
                    logger.warning(f"⚠️ Unexpected error for brand {brand_id} ({language}) attempt {attempt + 1}: {str(e)}")
                    logger.info(f"🔄 Will retry unexpected error for brand {brand_id} ({language}) - {max_retries - attempt} attempts remaining")
        
        # This should never be reached
        raise Exception("Unexpected end of retry loop")
    
    async def fetch_cities_arabic(self) -> Dict[str, Any]:
        """Fetch all cities from external API in Arabic"""
        url = f"{self.base_url}/get-cities"
        
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=self.headers_ar) as response:
                    response.raise_for_status()
                    return await response.json()
        except Exception as e:
            logger.error(f"Error fetching cities (Arabic): {str(e)}")
            raise
    
    async def fetch_cities_english(self) -> Dict[str, Any]:
        """Fetch all cities from external API in English"""
        url = f"{self.base_url}/get-cities"
        
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=self.headers_en) as response:
                    response.raise_for_status()
                    return await response.json()
        except Exception as e:
            logger.error(f"Error fetching cities (English): {str(e)}")
            raise

    async def fetch_brands_by_city(self, city_id: int, language: str = 'ar') -> Dict[str, Any]:
        """Fetch brands for a specific city in specified language"""
        url = f"{self.base_url}/get-location-brands/{city_id}"
        headers = self.headers_ar if language == 'ar' else self.headers_en
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as response:
                    response.raise_for_status()
                    data = await response.json()
                    return data
            except Exception as e:
                logger.error(f"Error fetching brands for city {city_id} in {language}: {str(e)}")
                raise
    
    async def fetch_brands_by_city_arabic(self, city_id: int) -> Dict[str, Any]:
        """Fetch brands for a specific city in Arabic"""
        return await self.fetch_brands_by_city(city_id, 'ar')
    
    async def fetch_brands_by_city_english(self, city_id: int) -> Dict[str, Any]:
        """Fetch brands for a specific city in English"""
        return await self.fetch_brands_by_city(city_id, 'en')
    
    async def fetch_products_by_brand(self, brand_id: int, language: str = 'ar') -> Dict[str, Any]:
        """Fetch products for a specific brand in specified language"""
        url = f"{self.base_url}/get-brand-products/{brand_id}"
        headers = self.headers_ar if language == 'ar' else self.headers_en
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as response:
                    response.raise_for_status()
                    data = await response.json()
                    return data
            except Exception as e:
                logger.error(f"Error fetching products for brand {brand_id} in {language}: {str(e)}")
                raise
    
    async def fetch_products_by_brand_arabic(self, brand_id: int) -> Dict[str, Any]:
        """Fetch products for a specific brand in Arabic"""
        return await self.fetch_products_by_brand(brand_id, 'ar')
    
    async def fetch_products_by_brand_english(self, brand_id: int) -> Dict[str, Any]:
        """Fetch products for a specific brand in English"""
        return await self.fetch_products_by_brand(brand_id, 'en')

    async def brand_has_products(self, session: aiohttp.ClientSession, brand_id: int, max_retries: int = 3) -> bool:
        """
        Check if a brand has any products with retry logic
        NOTE: Currently not used in scraping process (disabled for performance)
        Kept for potential future use or manual verification
        """
        url = f"{self.base_url}/get-brand-products/{brand_id}"
        
        for attempt in range(max_retries):
            try:
                # Add a small delay before each request to avoid overwhelming the server
                if attempt > 0:
                    logger.info(f"🔄 Retrying brand {brand_id} check (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(5)  # Wait 5 seconds before retry
                else:
                    await asyncio.sleep(0.5)  # Small delay for first attempt
                
                async with session.get(url, headers=self.headers_ar) as response:
                    response.raise_for_status()
                    data = await response.json()
                    
                    if data.get('key') == 'success':
                        # Products are inside data.products for the get-brand-products endpoint
                        brand_data = data.get('data', {})
                        products = brand_data.get('products', [])
                        has_products = len(products) > 0
                        logger.info(f"✅ Brand {brand_id} check successful: {'has products' if has_products else 'no products'}")
                        return has_products
                    else:
                        logger.warning(f"⚠️ API returned non-success for brand {brand_id}: {data.get('msg', 'Unknown error')}")
                        return False
                        
            except aiohttp.ClientResponseError as e:
                logger.error(f"❌ HTTP error checking products for brand {brand_id} (attempt {attempt + 1}): {e.status}, message='{e.message}', url='{e.request_info.url}'")
                if attempt == max_retries - 1:  # Last attempt
                    logger.error(f"💥 Failed to check brand {brand_id} after {max_retries} attempts")
                    return False
                # Continue to next attempt with delay
                
            except Exception as e:
                logger.error(f"❌ Unexpected error checking products for brand {brand_id} (attempt {attempt + 1}): {str(e)}")
                if attempt == max_retries - 1:  # Last attempt
                    logger.error(f"💥 Failed to check brand {brand_id} after {max_retries} attempts")
                    return False
                # Continue to next attempt with delay
        
        return False
    
    async def fetch_brand_details(self) -> Dict[str, Any]:
        """Fetch detailed brand information"""
        url = f"{self.base_url}/get-all-brand-details"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=self.headers_ar) as response:
                    response.raise_for_status()
                    data = await response.json()
                    return data
            except Exception as e:
                logger.error(f"Error fetching brand details: {str(e)}")
                raise
    
    async def clean_slate_sync_cities(self, db: Session) -> int:
        """CLEAN SLATE: Delete all cities and sync fresh data with external IDs as primary keys"""
        try:
            logger.info("🗑️ Starting CLEAN SLATE cities sync...")
            sync_log = DatabaseManager.create_sync_log(db, 'cities', 'started')
            
            # STEP 1: DELETE ALL EXISTING DATA
            logger.info("🧹 Deleting all existing cities...")
            db.query(City).delete()
            db.commit()
            logger.info("✅ All existing cities deleted")
            
            # STEP 2: FETCH FRESH DATA
            # Fetch Arabic cities
            logger.info("📥 Fetching cities in Arabic...")
            arabic_data = await self.fetch_cities_arabic()
            
            if arabic_data.get('key') != 'success':
                raise Exception(f"API error (Arabic): {arabic_data.get('msg', 'Unknown error')}")
            
            # Fetch English cities
            logger.info("📥 Fetching cities in English...")
            english_data = await self.fetch_cities_english()
            
            if english_data.get('key') != 'success':
                raise Exception(f"API error (English): {english_data.get('msg', 'Unknown error')}")
            
            # STEP 3: CREATE LOOKUP FOR ENGLISH NAMES
            english_cities = {city['id']: city['title'] for city in english_data.get('data', [])}
            
            # STEP 4: INSERT FRESH DATA WITH EXTERNAL ID AS PRIMARY KEY
            cities_data = arabic_data.get('data', [])
            processed_count = 0
            
            for city_data in cities_data:
                external_city_id = city_data.get('id')
                city_title_ar = city_data.get('title', '')
                city_title_en = english_cities.get(external_city_id, '')
                city_lat = city_data.get('lat')
                city_lng = city_data.get('lng')
                
                # Skip excluded Riyadh region cities
                if external_city_id in self.excluded_city_ids:
                    logger.info(f"⏭️ Skipping excluded city: ID={external_city_id}, {city_title_ar}")
                    continue
                
                if external_city_id and city_title_ar:
                    # NORMALIZE city names during scraping
                    normalized_city_ar = self._normalize_scraped_name(city_title_ar)
                    normalized_city_en = self._normalize_scraped_name(city_title_en) if city_title_en else city_title_en
                    
                    logger.info(f"📝 City normalization: '{city_title_ar}' -> '{normalized_city_ar}'")
                    
                    # Create city with external ID as the primary key
                    city = City(
                        id=external_city_id,  # Use external ID as primary key
                        external_id=external_city_id,  # Keep external_id for compatibility
                        name=normalized_city_ar,  # Normalized Arabic name
                        name_en=normalized_city_en,  # Normalized English name
                        title=normalized_city_ar,  # Alternative title field
                        lat=city_lat,
                        lng=city_lng
                    )
                    db.add(city)
                    processed_count += 1
                    logger.info(f"✅ Created city: ID={external_city_id}, {normalized_city_ar} ({normalized_city_en})")
            
            db.commit()
            
            # Update sync log
            sync_log.status = 'success'
            sync_log.records_processed = processed_count
            sync_log.completed_at = datetime.utcnow()
            db.commit()
            
            logger.info(f"🎉 Clean slate cities sync completed. Processed {processed_count} cities.")
            return processed_count
            
        except Exception as e:
            logger.error(f"❌ Cities sync failed: {str(e)}")
            sync_log.status = 'failed'
            sync_log.error_message = str(e)
            sync_log.completed_at = datetime.utcnow()
            db.commit()
            raise
    
    async def clean_slate_sync_brands(self, db: Session) -> int:
        """CLEAN SLATE: Delete all brands and sync fresh data with external IDs as primary keys"""
        try:
            logger.info("🗑️ Starting CLEAN SLATE brands sync...")
            sync_log = DatabaseManager.create_sync_log(db, 'brands', 'started')
            
            # STEP 1: DELETE ALL EXISTING BRANDS DATA
            logger.info("🧹 Deleting all existing brands...")
            # First delete city-brand relationships
            db.execute(text("DELETE FROM city_brands"))
            db.commit()
            # Then delete brands
            db.query(Brand).delete()
            db.commit()
            logger.info("✅ All existing brands and relationships deleted")
            
            # STEP 2: GET ALL CITIES TO SYNC BRANDS FOR
            cities = db.query(City).all()
            logger.info(f"📋 Found {len(cities)} cities to sync brands for")
            
            processed_count = 0
            all_brands = {}
            city_brand_relationships = []
            
            # STEP 3: SYNC BRANDS FOR EACH CITY (WITH DUAL-LANGUAGE SUPPORT)
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for city in cities:
                    logger.info(f"🏙️ Syncing brands for city: {city.name} (ID: {city.id})")
                    
                    try:
                        # FETCH ARABIC BRANDS DATA
                        url = f"{self.base_url}/get-location-brands/{city.id}"
                        async with session.get(url, headers=self.headers_ar) as response:
                            response.raise_for_status()
                            arabic_data = await response.json()
                        
                        if arabic_data.get('key') != 'success':
                            logger.warning(f"⚠️ API error (Arabic) for city {city.id}: {arabic_data.get('msg', 'Unknown error')}")
                            continue
                        
                        # FETCH ENGLISH BRANDS DATA
                        async with session.get(url, headers=self.headers_en) as response:
                            response.raise_for_status()
                            english_data = await response.json()
                        
                        if english_data.get('key') != 'success':
                            logger.warning(f"⚠️ API error (English) for city {city.id}: {english_data.get('msg', 'Unknown error')}")
                            # Continue with Arabic data only if English fails
                            english_data = {'data': []}
                        
                        # CREATE LOOKUP FOR ENGLISH BRAND NAMES
                        english_brands = {}
                        for brand_data in english_data.get('data', []):
                            contract_id = brand_data.get('contract_id')
                            brand_title_en = brand_data.get('brand_title', '')
                            if contract_id and brand_title_en:
                                english_brands[contract_id] = brand_title_en
                        
                        brands_data = arabic_data.get('data', [])
                        logger.info(f"📦 Found {len(brands_data)} brands for {city.name} (Arabic: {len(brands_data)}, English: {len(english_brands)})")
                        
                        for brand_data in brands_data:
                            contract_id = brand_data.get('contract_id')
                            brand_title_ar = brand_data.get('brand_title', '')
                            brand_title_en = english_brands.get(contract_id, '')
                            brand_image = brand_data.get('brand_image', '')
                            
                            if contract_id and brand_title_ar:
                                # DISABLED: Check if brand has products before saving
                                # This speeds up scraping by not pre-checking products for each brand
                                # Brands will be saved regardless of whether they have products
                                # logger.info(f"🔍 Checking if brand {contract_id} ({brand_title_ar}) has products...")
                                # has_products = await self.brand_has_products(session, contract_id)
                                # 
                                # if not has_products:
                                #     logger.info(f"⏭️ Skipping brand without products: ID={contract_id}, {brand_title_ar}")
                                #     continue
                                
                                # Add delay between processing different brands to avoid overwhelming the server
                                await asyncio.sleep(1)
                                
                                # CLEAN and NORMALIZE brand titles during scraping
                                cleaned_brand_title_ar = self._clean_and_normalize_brand_name(brand_title_ar)
                                cleaned_brand_title_en = self._clean_and_normalize_brand_name(brand_title_en) if brand_title_en else ''
                                logger.info(f"📝 Brand cleaning: AR: '{brand_title_ar}' -> '{cleaned_brand_title_ar}', EN: '{brand_title_en}' -> '{cleaned_brand_title_en}'")
                                
                                # Create brand with external ID as primary key (if not exists)
                                if contract_id not in all_brands:
                                    brand = Brand(
                                        id=contract_id,  # Use external ID as primary key
                                        external_id=contract_id,  # Keep for compatibility
                                        title=cleaned_brand_title_ar,  # Arabic title (cleaned and normalized)
                                        title_en=cleaned_brand_title_en,  # English title (cleaned and normalized)
                                        image_url=brand_image
                                    )
                                    db.add(brand)
                                    all_brands[contract_id] = brand
                                    logger.info(f"✅ Created brand: ID={contract_id}, AR: '{cleaned_brand_title_ar}', EN: '{cleaned_brand_title_en}'")
                                
                                # Store city-brand relationship for bulk insert
                                relationship = (city.id, contract_id)
                                if relationship not in city_brand_relationships:
                                    city_brand_relationships.append(relationship)
                                
                                processed_count += 1
                    
                    except Exception as e:
                        logger.error(f"❌ Error syncing brands for city {city.id}: {str(e)}")
                        continue
                    
                    # Add delay between processing different cities to avoid overwhelming the server
                    await asyncio.sleep(2)
            
            # Commit brands first
            db.commit()
            logger.info(f"✅ Committed {len(all_brands)} brands to database")
            
            # STEP 4: BULK INSERT CITY-BRAND RELATIONSHIPS
            if city_brand_relationships:
                logger.info(f"🔗 Inserting {len(city_brand_relationships)} city-brand relationships...")
                
                # Use bulk insert for better performance
                insert_stmt = text("""
                    INSERT INTO city_brands (city_id, brand_id) 
                    VALUES (:city_id, :brand_id)
                """)
                
                relationship_data = [
                    {"city_id": city_id, "brand_id": brand_id}
                    for city_id, brand_id in city_brand_relationships
                ]
                
                db.execute(insert_stmt, relationship_data)
                db.commit()
                logger.info(f"✅ Inserted {len(city_brand_relationships)} city-brand relationships")
            
            DatabaseManager.create_sync_log(db, 'brands', 'completed', processed_count)
            
            logger.info(f"🎉 CLEAN SLATE brands sync completed!")
            logger.info(f"📊 Total processed: {processed_count}")
            logger.info(f"📊 Total brands: {len(all_brands)}")
            logger.info(f"📊 Total relationships: {len(city_brand_relationships)}")
            
            return processed_count
            
        except Exception as e:
            logger.error(f"❌ CLEAN SLATE brands sync failed: {str(e)}")
            DatabaseManager.create_sync_log(db, 'brands', 'failed', 0, str(e))
            raise
    
    async def clean_slate_sync_products(self, db: Session) -> int:
        """CLEAN SLATE: Delete all products and sync fresh data with external IDs as primary keys"""
        try:
            logger.info("🗑️ Starting CLEAN SLATE products sync...")
            sync_log = DatabaseManager.create_sync_log(db, 'products', 'started')
            
            # STEP 1: DELETE ALL EXISTING PRODUCTS DATA
            logger.info("🧹 Deleting all existing products...")
            db.query(Product).delete()
            db.commit()
            logger.info("✅ All existing products deleted")
            
            # STEP 2: GET ALL BRANDS TO SYNC PRODUCTS FOR
            brands = db.query(Brand).all()
            logger.info(f"📋 Found {len(brands)} brands to sync products for")
            
            processed_count = 0
            skipped_count = 0
            
            # STEP 3: SYNC PRODUCTS FOR EACH BRAND
            for brand in brands:
                logger.info(f"🏷️ Syncing products for brand: {brand.title} (ID: {brand.id})")
                
                try:
                    url = f"{self.base_url}/get-brand-products/{brand.id}"
                    timeout = aiohttp.ClientTimeout(total=30)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        # FETCH ARABIC PRODUCTS DATA with retry logic (including 400 errors)
                        try:
                            arabic_data = await self.make_product_api_request_with_retry(
                                session, url, self.headers_ar, brand.id, 'ar', max_retries=3, base_delay=1.0
                            )
                        except Exception as e:
                            logger.error(f"❌ Failed to fetch Arabic products for brand {brand.id} after 3 retries: {str(e)}")
                            continue
                        
                        if arabic_data.get('key') != 'success':
                            logger.warning(f"⚠️ API error (Arabic) for brand {brand.id}: {arabic_data.get('msg', 'Unknown error')}")
                            continue
                        
                        # Add delay between Arabic and English requests
                        await asyncio.sleep(0.5)
                        
                        # FETCH ENGLISH PRODUCTS DATA with retry logic (including 400 errors)
                        try:
                            english_data = await self.make_product_api_request_with_retry(
                                session, url, self.headers_en, brand.id, 'en', max_retries=3, base_delay=1.0
                            )
                        except Exception as e:
                            logger.warning(f"⚠️ Failed to fetch English products for brand {brand.id} after 3 retries: {str(e)}")
                            # Continue with Arabic data only if English fails
                            english_data = {'data': {'products': []}}
                        
                        if english_data.get('key') != 'success' and 'data' not in english_data:
                            logger.warning(f"⚠️ API error (English) for brand {brand.id}: {english_data.get('msg', 'Unknown error')}")
                            # Continue with Arabic data only if English fails
                            english_data = {'data': {'products': []}}
                        
                        # CREATE LOOKUP FOR ENGLISH PRODUCT NAMES
                        english_products = {}
                        english_brand_data = english_data.get('data', {})
                        english_products_data = english_brand_data.get('products', [])
                        for product_data in english_products_data:
                            product_id = product_data.get('product_id')
                            product_title_en = product_data.get('product_title', '')
                            if product_id and product_title_en:
                                english_products[product_id] = product_title_en
                    
                    # Products are inside data.products, not data directly
                    brand_data = arabic_data.get('data', {})
                    products_data = brand_data.get('products', [])
                    logger.info(f"📦 Found {len(products_data)} products for {brand.title} (Arabic: {len(products_data)}, English: {len(english_products)})")
                    
                    for product_data in products_data:
                        product_id = product_data.get('product_id')  # Note: it's product_id, not id
                        product_title_ar = product_data.get('product_title', '')
                        product_title_en = english_products.get(product_id, '')
                        product_packing = product_data.get('product_packing', '')
                        product_price = product_data.get('product_contract_price', 0.0)
                        
                        if product_id and product_title_ar:
                            try:
                                # Check if product with this ID already exists
                                existing_product = db.query(Product).filter(Product.id == product_id).first()
                                
                                if existing_product:
                                    logger.info(f"⚠️ Product ID={product_id} already exists, skipping duplicate")
                                    skipped_count += 1
                                    continue
                                
                                # Create product with external ID as primary key
                                product = Product(
                                    id=product_id,  # Use external ID as primary key
                                    external_id=product_id,  # Keep for compatibility
                                    brand_id=brand.id,  # Use brand's ID (which is also external ID)
                                    title=product_title_ar,  # Arabic title
                                    title_en=product_title_en,  # English title
                                    packing=product_packing,
                                    contract_price=float(product_price) if product_price else 0.0
                                )
                                
                                db.add(product)
                                db.commit()  # Commit each product individually
                                processed_count += 1
                                logger.info(f"✅ Created product: ID={product_id}, AR: '{product_title_ar}', EN: '{product_title_en}'")
                            
                            except Exception as product_error:
                                logger.warning(f"⚠️ Failed to create product ID={product_id}: {str(product_error)}")
                                db.rollback()
                                skipped_count += 1
                                continue
                
                except Exception as e:
                    logger.error(f"❌ Error syncing products for brand {brand.id}: {str(e)}")
                    continue
                
                # Add delay between brand processing to avoid overwhelming the API
                await asyncio.sleep(1.0)
            
            # Update sync log
            sync_log.status = 'success'
            sync_log.records_processed = processed_count
            sync_log.completed_at = datetime.utcnow()
            db.commit()
            
            logger.info(f"🎉 Clean slate products sync completed. Created {processed_count} products, skipped {skipped_count} duplicates.")
            return processed_count
            
        except Exception as e:
            logger.error(f"❌ Products sync failed: {str(e)}")
            sync_log.status = 'failed'
            sync_log.error_message = str(e)
            sync_log.completed_at = datetime.utcnow()
            db.commit()
            raise
            
    async def full_clean_slate_sync(self, db: Session) -> Dict[str, int]:
        """COMPLETE CLEAN SLATE: Delete all data and sync everything fresh"""
        logger.info("🚀 Starting COMPLETE CLEAN SLATE SYNC...")
        logger.info("⚠️ This will delete ALL existing data and sync fresh from external API")
        
        results = {}
        
        try:
            # CRITICAL FIX: Disable foreign key constraints temporarily for clean deletion
            logger.info("🔧 Temporarily disabling foreign key constraints...")
            db.execute(text("PRAGMA foreign_keys=OFF"))
            db.commit()
            
            # STEP 0: Delete all data in reverse dependency order to avoid FK conflicts
            logger.info("\n" + "="*50)
            logger.info("STEP 0: CLEAN DELETION (REVERSE FK ORDER)")
            logger.info("="*50)
            
            logger.info("🗑️ Deleting products...")
            db.query(Product).delete()
            db.commit()
            logger.info("✅ All products deleted")
            
            logger.info("🗑️ Deleting city-brand relationships...")
            db.execute(text("DELETE FROM city_brands"))
            db.commit()
            logger.info("✅ All city-brand relationships deleted")
            
            logger.info("🗑️ Deleting brands...")
            db.query(Brand).delete()
            db.commit()
            logger.info("✅ All brands deleted")
            
            logger.info("🗑️ Deleting cities...")
            db.query(City).delete()
            db.commit()
            logger.info("✅ All cities deleted")
            
            # Re-enable foreign key constraints
            logger.info("🔧 Re-enabling foreign key constraints...")
            db.execute(text("PRAGMA foreign_keys=ON"))
            db.commit()
            
            # Step 1: Sync Cities (now with clean slate)
            logger.info("\n" + "="*50)
            logger.info("STEP 1: CLEAN SLATE CITIES SYNC")
            logger.info("="*50)
            results['cities'] = await self.clean_slate_sync_cities_no_delete(db)
            
            # Step 2: Sync Brands (now with clean slate)
            logger.info("\n" + "="*50)
            logger.info("STEP 2: CLEAN SLATE BRANDS SYNC")
            logger.info("="*50)
            results['brands'] = await self.clean_slate_sync_brands_no_delete(db)
            
            # Step 3: Sync Products (now with clean slate)
            logger.info("\n" + "="*50)
            logger.info("STEP 3: CLEAN SLATE PRODUCTS SYNC")
            logger.info("="*50)
            results['products'] = await self.clean_slate_sync_products_no_delete(db)
            
            logger.info("\n" + "="*60)
            logger.info("🎉 COMPLETE CLEAN SLATE SYNC FINISHED!")
            logger.info("="*60)
            logger.info(f"📊 SUMMARY:")
            logger.info(f"   🏙️ Cities: {results['cities']}")
            logger.info(f"   🏷️ Brands: {results['brands']}")
            logger.info(f"   📦 Products: {results['products']}")
            logger.info("="*60)
            
            return results
            
        except Exception as e:
            # Always re-enable foreign keys even if sync fails
            try:
                logger.info("🔧 Re-enabling foreign key constraints after error...")
                db.execute(text("PRAGMA foreign_keys=ON"))
                db.commit()
            except:
                pass
            
            logger.error(f"❌ COMPLETE CLEAN SLATE SYNC FAILED: {str(e)}")
            raise

    async def clean_slate_sync_cities_no_delete(self, db: Session) -> int:
        """CLEAN SLATE cities sync without deletion (deletion already done in main sync)"""
        try:
            logger.info("📥 Starting cities sync (no deletion - already cleaned)...")
            sync_log = DatabaseManager.create_sync_log(db, 'cities', 'started')
            
            # STEP 1: FETCH FRESH DATA
            # Fetch Arabic cities
            logger.info("📥 Fetching cities in Arabic...")
            arabic_data = await self.fetch_cities_arabic()
            
            if arabic_data.get('key') != 'success':
                raise Exception(f"API error (Arabic): {arabic_data.get('msg', 'Unknown error')}")
            
            # Fetch English cities
            logger.info("📥 Fetching cities in English...")
            english_data = await self.fetch_cities_english()
            
            if english_data.get('key') != 'success':
                raise Exception(f"API error (English): {english_data.get('msg', 'Unknown error')}")
            
            # STEP 2: CREATE LOOKUP FOR ENGLISH NAMES
            english_cities = {city['id']: city['title'] for city in english_data.get('data', [])}
            
            # STEP 3: INSERT FRESH DATA WITH EXTERNAL ID AS PRIMARY KEY
            cities_data = arabic_data.get('data', [])
            processed_count = 0
            
            for city_data in cities_data:
                external_city_id = city_data.get('id')
                city_title_ar = city_data.get('title', '')
                city_title_en = english_cities.get(external_city_id, '')
                city_lat = city_data.get('lat')
                city_lng = city_data.get('lng')
                
                # Skip excluded Riyadh region cities
                if external_city_id in self.excluded_city_ids:
                    logger.info(f"⏭️ Skipping excluded city: ID={external_city_id}, {city_title_ar}")
                    continue
                
                if external_city_id and city_title_ar:
                    # Create city with external ID as the primary key
                    city = City(
                        id=external_city_id,  # Use external ID as primary key
                        external_id=external_city_id,  # Keep external_id for compatibility
                        name=city_title_ar,  # Arabic name
                        name_en=city_title_en,  # English name
                        title=city_title_ar,  # Alternative title field
                        lat=city_lat,
                        lng=city_lng
                    )
                    db.add(city)
                    processed_count += 1
                    logger.info(f"✅ Created city: ID={external_city_id}, {city_title_ar} ({city_title_en})")
            
            db.commit()
            
            # Update sync log
            sync_log.status = 'success'
            sync_log.records_processed = processed_count
            sync_log.completed_at = datetime.utcnow()
            db.commit()
            
            logger.info(f"🎉 Cities sync completed. Processed {processed_count} cities.")
            return processed_count
            
        except Exception as e:
            logger.error(f"❌ Cities sync failed: {str(e)}")
            sync_log.status = 'failed'
            sync_log.error_message = str(e)
            sync_log.completed_at = datetime.utcnow()
            db.commit()
            raise

    async def clean_slate_sync_brands_no_delete(self, db: Session) -> int:
        """CLEAN SLATE brands sync without deletion (deletion already done in main sync)"""
        try:
            logger.info("📥 Starting brands sync (no deletion - already cleaned)...")
            sync_log = DatabaseManager.create_sync_log(db, 'brands', 'started')
            
            # Get all cities to sync brands for
            cities = db.query(City).all()
            logger.info(f"📋 Found {len(cities)} cities to sync brands for")
            
            processed_count = 0
            all_brands = {}
            city_brand_relationships = []
            
            # Sync brands for each city (WITH DUAL-LANGUAGE SUPPORT)
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for city in cities:
                    logger.info(f"🏙️ Syncing brands for city: {city.name} (ID: {city.id})")
                    
                    try:
                        # FETCH ARABIC BRANDS DATA
                        url = f"{self.base_url}/get-location-brands/{city.id}"
                        async with session.get(url, headers=self.headers_ar) as response:
                            response.raise_for_status()
                            arabic_data = await response.json()
                        
                        if arabic_data.get('key') != 'success':
                            logger.warning(f"⚠️ API error (Arabic) for city {city.id}: {arabic_data.get('msg', 'Unknown error')}")
                            continue
                        
                        # FETCH ENGLISH BRANDS DATA
                        async with session.get(url, headers=self.headers_en) as response:
                            response.raise_for_status()
                            english_data = await response.json()
                        
                        if english_data.get('key') != 'success':
                            logger.warning(f"⚠️ API error (English) for city {city.id}: {english_data.get('msg', 'Unknown error')}")
                            # Continue with Arabic data only if English fails
                            english_data = {'data': []}
                        
                        # CREATE LOOKUP FOR ENGLISH BRAND NAMES
                        english_brands = {}
                        for brand_data in english_data.get('data', []):
                            contract_id = brand_data.get('contract_id')
                            brand_title_en = brand_data.get('brand_title', '')
                            if contract_id and brand_title_en:
                                english_brands[contract_id] = brand_title_en
                        
                        brands_data = arabic_data.get('data', [])
                        logger.info(f"📦 Found {len(brands_data)} brands for {city.name} (Arabic: {len(brands_data)}, English: {len(english_brands)})")
                        
                        for brand_data in brands_data:
                            contract_id = brand_data.get('contract_id')
                            brand_title_ar = brand_data.get('brand_title', '')
                            brand_title_en = english_brands.get(contract_id, '')
                            brand_image = brand_data.get('brand_image', '')
                            
                            if contract_id and brand_title_ar:
                                # DISABLED: Check if brand has products before saving
                                # This speeds up scraping by not pre-checking products for each brand
                                # Brands will be saved regardless of whether they have products
                                # logger.info(f"🔍 Checking if brand {contract_id} ({brand_title_ar}) has products...")
                                # has_products = await self.brand_has_products(session, contract_id)
                                # 
                                # if not has_products:
                                #     logger.info(f"⏭️ Skipping brand without products: ID={contract_id}, {brand_title_ar}")
                                #     continue
                                
                                # Add delay between processing different brands to avoid overwhelming the server
                                await asyncio.sleep(1)
                                
                                # CLEAN and NORMALIZE brand titles during scraping
                                cleaned_brand_title_ar = self._clean_and_normalize_brand_name(brand_title_ar)
                                cleaned_brand_title_en = self._clean_and_normalize_brand_name(brand_title_en) if brand_title_en else ''
                                logger.info(f"📝 Brand cleaning: AR: '{brand_title_ar}' -> '{cleaned_brand_title_ar}', EN: '{brand_title_en}' -> '{cleaned_brand_title_en}'")
                                
                                # Create brand with external ID as primary key (if not exists)
                                if contract_id not in all_brands:
                                    brand = Brand(
                                        id=contract_id,  # Use external ID as primary key
                                        external_id=contract_id,  # Keep for compatibility
                                        title=cleaned_brand_title_ar,  # Arabic title (cleaned and normalized)
                                        title_en=cleaned_brand_title_en,  # English title (cleaned and normalized)
                                        image_url=brand_image
                                    )
                                    db.add(brand)
                                    all_brands[contract_id] = brand
                                    logger.info(f"✅ Created brand: ID={contract_id}, AR: '{cleaned_brand_title_ar}', EN: '{cleaned_brand_title_en}'")
                                
                                # Store city-brand relationship for bulk insert
                                relationship = (city.id, contract_id)
                                if relationship not in city_brand_relationships:
                                    city_brand_relationships.append(relationship)
                                
                                processed_count += 1
                    
                    except Exception as e:
                        logger.error(f"❌ Error syncing brands for city {city.id}: {str(e)}")
                        continue
                    
                    # Add delay between processing different cities to avoid overwhelming the server
                    await asyncio.sleep(2)
            
            # Commit brands first
            db.commit()
            logger.info(f"✅ Committed {len(all_brands)} brands to database")
            
            # Bulk insert city-brand relationships
            if city_brand_relationships:
                logger.info(f"🔗 Inserting {len(city_brand_relationships)} city-brand relationships...")
                
                # Use bulk insert for better performance
                insert_stmt = text("""
                    INSERT INTO city_brands (city_id, brand_id) 
                    VALUES (:city_id, :brand_id)
                """)
                
                relationship_data = [
                    {"city_id": city_id, "brand_id": brand_id}
                    for city_id, brand_id in city_brand_relationships
                ]
                
                db.execute(insert_stmt, relationship_data)
                db.commit()
                logger.info(f"✅ Inserted {len(city_brand_relationships)} city-brand relationships")
            
            # Update sync log
            sync_log.status = 'success'
            sync_log.records_processed = processed_count
            sync_log.completed_at = datetime.utcnow()
            db.commit()
            
            logger.info(f"🎉 Brands sync completed!")
            logger.info(f"📊 Total processed: {processed_count}")
            logger.info(f"📊 Total brands: {len(all_brands)}")
            logger.info(f"📊 Total relationships: {len(city_brand_relationships)}")
            
            return processed_count
            
        except Exception as e:
            logger.error(f"❌ Brands sync failed: {str(e)}")
            sync_log.status = 'failed'
            sync_log.error_message = str(e)
            sync_log.completed_at = datetime.utcnow()
            db.commit()
            raise

    async def clean_slate_sync_products_no_delete(self, db: Session) -> int:
        """CLEAN SLATE products sync without deletion (deletion already done in main sync)"""
        try:
            logger.info("📥 Starting products sync (no deletion - already cleaned)...")
            sync_log = DatabaseManager.create_sync_log(db, 'products', 'started')
            
            # Get all brands to sync products for
            brands = db.query(Brand).all()
            logger.info(f"📋 Found {len(brands)} brands to sync products for")
            
            processed_count = 0
            skipped_count = 0
            
            # Sync products for each brand (WITH DUAL-LANGUAGE SUPPORT)
            for brand in brands:
                logger.info(f"🏷️ Syncing products for brand: {brand.title} (ID: {brand.id})")
                
                try:
                    url = f"{self.base_url}/get-brand-products/{brand.id}"
                    timeout = aiohttp.ClientTimeout(total=30)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        # FETCH ARABIC PRODUCTS DATA with retry logic (including 400 errors)
                        try:
                            arabic_data = await self.make_product_api_request_with_retry(
                                session, url, self.headers_ar, brand.id, 'ar', max_retries=3, base_delay=1.0
                            )
                        except Exception as e:
                            logger.error(f"❌ Failed to fetch Arabic products for brand {brand.id} after 3 retries: {str(e)}")
                            continue
                        
                        if arabic_data.get('key') != 'success':
                            logger.warning(f"⚠️ API error (Arabic) for brand {brand.id}: {arabic_data.get('msg', 'Unknown error')}")
                            continue
                        
                        # Add delay between Arabic and English requests
                        await asyncio.sleep(0.5)
                        
                        # FETCH ENGLISH PRODUCTS DATA with retry logic (including 400 errors)
                        try:
                            english_data = await self.make_product_api_request_with_retry(
                                session, url, self.headers_en, brand.id, 'en', max_retries=3, base_delay=1.0
                            )
                        except Exception as e:
                            logger.warning(f"⚠️ Failed to fetch English products for brand {brand.id} after 3 retries: {str(e)}")
                            # Continue with Arabic data only if English fails
                            english_data = {'data': {'products': []}}
                        
                        if english_data.get('key') != 'success' and 'data' not in english_data:
                            logger.warning(f"⚠️ API error (English) for brand {brand.id}: {english_data.get('msg', 'Unknown error')}")
                            # Continue with Arabic data only if English fails
                            english_data = {'data': {'products': []}}
                        
                        # CREATE LOOKUP FOR ENGLISH PRODUCT NAMES
                        english_products = {}
                        english_brand_data = english_data.get('data', {})
                        english_products_data = english_brand_data.get('products', [])
                        for product_data in english_products_data:
                            product_id = product_data.get('product_id')
                            product_title_en = product_data.get('product_title', '')
                            if product_id and product_title_en:
                                english_products[product_id] = product_title_en
                    
                    # Products are inside data.products, not data directly
                    brand_data = arabic_data.get('data', {})
                    products_data = brand_data.get('products', [])
                    logger.info(f"📦 Found {len(products_data)} products for {brand.title} (Arabic: {len(products_data)}, English: {len(english_products)})")
                    
                    for product_data in products_data:
                        product_id = product_data.get('product_id')  # Note: it's product_id, not id
                        product_title_ar = product_data.get('product_title', '')
                        product_title_en = english_products.get(product_id, '')
                        product_packing = product_data.get('product_packing', '')
                        product_price = product_data.get('product_contract_price', 0.0)
                        
                        if product_id and product_title_ar:
                            try:
                                # Check if product already exists for this brand
                                existing_product = db.query(Product).filter(
                                    Product.external_id == product_id,
                                    Product.brand_id == brand.id
                                ).first()
                                
                                if existing_product:
                                    # Update existing product
                                    existing_product.title = product_title_ar
                                    existing_product.title_en = product_title_en
                                    existing_product.packing = product_packing
                                    existing_product.contract_price = float(product_price) if product_price else 0.0
                                    logger.info(f"🔄 Updated product: external_id={product_id}, AR: '{product_title_ar}', EN: '{product_title_en}'")
                                else:
                                    # Create new product (let id auto-increment)
                                    product = Product(
                                        external_id=product_id,  # Store external ID for reference
                                        brand_id=brand.id,  # Use brand's ID (which is also external ID)
                                        title=product_title_ar,  # Arabic title
                                        title_en=product_title_en,  # English title
                                        packing=product_packing,
                                        contract_price=float(product_price) if product_price else 0.0
                                    )
                                    
                                    db.add(product)
                                    logger.info(f"✅ Created product: external_id={product_id}, AR: '{product_title_ar}', EN: '{product_title_en}'")
                                
                                db.commit()  # Commit each product individually
                                processed_count += 1
                            
                            except Exception as product_error:
                                logger.warning(f"⚠️ Failed to create/update product external_id={product_id}: {str(product_error)}")
                                db.rollback()
                                skipped_count += 1
                                continue
                
                except Exception as e:
                    logger.error(f"❌ Error syncing products for brand {brand.id}: {str(e)}")
                    continue
                
                # Add delay between brand processing to avoid overwhelming the API
                await asyncio.sleep(1.0)
            
            # Update sync log
            sync_log.status = 'success'
            sync_log.records_processed = processed_count
            sync_log.completed_at = datetime.utcnow()
            db.commit()
            
            logger.info(f"🎉 Products sync completed. Created {processed_count} products, skipped {skipped_count} duplicates.")
            return processed_count
            
        except Exception as e:
            logger.error(f"❌ Products sync failed: {str(e)}")
            sync_log.status = 'failed'
            sync_log.error_message = str(e)
            sync_log.completed_at = datetime.utcnow()
            db.commit()
            raise

    # Legacy methods for compatibility (marked as deprecated)
    def sync_cities(self, db: Session) -> int:
        """DEPRECATED: Use clean_slate_sync_cities instead"""
        logger.warning("⚠️ sync_cities is deprecated. Use clean_slate_sync_cities for fresh data.")
        return self.clean_slate_sync_cities(db)
    
    def sync_brands_for_city(self, db: Session, city_external_id: int) -> int:
        """DEPRECATED: Use clean_slate_sync_brands instead"""
        logger.warning("⚠️ sync_brands_for_city is deprecated. Use clean_slate_sync_brands for fresh data.")
        return 0  # Return 0 to indicate deprecated
        
    def sync_all_brands(self, db: Session) -> int:
        """DEPRECATED: Use clean_slate_sync_brands instead"""
        logger.warning("⚠️ sync_all_brands is deprecated. Use clean_slate_sync_brands for fresh data.")
        return self.clean_slate_sync_brands(db)
        
    async def full_sync(self, db: Session) -> Dict[str, int]:
        """DEPRECATED: Use full_clean_slate_sync instead"""
        logger.warning("⚠️ full_sync is deprecated. Use full_clean_slate_sync for fresh data.")
        return await self.full_clean_slate_sync(db)


# Singleton instance
data_scraper = DataScraperService() 