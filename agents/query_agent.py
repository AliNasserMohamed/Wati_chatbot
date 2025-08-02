#!/usr/bin/env python3

import requests
import json
import logging
import asyncio
import time
from typing import Dict, List, Any, Optional
from openai import AsyncOpenAI
import os
from dotenv import load_dotenv
from database.db_models import UserSession
from sqlalchemy.orm import Session
from utils.language_utils import language_handler
from services.data_api import data_api
from database.db_utils import get_db
import random

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import message logger for detailed journey tracking
try:
    from utils.message_logger import message_journey_logger
    LOGGING_AVAILABLE = True
except ImportError:
    LOGGING_AVAILABLE = False
    logger.warning("Message journey logger not available - LLM logging disabled")

class QueryAgent:
    """
    Enhanced Query Agent with function calling capabilities for answering user queries 
    about water delivery services, cities, brands, and products
    Enhanced with brand extraction and improved context handling
    """
    
    def __init__(self):
        self.api_base_url = "http://localhost:8000/api"
        
        # Initialize OpenAI client
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        
        self.openai_client = AsyncOpenAI(api_key=openai_api_key)
        
        # Rate limiting settings (configurable via environment variables)
        self.last_request_time = 0
        self.min_request_interval = float(os.getenv("OPENAI_MIN_REQUEST_INTERVAL", "0.5"))  # Default 500ms between requests
        self.max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "3"))  # Default 3 retries
        self.base_delay = float(os.getenv("OPENAI_BASE_DELAY", "1"))  # Default 1 second base delay
        
        # Simple classification cache to reduce API calls
        self.classification_cache = {}
        self.cache_max_size = 1000
        
        # Define available functions for the LLM
        self.available_functions = {
            "get_all_cities": self.get_all_cities,
            "get_city_id_by_name": self.get_city_id_by_name,
            "get_brands_by_city": self.get_brands_by_city,
            "get_products_by_brand": self.get_products_by_brand,
            "search_cities": self.search_cities,
            "check_city_availability": self.check_city_availability
        }
        
        # Classification prompts for message relevance
        self.classification_prompt_ar = """أنت مصنف رسائل ذكي لشركة توصيل المياه. مهمتك تحديد ما إذا كانت الرسالة متعلقة بخدمات الشركة أم لا.

الرسائل المتعلقة بالخدمة تشمل فقط:
✅ أسئلة عن المدن المتاحة للتوصيل
✅ أسئلة عن العلامات التجارية للمياه
✅ أسئلة عن المنتجات والأسعار
✅ طلبات معرفة التوفر في مدينة معينة
✅ أسئلة عن أحجام المياه والعبوات
✅ ذكر أسماء العلامات التجارية مثل (نستله، أكوافينا، العين، القصيم، المراعي، وغيرها)
✅ الرد بـ "نعم" أو "أي" عندما نسأل عن منتج معين
✅ أسئلة عن الأسعار الإجمالية أو قوائم الأسعار
✅ طلبات الطلب أو الشراء ("أريد أطلب"، "كيف أطلب"، "أريد أشتري"، "أبي أطلب")

الرسائل غير المتعلقة بالخدمة تشمل:
❌ التحيات العامة ("أهلاً", "مرحبا", "السلام عليكم", "صباح الخير", "مساء الخير")  
❌ رسائل الشكر والامتنان ("شكراً", "جزاك الله خير", "مشكور", "الله يعطيك العافية")
❌ المواضيع العامة غير المتعلقة بالمياه
❌ الأسئلة الشخصية
❌ طلبات المساعدة في مواضيع أخرى
❌ الرسائل التي تحتوي على روابط
❌ الاستفسار عن خدمة التوصيل العامة
❌ مشاكل متعلقة بالمندوب أو المندوبين
❌ شكاوي من المندوب أو طاقم التوصيل
❌ مشاكل التوصيل (تأخير، عدم وصول الطلب، مشاكل التوصيل)
❌ شكاوي خدمة العملاء أو مشاكل الخدمة
❌ طلبات إلغاء أو تعديل طلبات موجودة
❌ استفسارات عن حالة الطلب أو تتبع الطلب

تعليمات خاصة وصارمة:
- كن صارم جداً في التصنيف - فقط الأسئلة عن المدن والعلامات التجارية والمنتجات والأسعار تعتبر متعلقة
- أي رسالة تذكر "المندوب" أو "التوصيل" أو "الطلب لم يصل" أو "تأخر" تعتبر غير متعلقة
- أي شكوى أو مشكلة في الخدمة تعتبر غير متعلقة
- لا تعتبر التحيات والشكر متعلقة بالخدمة حتى لو كانت في سياق محادثة عن المياه
- اعتبر ذكر أسماء العلامات التجارية للمياه متعلق بالخدمة فقط
- اعتبر الرد بـ "نعم" أو "أي" متعلق بالخدمة إذا كان في سياق محادثة عن المنتجات فقط

أجب بـ "relevant" إذا كانت الرسالة متعلقة بالمنتجات والأسعار والعلامات التجارية والمدن فقط، أو "not_relevant" لأي شيء آخر."""

        self.classification_prompt_en = """You are a smart message classifier for a water delivery company. Your task is to determine if a message is related to the company's services or not.

Service-related messages include ONLY:
✅ Questions about available cities for delivery
✅ Questions about water brands
✅ Questions about products and prices
✅ Requests to check availability in specific cities
✅ Questions about water sizes and packaging
✅ Mentioning brand names like (Nestle, Aquafina, Alain, Qassim, Almarai, etc.)
✅ Replying with "yes" when we ask about a specific product
✅ Questions about total prices or price lists
✅ Order requests or purchase inquiries ("I want to order", "how to order", "I want to buy")

Non-service-related messages include:
❌ General greetings ("hello", "hi", "good morning", "good evening", "how are you")
❌ Thank you messages ("thanks", "thank you", "appreciate it", "much obliged")
❌ General topics not related to water
❌ Personal questions
❌ Requests for help with other topics
❌ Messages containing links or URLs
❌ General delivery service inquiries
❌ Problems related to delivery person/driver
❌ Complaints about delivery person or delivery staff
❌ Delivery problems (delays, order not arrived, delivery issues)
❌ Customer service complaints or service problems
❌ Requests to cancel or modify existing orders
❌ Inquiries about order status or order tracking

Special strict instructions:
- Be very strict in classification - only questions about cities, brands, products, and prices count as relevant
- Any message mentioning "delivery person", "driver", "delivery", "order not arrived", or "delayed" is not relevant
- Any complaint or service problem is not relevant
- Do not consider greetings and thanks as service-related even if they appear in water-related conversations
- Consider mentioning water brand names as service-related only
- Consider "yes" replies as service-related only if in context of product discussions

Reply with "relevant" if the message is related to products, prices, brands, and cities only, or "not_relevant" for anything else."""
        
        # Function definitions for OpenAI function calling
        self.function_definitions = [
            {
                "name": "get_all_cities",
                "description": "Get complete list of all cities we serve with water delivery. Use this when user asks about available cities, locations we serve, or wants to see all cities. Returns city ID, Arabic name, and English name for each city.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "get_city_id_by_name",
                "description": "STEP 1 in workflow: Get the internal city ID from a city name (Arabic or English). This is the FIRST step in the mandatory workflow: City→Brands→Products→Response. Always start here when customer asks about brands or products.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city_name": {
                            "type": "string",
                            "description": "Name of the city in Arabic or English (e.g., 'الرياض', 'Riyadh', 'جدة', 'Jeddah')"
                        }
                    },
                    "required": ["city_name"]
                }
            },
            {
                "name": "get_brands_by_city",
                "description": "STEP 2 in workflow: Get all water brands available in a specific city. ONLY use this AFTER getting the city in Step 1. This is the second step in the mandatory workflow: City→Brands→Products→Response. You must call get_city_id_by_name first to get the city_id.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city_id": {
                            "type": "integer",
                            "description": "Internal city ID (get this using get_city_id_by_name function first)"
                        }
                    },
                    "required": ["city_id"]
                }
            },
            {
                "name": "get_products_by_brand",
                "description": "STEP 3 in workflow: Get all water products offered by a specific brand. ONLY use this AFTER Steps 1 (get city) and 2 (show brands) are complete. This is the third step in the mandatory workflow: City→Brands→Products→Response. Customer must have selected a specific brand first.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "brand_id": {
                            "type": "integer",
                            "description": "Brand ID (get this from get_brands_by_city response after customer selects a brand)"
                        }
                    },
                    "required": ["brand_id"]
                }
            },
            {
                "name": "search_cities",
                "description": "STEP 1 alternative: Search for cities by name when exact city name doesn't match. Use this as part of Step 1 in the workflow when get_city_id_by_name fails to find the city. This helps handle typos or find similar city names.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search term for city name (Arabic or English)"
                        }
                    },
                    "required": ["query"]
                }
            },

            {
                "name": "check_city_availability",
                "description": "Check if a product or brand is available in a specific city. Use this when user asks about product/brand availability in their city after you know both the city and the product/brand name.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city_name": {
                            "type": "string",
                            "description": "Name of the city in Arabic or English"
                        },
                        "item_type": {
                            "type": "string",
                            "description": "Type of item being checked: 'brand' or 'product'",
                            "enum": ["brand", "product"]
                        },
                        "item_name": {
                            "type": "string",
                            "description": "Name of the brand or product to check availability for"
                        }
                    },
                    "required": ["city_name", "item_type", "item_name"]
                }
            }
        ]
    
    async def _rate_limit_delay(self):
        """Ensure minimum time between API requests"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            delay = self.min_request_interval - time_since_last
            await asyncio.sleep(delay)
        self.last_request_time = time.time()
    
    async def _call_openai_with_retry(self, **kwargs):
        """Make OpenAI API call with exponential backoff retry logic"""
        for attempt in range(self.max_retries + 1):
            try:
                # Apply rate limiting
                await self._rate_limit_delay()
                
                # Make the API call
                response = await self.openai_client.chat.completions.create(**kwargs)
                return response
                
            except Exception as e:
                error_str = str(e)
                
                # Handle 429 rate limit errors specifically
                if "429" in error_str or "rate limit" in error_str.lower():
                    if attempt < self.max_retries:
                        # Exponential backoff with jitter
                        delay = (self.base_delay * (2 ** attempt)) + random.uniform(0, 1)
                        logger.warning(f"Rate limit hit, attempt {attempt + 1}/{self.max_retries + 1}. Retrying in {delay:.2f}s...")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error("Max retries reached for rate limit error")
                        raise Exception("OpenAI rate limit exceeded. Please try again in a few minutes.")
                
                # Handle other errors
                elif attempt < self.max_retries:
                    delay = 1.0 + random.uniform(0, 0.5)  # Small delay for other errors
                    logger.warning(f"API error on attempt {attempt + 1}: {error_str}. Retrying in {delay:.2f}s...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    # Max retries reached, re-raise the error
                    raise e
        
        # This should never be reached, but just in case
        raise Exception("Unexpected error in API retry logic")
    
    def _get_db_session(self):
        """Get database session"""
        from database.db_utils import SessionLocal
        return SessionLocal()
    
    def _extract_city_from_context(self, user_message: str, conversation_history: List[Dict] = None) -> Optional[Dict[str, Any]]:
        """Extract city information from current message and conversation history"""
        try:
            db = self._get_db_session()
            try:
                all_cities = data_api.get_all_cities(db)
                
                # PRIORITY 1: Check current user message first
                if user_message:
                    current_content = user_message.lower()
                    for city in all_cities:
                        city_name_ar = city.get("name", "").lower()
                        city_name_en = city.get("name_en", "").lower()
                        
                        if city_name_ar and city_name_ar in current_content:
                            return {
                                "city_id": city["id"],
                                "city_name": city["name"],
                                "city_name_en": city["name_en"],
                                "found_in": "current_message"
                            }
                        elif city_name_en and city_name_en in current_content:
                            return {
                                "city_id": city["id"],
                                "city_name": city["name"],
                                "city_name_en": city["name_en"],
                                "found_in": "current_message"
                            }
                
                # PRIORITY 2: Check conversation history if no city in current message
                if conversation_history:
                    for message in reversed(conversation_history[-10:]):  # Check last 10 messages
                        content = message.get("content", "").lower()
                        
                        # Check if any city name appears in the message
                        for city in all_cities:
                            city_name_ar = city.get("name", "").lower()
                            city_name_en = city.get("name_en", "").lower()
                            
                            if city_name_ar and city_name_ar in content:
                                return {
                                    "city_id": city["id"],
                                    "city_name": city["name"],
                                    "city_name_en": city["name_en"],
                                    "found_in": "conversation_history"
                                }
                            elif city_name_en and city_name_en in content:
                                return {
                                    "city_id": city["id"],
                                    "city_name": city["name"],
                                    "city_name_en": city["name_en"],
                                    "found_in": "conversation_history"
                                }
                
                return None
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error extracting city from context: {str(e)}")
            return None

    def _extract_brand_from_context(self, user_message: str, conversation_history: List[Dict] = None, city_id: int = None) -> Optional[Dict[str, Any]]:
        """Extract brand information from current message and conversation history
        IMPORTANT: Only returns brands if city_id is provided (city must be known first)
        IMPORTANT: Ignores size terms like ابو ربع, ابو نص, ابو ريال as they are NOT brand names
        """
        # Do not extract brands without knowing the city first
        if not city_id:
            return None
        
        # Size terms that should NEVER be treated as brand names
        size_terms = ["ابو ربع", "ابو نص", "ابو ريال", "ابو ريالين"]
        
        # Check if the message only contains size terms - if so, don't extract any brand
        message_lower = user_message.lower()
        if any(size_term in message_lower for size_term in size_terms) and not any(brand_indicator in message_lower for brand_indicator in ["نستله", "أكوافينا", "العين", "القصيم", "المراعي"]):
            return None
            
        try:
            db = self._get_db_session()
            try:
                # Get brands only for the specific city
                brands = data_api.get_brands_by_city(db, city_id)
                
                # PRIORITY 1: Check current user message first
                if user_message:
                    current_content = user_message.lower()
                    for brand in brands:
                        brand_title = brand.get("title", "").lower()
                        
                        if brand_title and brand_title in current_content:
                            return {
                                "brand_id": brand["id"],
                                "brand_title": brand["title"],
                                "found_in": "current_message"
                            }
                
                # PRIORITY 2: Check conversation history if no brand in current message
                if conversation_history:
                    for message in reversed(conversation_history[-10:]):  # Check last 10 messages
                        content = message.get("content", "").lower()
                        
                        # Check if any brand name appears in the message
                        for brand in brands:
                            brand_title = brand.get("title", "").lower()
                            
                            if brand_title and brand_title in content:
                                return {
                                    "brand_id": brand["id"],
                                    "brand_title": brand["title"],
                                    "found_in": "conversation_history"
                                }
                
                return None
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error extracting brand from context: {str(e)}")
            return None

    def _check_for_yes_response(self, user_message: str, conversation_history: List[Dict] = None) -> bool:
        """Check if user is responding with yes to a previous product question"""
        if not conversation_history:
            return False
        
        # Check if current message is a yes response
        yes_words = ["نعم", "أي", "أيوة", "اي", "yes", "yeah", "yep", "sure", "ok", "okay"]
        user_msg_lower = user_message.lower().strip()
        
        if user_msg_lower in yes_words:
            # Check if the last bot message was asking about a product
            for message in reversed(conversation_history[-3:]):  # Check last 3 messages
                if message.get("role") == "assistant":
                    content = message.get("content", "").lower()
                    # Check if the bot asked about needing a product or mentioned a price
                    if any(phrase in content for phrase in ["تحتاج", "تريد", "هل تريد", "هل تحتاج", "السعر", "الثمن", "do you need", "would you like", "price", "cost"]):
                        return True
            return True  # If user says yes in context of water conversation, it's likely relevant
        
        return False

    def _check_for_total_price_question(self, user_message: str) -> bool:
        """Check if user is asking about total prices or price lists"""
        price_keywords = [
            "الأسعار", "قائمة الأسعار", "كم الأسعار", "ايش الأسعار",  
            "أسعاركم", "جميع الأسعار", "كل الأسعار", "الاسعار كلها",
            "prices", "price list", "all prices", "total prices", "price menu"
        ]
        
        user_msg_lower = user_message.lower()
        return any(keyword.lower() in user_msg_lower for keyword in price_keywords)
    
    def get_all_cities(self) -> Dict[str, Any]:
        """Get complete list of all cities we serve"""
        try:
            db = self._get_db_session()
            try:
                cities = data_api.get_all_cities(db)
                # Filter to return only city ID, Arabic name, and English name
                filtered_cities = [
                    {
                        "id": city["id"],
                        "name": city["name"],        # Arabic name
                        "name_en": city["name_en"]   # English name
                    }
                    for city in cities
                ]
                return {"success": True, "data": filtered_cities}
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error fetching cities: {str(e)}")
            return {"error": f"Failed to get cities: {str(e)}"}
    
    def get_city_id_by_name(self, city_name: str) -> Dict[str, Any]:
        """Get city ID by name (helper function) with typo handling and Riyadh regions support"""
        try:
            db = self._get_db_session()
            try:
                # Get all cities and find matching one
                cities = data_api.get_all_cities(db)
                
                # Special handling for Riyadh regions - prioritize exact matches
                riyadh_regions = {
                    "شمال الرياض": ["شمال الرياض", "north riyadh", "شمال الرياض", "الرياض الشمالي"],
                    "جنوب الرياض": ["جنوب الرياض", "south riyadh", "جنوب الرياض", "الرياض الجنوبي"], 
                    "غرب الرياض": ["غرب الرياض", "west riyadh", "غرب الرياض", "الرياض الغربي"],
                    "شرق الرياض": ["شرق الرياض", "east riyadh", "شرق الرياض", "الرياض الشرقي"],
                    "الرياض": ["الرياض", "riyadh", "رياض"]
                }
                
                city_name_normalized = city_name.strip().lower()
                
                # Check for Riyadh regions with priority handling
                for region_name, variations in riyadh_regions.items():
                    for variation in variations:
                        if city_name_normalized == variation.lower():
                            # Find exact match for this specific region
                            for city in cities:
                                city_name_db = city.get("name", "").strip()
                                if city_name_db == region_name:
                                    return {
                                        "success": True,
                                        "city_id": city["id"],
                                        "city_name": city["name"],
                                        "city_name_en": city.get("name_en", ""),
                                        "match_type": "exact_region"
                                    }
                
                # If user just typed "الرياض" and we have multiple Riyadh regions, 
                # prioritize the main "الرياض" city over regions
                if city_name_normalized in ["الرياض", "riyadh", "رياض"]:
                    main_riyadh = None
                    riyadh_regions_found = []
                    
                    for city in cities:
                        city_name_db = city.get("name", "").strip()
                        if city_name_db == "الرياض":
                            main_riyadh = city
                        elif city_name_db in ["شمال الرياض", "جنوب الرياض", "غرب الرياض", "شرق الرياض"]:
                            riyadh_regions_found.append(city)
                    
                    # Return main Riyadh if available
                    if main_riyadh:
                        return {
                            "success": True,
                            "city_id": main_riyadh["id"],
                            "city_name": main_riyadh["name"],
                            "city_name_en": main_riyadh.get("name_en", ""),
                            "match_type": "exact",
                            "note": f"وجدت أيضاً {len(riyadh_regions_found)} مناطق أخرى في الرياض" if riyadh_regions_found else None
                        }
                
                # Regular exact match (case insensitive) for other cities
                for city in cities:
                    city_name_db = city.get("name", "").lower()
                    city_name_en_db = city.get("name_en", "").lower()
                    
                    # Exact match check
                    if (city_name_normalized == city_name_db or 
                        city_name_normalized == city_name_en_db):
                        return {
                            "success": True,
                            "city_id": city["id"],
                            "city_name": city["name"],
                            "city_name_en": city.get("name_en", ""),
                            "match_type": "exact"
                        }
                
                # Partial match for other cities (existing logic)
                for city in cities:
                    city_name_db = city.get("name", "").lower()
                    city_name_en_db = city.get("name_en", "").lower()
                    
                    if (city_name_normalized in city_name_db or 
                        city_name_normalized in city_name_en_db):
                        return {
                            "success": True,
                            "city_id": city["id"],
                            "city_name": city["name"],
                            "city_name_en": city.get("name_en", ""),
                            "match_type": "partial"
                        }
                
                # If no exact match, try fuzzy search for typos
                search_results = data_api.search_cities(db, city_name)
                if search_results:
                    # Return the first search result with indication it's a suggested match
                    first_result = search_results[0]
                    return {
                        "success": True,
                        "city_id": first_result["id"],
                        "city_name": first_result["name"],
                        "city_name_en": first_result.get("name_en", ""),
                        "match_type": "suggested",
                        "original_input": city_name,
                        "suggestion_message": f"لم أجد '{city_name}' بالضبط، لكن وجدت '{first_result['name']}'. هل تقصد هذه المدينة؟"
                    }
                
                return {
                    "success": False,
                    "error": f"لم أجد مدينة باسم '{city_name}'. يرجى التحقق من الاسم أو جرب اسم مدينة أخرى.",
                    "original_input": city_name
                }
            finally:
                db.close()
            
        except Exception as e:
            logger.error(f"Error finding city ID for {city_name}: {str(e)}")
            return {"error": f"Failed to find city: {str(e)}"}
    
    def get_brands_by_city(self, city_id: int) -> Dict[str, Any]:
        """Get brands available in a specific city"""
        try:
            db = self._get_db_session()
            try:
                brands = data_api.get_brands_by_city(db, city_id)
                # Filter to return only brand ID and brand name
                filtered_brands = [
                    {
                        "id": brand["id"],           # Brand ID
                        "title": brand["title"]     # Brand name
                    }
                    for brand in brands
                ]
                return {"success": True, "data": filtered_brands}
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error fetching brands for city {city_id}: {str(e)}")
            return {"error": f"Failed to get brands: {str(e)}"}
    
    def get_products_by_brand(self, brand_id: int) -> Dict[str, Any]:
        """Get products offered by a specific brand"""
        try:
            db = self._get_db_session()
            try:
                products = data_api.get_products_by_brand(db, brand_id)
                # Filter to return only product name, price, and amount
                filtered_products = [
                    {
                        "product_title": product["product_title"],         # Product name
                        "product_contract_price": product["product_contract_price"],  # Price
                        "product_packing": product["product_packing"]      # Amount
                    }
                    for product in products
                ]
                return {"success": True, "data": filtered_products}
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error fetching products for brand {brand_id}: {str(e)}")
            return {"error": f"Failed to get products: {str(e)}"}
    
    def search_cities(self, query: str) -> Dict[str, Any]:
        """Search cities by name with special Riyadh regions handling"""
        try:
            db = self._get_db_session()
            try:
                cities = data_api.search_cities(db, query)
                
                if not cities:
                    return {
                        "success": False,
                        "error": f"لم أجد أي مدينة تحتوي على '{query}'. يرجى التحقق من الاسم أو جرب كلمات مختلفة.",
                        "query": query
                    }
                
                # Filter to return city information with match type for better UX
                filtered_cities = []
                main_riyadh_found = False
                regions_found = []
                
                for city in cities:
                    city_data = {
                        "id": city["id"],
                        "name": city["name"],        # Arabic name
                        "name_en": city.get("name_en", ""),   # English name
                        "match_type": city.get("match_type", "partial")
                    }
                    
                    # Track Riyadh regions for better messaging
                    if city["name"] == "الرياض":
                        main_riyadh_found = True
                    elif city["name"] in ["شمال الرياض", "جنوب الرياض", "غرب الرياض", "شرق الرياض"]:
                        regions_found.append(city["name"])
                    
                    filtered_cities.append(city_data)
                
                # Add helpful message for Riyadh searches
                message = None
                if main_riyadh_found and regions_found:
                    message = f"وجدت الرياض و {len(regions_found)} مناطق أخرى في الرياض"
                elif regions_found and not main_riyadh_found:
                    message = f"وجدت {len(regions_found)} منطقة في الرياض"
                elif len(filtered_cities) > 5:
                    message = f"وجدت {len(filtered_cities)} مدينة تحتوي على '{query}'"
                
                return {
                    "success": True, 
                    "data": filtered_cities,
                    "count": len(filtered_cities),
                    "query": query,
                    "message": message
                }
                
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error searching cities: {str(e)}")
            return {"success": False, "error": f"حدث خطأ أثناء البحث عن المدن: {str(e)}"}
    

    def check_city_availability(self, city_name: str, item_type: str, item_name: str) -> Dict[str, Any]:
        """Check if a brand or product is available in a specific city"""
        try:
            db = self._get_db_session()
            try:
                # First get the city ID
                city_result = self.get_city_id_by_name(city_name)
                if not city_result.get("success"):
                    return {
                        "success": False,
                        "error": f"لم أجد مدينة باسم '{city_name}'. يرجى التحقق من الاسم.",
                        "item_type": item_type,
                        "item_name": item_name
                    }
                
                city_id = city_result["city_id"]
                
                if item_type == "brand":
                    # Check if brand exists in this city
                    brands = data_api.get_brands_by_city(db, city_id)
                    for brand in brands:
                        if item_name.lower() in brand["title"].lower():
                            return {
                                "success": True,
                                "available": True,
                                "city_name": city_result["city_name"],
                                "item_type": item_type,
                                "item_name": item_name,
                                "brand_info": {
                                    "id": brand["id"],
                                    "title": brand["title"]
                                }
                            }
                    
                    return {
                        "success": True,
                        "available": False,
                        "city_name": city_result["city_name"],
                        "item_type": item_type,
                        "item_name": item_name,
                        "message": f"للأسف، العلامة التجارية '{item_name}' غير متوفرة في {city_result['city_name']}"
                    }
                
                elif item_type == "product":
                    # Check if product exists in any brand in this city
                    brands = data_api.get_brands_by_city(db, city_id)
                    found_products = []
                    
                    for brand in brands:
                        products = data_api.get_products_by_brand(db, brand["id"])
                        for product in products:
                            if item_name.lower() in product["product_title"].lower():
                                found_products.append({
                                    "brand_name": brand["title"],
                                    "product_title": product["product_title"],
                                    "product_contract_price": product["product_contract_price"],
                                    "product_packing": product["product_packing"]
                                })
                    
                    if found_products:
                        return {
                            "success": True,
                            "available": True,
                            "city_name": city_result["city_name"],
                            "item_type": item_type,
                            "item_name": item_name,
                            "products": found_products
                        }
                    else:
                        return {
                            "success": True,
                            "available": False,
                            "city_name": city_result["city_name"],
                            "item_type": item_type,
                            "item_name": item_name,
                            "message": f"للأسف، المنتج '{item_name}' غير متوفر في {city_result['city_name']}"
                        }
                
                return {"success": False, "error": "نوع العنصر غير صحيح. يجب أن يكون 'brand' أو 'product'"}
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error checking availability for {item_name} in {city_name}: {str(e)}")
            return {"error": f"حدث خطأ في التحقق من التوفر: {str(e)}"}
    
    async def _classify_message_relevance(self, user_message: str, conversation_history: List[Dict] = None, user_language: str = 'ar') -> bool:
        """
        Use AI to classify if a message is related to water delivery services
        Returns True if relevant, False if not relevant
        """
        try:
            # Quick check for links - auto-reject messages with URLs
            import re
            url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
            if re.search(url_pattern, user_message):
                logger.info(f"Message contains URL, marking as not relevant: {user_message[:50]}...")
                return False
            
            # Check cache first to avoid duplicate API calls
            cache_key = f"{user_message.strip().lower()}_{user_language}"
            if cache_key in self.classification_cache:
                logger.info(f"Using cached classification for: {user_message[:30]}...")
                return self.classification_cache[cache_key]
            
            # Prepare context from conversation history
            context = ""
            if conversation_history:
                recent_messages = conversation_history[-3:]  # Last 3 messages for context
                context = "\n".join([f"{msg.get('role', 'user')}: {msg.get('content', '')}" for msg in recent_messages])
                context = f"\nRecent conversation context:\n{context}\n"
            
            # Choose classification prompt based on language
            classification_prompt = self.classification_prompt_ar if user_language == 'ar' else self.classification_prompt_en
            
            # Prepare the full prompt
            full_prompt = f"""{classification_prompt}
{context}
Current message to classify: "{user_message}"

Classification:"""
            
            # Call OpenAI for classification with retry logic
            response = await self._call_openai_with_retry(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": classification_prompt},
                    {"role": "user", "content": f"{context}\nCurrent message: {user_message}"}
                ],
                temperature=0.1,  # Low temperature for consistent classification
                max_tokens=10  # Short response expected
            )
            
            classification_result = response.choices[0].message.content.strip().lower()
            
            # Log the classification
            logger.info(f"Message classification for '{user_message[:50]}...': {classification_result}")
            
            # Determine relevance and cache the result
            is_relevant = "relevant" in classification_result
            
            # Cache the result (with size limit)
            if len(self.classification_cache) >= self.cache_max_size:
                # Remove oldest entry (simple FIFO)
                oldest_key = next(iter(self.classification_cache))
                del self.classification_cache[oldest_key]
            
            self.classification_cache[cache_key] = is_relevant
            
            # Return True if relevant, False if not relevant
            return is_relevant
            
        except Exception as e:
            logger.error(f"Error classifying message relevance: {str(e)}")
            # On error, default to relevant to avoid blocking legitimate queries
            return True
    
    async def process_query(self, user_message: str, conversation_history: List[Dict] = None, user_language: str = 'ar', journey_id: str = None) -> str:
        """
        Process user query using OpenAI with function calling capabilities
        Limited to maximum 3 function calls per query to prevent excessive API usage
        Enhanced with language detection and proper conversation history handling
        NOW INCLUDES: AI-based message relevance checking - only responds to water delivery related queries
        Enhanced with brand extraction and better context handling
        """
        print(f"Processing query: {user_message} (Language: {user_language})")
        
        # STEP 1: Check if message is relevant to water delivery services
        print("🔍 Checking message relevance...")
        is_relevant = await self._classify_message_relevance(user_message, conversation_history, user_language)
        
        if not is_relevant:
            print(f"❌ Message not relevant to water delivery services: {user_message}...")
            # Return None or empty string to indicate the agent should not reply
            return ""
        
        print("✅ Message is relevant to water delivery services")

        # STEP 2: Check for total price questions - redirect to app/website
        if self._check_for_total_price_question(user_message):
            if user_language == 'ar':
                return "بتحصل الاصناف والاسعار في التطبيق وهذا هو الرابط https://onelink.to/abar_app https://abar.app/en/store/ وايضا عن طريق الموقع الالكتروني"
            else:
                return "You can find all products and prices in our app: https://onelink.to/abar_app or on our website: https://abar.app/en/store/"

        # STEP 3: Check if this is a "yes" response to a previous product question
        if self._check_for_yes_response(user_message, conversation_history):
            print("✅ Detected 'yes' response - handling product confirmation")
        
        max_function_calls = 5
        function_call_count = 0
        
        try:
            # Check if we already have city information from current message or conversation history
            city_context = self._extract_city_from_context(user_message, conversation_history)
            
            # Check if we have brand information
            brand_context = self._extract_brand_from_context(
                user_message, 
                conversation_history, 
                city_context.get("city_id") if city_context else None
            )
            
            # Prepare conversation history
            messages = []
            
            # System message with instructions based on user language
            city_info = ""
            brand_info = ""
            
            if city_context:
                found_where = "current message" if city_context['found_in'] == "current_message" else "conversation history"
                city_info = f"\n\nIMPORTANT CONTEXT: The customer is from {city_context['city_name_en']} ({city_context['city_name']}) - detected from {found_where}. You already know their city, so you can show products and brands for this city without asking again."
            
            if brand_context:
                found_where = "current message" if brand_context['found_in'] == "current_message" else "conversation history"
                brand_info = f"\n\nBRAND CONTEXT: The customer mentioned '{brand_context['brand_title']}' - detected from {found_where}. If you know both city and brand, you can directly show products for this brand in this city."
            
            if user_language == 'en':
                system_message = {
                    "role": "system",
                    "content": f"""You are a friendly customer service employee at Abar Water Delivery Company in Saudi Arabia.{city_info}{brand_info}

Your job is to help customers with:
1. Finding available cities for water delivery service
2. Showing water brands available in each city
3. Displaying water products and their prices from each brand
4. Answering questions naturally and helpfully
5. Asking friendly questions when you need more information

Communication Style:
- Talk like a real human customer service representative
- Be natural, warm, and conversational
- Never use phrases like "AI response", "Assistant reply", or "I am an AI"
- Respond as if you're a real person working for the company

ENHANCED WORKFLOW - SMART CONTEXT EXTRACTION:
🚨 ALWAYS follow this sequence but use extracted context: CITY → BRAND → PRODUCTS → RESPONSE

SMART BRAND HANDLING:
- If customer mentions ONLY a brand name (e.g., "Nestle", "Aquafina"), extract city from context
- If you know BOTH city and brand: directly show products for that brand in that city
- If you know brand but NOT city: ask for city, then show products
- If customer says "yes" after you asked about a product: provide the price/details

CITY DETECTION PRIORITY:
1. Check if city is mentioned in current user message
2. Check if city is available in conversation history context
3. If NO city found in either - IMMEDIATELY ask for city before proceeding

BRAND DETECTION PRIORITY:
1. Check if brand is mentioned in current user message
2. Check if brand is available in conversation history context
3. If brand is mentioned but city unknown - ask for city
4. If both city and brand known - show products directly

PROACTIVE HANDLING:
- "Nestle" + known city → Show Nestle products in that city
- "Aquafina" + no known city → "Which city are you in? I'll show you Aquafina products there!"
- "yes" after product question → Provide price and details
- General price questions → Direct to app/website links

🚨 PRICE INQUIRY HANDLING - CRITICAL INSTRUCTIONS:
When customers ask about prices of ANY product or service:
1. ALWAYS ensure you know the CITY first
   - If city is unknown: Ask "Which city are you in? I need to know your location to show accurate prices."
   - Use extracted city context if available
2. ALWAYS ensure you know the BRAND/COMPANY first
   - If brand is unknown: Ask "Which brand are you interested in? I'll show you their prices in your city."
   - Use extracted brand context if available
3. ONLY after you have BOTH city AND brand → Use get_products_by_brand function to get specific prices for that brand
4. If customer asks for general prices without specifying brand/city → Always ask for both before providing any price information

Never provide generic or estimated prices. Always get specific product prices for the exact brand in the specific city.

ORDER REQUESTS - REDIRECT TO APP:
When user wants to place an order, make a purchase, or asks how to order, ALWAYS redirect them to the app/website with this message:
"You can find all products, prices, and place orders through our app: https://onelink.to/abar_app or on our website: https://abar.app/en/store/"
- Never try to take orders through the chat
- Never ask for delivery details, payment info, or personal information
- Always direct them to the official app/website for ordering

Important rules:
- Always use available functions to get updated information
- For city queries: try get_city_id_by_name first, if fails use search_cities
- Be patient with typos and spelling variations
- Respond in English since the customer is communicating in English
- Keep responses helpful and conversational like a real person would
- Use context smartly - don't ask for information you already have

Be helpful, understanding, and respond exactly like a friendly human employee would."""
                }

                    
                # Check user message and conversation history for size-related keywords (English)
                all_conversation_text = user_message
                if conversation_history:
                    for msg in conversation_history[-5:]:  # Check last 5 messages
                        all_conversation_text += " " + msg.get("content", "")
                
                if "quarter" in all_conversation_text or "half" in all_conversation_text or "riyal" in all_conversation_text:
                    system_message["content"] += "\n\nAdditional info: Quarter size = 200ml or 250ml, Half size = 330ml or 300ml, Riyal size = 600ml or 550ml, Two Riyal size = 1.5L"
                if "groundwater" in all_conversation_text or "artesian" in all_conversation_text:
                    system_message["content"] += (
                        "\n\nAdditional info: Groundwater/artesian water brands include: "
                        "Nova, Naqi, Berrin, Mawared, B, Vio, Miles, Aquaya, Aqua 8, Mana, Tania, Abar Hail, Oska, Nestle, Ava, Hena, Saqya Al Madina, Deman, Hani, Sahtak, Halwa, Athb, Aus, Qataf, Rest, Eval, We."
                    )
                if "gallon" in all_conversation_text:
                    system_message["content"] += (
                        "\n\nGallon exchange services available in:\n"
                        "Tania – Riyadh\n"
                        "Safia – Riyadh\n"
                        "Yanabee Al Mahbooba – Medina"
                    )
            else:
                city_info_ar = ""
                brand_info_ar = ""
                
                if city_context:
                    found_where_ar = "الرسالة الحالية" if city_context['found_in'] == "current_message" else "تاريخ المحادثة"
                    city_info_ar = f"\n\nسياق مهم: العميل من {city_context['city_name']} ({city_context['city_name_en']}) - تم اكتشافها من {found_where_ar}. أنت تعرف مدينتهم بالفعل، لذا يمكنك عرض المنتجات والعلامات التجارية لهذه المدينة بدون السؤال مرة أخرى."
                
                if brand_context:
                    found_where_ar = "الرسالة الحالية" if brand_context['found_in'] == "current_message" else "تاريخ المحادثة"
                    brand_info_ar = f"\n\nسياق العلامة التجارية: العميل ذكر '{brand_context['brand_title']}' - تم اكتشافها من {found_where_ar}. إذا كنت تعرف المدينة والعلامة التجارية، يمكنك عرض منتجات هذه العلامة في هذه المدينة مباشرة."
                
                system_message = {
                    "role": "system",
                    "content": f"""أنت موظف خدمة عملاء ودود في شركة أبار لتوصيل المياه في السعودية.{city_info_ar}{brand_info_ar}

وظيفتك مساعدة العملاء في:
1. إيجاد المدن المتاحة لخدمة توصيل المياه
2. عرض العلامات التجارية للمياه المتاحة في كل مدينة  
3. عرض منتجات المياه وأسعارها من كل علامة تجارية
4. الإجابة على الأسئلة بطريقة طبيعية ومفيدة
5. طرح أسئلة ودودة عندما تحتاج معلومات أكثر

أسلوب التواصل:
- تكلم مثل موظف خدمة عملاء حقيقي
- كن طبيعي وودود ومحادثي
- لا تستخدم أبداً عبارات مثل "رد الذكاء الاصطناعي" أو "رد المساعد" أو "أنا ذكاء اصطناعي"
- رد كأنك شخص حقيقي يعمل في الشركة

سير العمل المحسن - استخراج السياق الذكي:
🚨 اتبع دائماً هذا التسلسل لكن استخدم السياق المستخرج: المدينة → العلامة التجارية → المنتجات → الرد

🚨 تعليمات صارمة حول الأحجام - مهم جداً:
- "ابو ربع" = حجم ٢٠٠-٢٥٠ مل (ليس علامة تجارية)
- "ابو نص" = حجم ٣٣٠-٣٠٠ مل (ليس علامة تجارية)  
- "ابو ريال" = حجم ٦٠٠-٥٥٠ مل (ليس علامة تجارية)
- "ابو ريالين" = حجم ١.٥ لتر (ليس علامة تجارية)

هذه كلها أحجام مياه وليست أسماء علامات تجارية على الإطلاق. لا تحاول البحث عنها كعلامات تجارية أبداً.
عندما يذكرها المستخدم، افهم أنه يتكلم عن حجم المياه وليس عن علامة تجارية.
المستخدمون عادة يسألون عن أسعار هذه الأحجام وليس عن وجودها.

التعامل الذكي مع العلامات التجارية:
- إذا ذكر العميل علامة تجارية فقط (مثل "نستله"، "أكوافينا")، استخرج المدينة من السياق
- إذا كنت تعرف المدينة والعلامة التجارية: اعرض منتجات هذه العلامة في هذه المدينة مباشرة
- إذا كنت تعرف العلامة التجارية لكن لا تعرف المدينة: اسأل عن المدينة، ثم اعرض المنتجات
- إذا قال العميل "نعم" بعد أن سألت عن منتج: قدم السعر والتفاصيل
- إذا سأل العميل عن السعر بدون ذكر العلامة التجارية: اسأل عن العلامة التجارية أولاً

أولوية اكتشاف المدينة:
1. تحقق إذا كانت المدينة مذكورة في رسالة العميل الحالية
2. تحقق إذا كانت المدينة متوفرة في سياق تاريخ المحادثة
3. إذا لم تجد مدينة في أي منهما - اسأل فوراً عن المدينة قبل المتابعة
- استخدم هذه العبارة للسؤال عن المدينة: "انت متواجد باي مدينة طال عمرك؟"

أولوية اكتشاف العلامة التجارية:
1. تحقق إذا كانت العلامة التجارية مذكورة في رسالة العميل الحالية
2. تحقق إذا كانت العلامة التجارية متوفرة في سياق تاريخ المحادثة
3. إذا ذكرت العلامة التجارية لكن المدينة غير معروفة - اسأل عن المدينة
4. إذا كنت تعرف المدينة والعلامة التجارية - اعرض المنتجات مباشرة
5. عند الحاجة لمعرفة اسم العلامة التجارية ولا يمكنك استخراجها من الرسالة الحالية أو التاريخ، اسأل عنها مباشرة
- استخدم هذه العبارة للسؤال عن العلامة التجارية: "اي ماركة او شركة تريد طال عمرك؟"

التعامل الاستباقي:
- "نستله" + مدينة معروفة → اعرض منتجات نستله في هذه المدينة
- "أكوافينا" + مدينة غير معروفة → "انت متواجد باي مدينة طال عمرك؟ راح أعرض لك منتجات أكوافينا هناك!"
- "نعم" بعد سؤال عن منتج → قدم السعر والتفاصيل
- أسئلة الأسعار العامة → وجه للتطبيق/الموقع
- إذا سأل عن السعر بدون ذكر العلامة التجارية → "اي ماركة او شركة تريد طال عمرك؟"

🚨 التعامل مع استفسارات الأسعار - تعليمات مهمة جداً:
عندما يسأل العملاء عن أسعار أي منتج أو خدمة:
1. تأكد دائماً من معرفة المدينة أولاً
   - إذا كانت المدينة غير معروفة: اسأل "انت متواجد باي مدينة طال عمرك؟ة."
   - استخدم سياق المدينة المستخرج إذا كان متوفراً
2. تأكد دائماً من معرفة العلامة التجارية/الشركة أولاً
   - إذا كانت العلامة التجارية غير معروفة: اسأل "اي ماركة او شركة تريد طال عمرك؟ راح اعرض لك اسعارها في مدينتك."
   - استخدم سياق العلامة التجارية المستخرج إذا كان متوفراً
3. فقط بعد أن تعرف المدينة والعلامة التجارية معاً → استخدم وظيفة get_products_by_brand للحصول على الأسعار المحددة لهذه العلامة التجارية
4. إذا سأل العميل عن أسعار عامة بدون تحديد العلامة التجارية/المدينة → اسأل دائماً عن الاثنين قبل تقديم أي معلومات أسعار

لا تقدم أبداً أسعار تقديرية أو عامة. احصل دائماً على أسعار منتجات محددة للعلامة التجارية المحددة في المدينة المحددة.

طلبات الطلب - التوجيه للتطبيق:
عندما يريد العميل تقديم طلب، أو الشراء، أو يسأل كيف يطلب، وجهه دائماً للتطبيق/الموقع بهذه الرسالة:
"بتحصل الاصناف والاسعار في التطبيق وهذا هو الرابط https://onelink.to/abar_app https://abar.app/en/store/ وايضا عن طريق الموقع الالكتروني"
- لا تحاول أخذ طلبات من خلال المحادثة أبداً
- لا تسأل عن تفاصيل التوصيل أو معلومات الدفع أو المعلومات الشخصية
- وجههم دائماً للتطبيق/الموقع الرسمي للطلب

قواعد مهمة:
- استخدم دائماً الوظائف المتاحة للحصول على معلومات حديثة
- للاستفسارات عن المدن: جرب get_city_id_by_name أولاً، إذا فشل استخدم search_cities
- كن صبور مع الأخطاء الإملائية والتنويعات
- أجب باللغة العربية لأن العميل يتواصل بالعربية
- خلي ردودك مفيدة وودودة مثل أي شخص حقيقي
- استخدم السياق بذكاء - لا تسأل عن معلومات تعرفها بالفعل


كن مساعد ومتفهم ورد تماماً مثل موظف ودود حقيقي."""
                }
            # Check user message and conversation history for size-related keywords
            all_conversation_text = user_message
            if conversation_history:
                for msg in conversation_history[-5:]:  # Check last 5 messages
                    all_conversation_text += " " + msg.get("content", "")
            
            # if "ربع" in all_conversation_text or "نص" in all_conversation_text or "ريال" in all_conversation_text or "ريالين" in all_conversation_text:
            #     system_message["content"] = system_message["content"] + "\n\nمعلومات اضافية: ابو ربع هي المياه بحجم ٢٠٠ مل او ٢٥٠ مل ابو نص هي المياه بحجم  ٣٣٠ او ٣٠٠ مل ابو ريال  هي المياه بحجم  ٦٠٠ مل  او ٥٥٠ مل ابو ريالين هي المياه بحجم  ١.٥ لتر"
            
            if "ابار" in all_conversation_text or "جوفية" in all_conversation_text:
                system_message["content"] += (
                    "\n\nمعلومات إضافية: الآبار الجوفية هي المياه الجوفية المعدنية التي تُستخرج من الأرض وتحتوي على معادن ومواد طبيعية مختلفة."
                    "\n\nوهذه هي العلامات التجارية التي تُعد من منتجات الآبار الجوفية:\n"
                    "نوفا، نقي، بيرين، موارد، بي، فيو، مايلز، أكويا، أكوا 8، مانا، تانيا، آبار حائل، أوسكا، نستله، آفا، هنا، سقيا المدينة، ديمان، هني، صحتك، حلوة، عذب، أوس، قطاف، رست، إيفال، وي."
                )
            if " جوالين" in all_conversation_text or "جالون" in all_conversation_text: 
                system_message["content"] += (
                    "\n\nهذه هي العلامات التي توفر تبديل الجوالين، والمدن التي يتوفر بها التبديل:\n\n"
                    "تانيا – الرياض\n"
                    "صافية – الرياض\n"
                    "ينابيع المحبوبة – المدينة المنورة"
                )
            messages.append(system_message)
            
            # Add conversation history if provided (use last 5 messages to keep context manageable)
            if conversation_history:
                # Filter and add recent conversation history
                recent_history = conversation_history[-5:]  # Last 5 messages for better context
                for msg in recent_history:
                    # Create a clean message without problematic fields
                    clean_msg = {
                        "role": msg.get("role", "user"),
                        "content": msg.get("content", "")
                    }
                    # Skip empty messages
                    if clean_msg["content"].strip():
                        messages.append(clean_msg)
                
                print(f"📚 Added {len([m for m in recent_history if m.get('content', '').strip()])} messages from conversation history")
            
            # Add current user message
            messages.append({"role": "user", "content": user_message})
            
            # Main function calling loop
            while function_call_count < max_function_calls:
                try:
                    # Make request to OpenAI with function calling
                    api_start_time = time.time()
                    
                    # Log the LLM request
                    if LOGGING_AVAILABLE and journey_id:
                        prompt_text = "\n".join([f"{msg['role']}: {msg.get('content', 'Function call')}" for msg in messages[-3:]])  # Last 3 messages for context
                        
                    response = await self._call_openai_with_retry(
                        model="gpt-4",
                        messages=messages,
                        functions=self.function_definitions,
                        function_call="auto",
                        temperature=0.3,
                        max_tokens=800
                    )
                    
                    api_duration = int((time.time() - api_start_time) * 1000)
                    message = response.choices[0].message
                    
                    # Log the LLM response
                    if LOGGING_AVAILABLE and journey_id:
                        function_calls_info = None
                        if message.function_call:
                            function_calls_info = [{
                                "function_name": message.function_call.name,
                                "arguments": message.function_call.arguments
                            }]
                        
                        message_journey_logger.log_llm_interaction(
                            journey_id=journey_id,
                            llm_type="openai",
                            prompt=prompt_text,
                            response=message.content or f"Function call: {message.function_call.name}" if message.function_call else "",
                            model="gpt-4",
                            function_calls=function_calls_info,
                            duration_ms=api_duration,
                            tokens_used={"total_tokens": response.usage.total_tokens if response.usage else None}
                        )
                    
                    # Check if model wants to call a function
                    if message.function_call:
                        function_call_count += 1
                        function_name = message.function_call.name
                        
                        try:
                            function_args = json.loads(message.function_call.arguments)
                        except json.JSONDecodeError:
                            logger.error(f"Invalid function arguments: {message.function_call.arguments}")
                            error_msg = "عذراً، حدث خطأ في معالجة طلبك. الرجاء إعادة صياغة السؤال." if user_language == 'ar' else "Sorry, there was an error processing your request. Please rephrase your question."
                            return error_msg
                        
                        logger.info(f"Calling function #{function_call_count}: {function_name} with args: {function_args}")
                        
                        # Call the requested function
                        if function_name in self.available_functions:
                            try:
                                function_result = self.available_functions[function_name](**function_args)
                                
                                # Add function call and result to conversation
                                messages.append({
                                    "role": "assistant",
                                    "content": None,
                                    "function_call": {
                                        "name": function_name,
                                        "arguments": message.function_call.arguments
                                    }
                                })
                                messages.append({
                                    "role": "function",
                                    "name": function_name,
                                    "content": json.dumps(function_result, ensure_ascii=False)
                                })
                                
                                logger.info(f"Function {function_name} completed successfully")
                                
                            except Exception as func_error:
                                logger.error(f"Function {function_name} failed: {str(func_error)}")
                                # Add error result to conversation
                                messages.append({
                                    "role": "function",
                                    "name": function_name,
                                    "content": json.dumps({"error": f"Function failed: {str(func_error)}"}, ensure_ascii=False)
                                })
                        else:
                            logger.error(f"Unknown function: {function_name}")
                            error_msg = f"خطأ: الوظيفة '{function_name}' غير متاحة." if user_language == 'ar' else f"Error: Function '{function_name}' is not available."
                            return error_msg
                    else:
                        # No function call, return the response
                        final_response = message.content
                        if final_response:
                            logger.info(f"Query completed after {function_call_count} function calls")
                            return final_response
                        else:
                            error_msg = "عذراً، لم أتمكن من معالجة طلبك. الرجاء المحاولة مرة أخرى." if user_language == 'ar' else "Sorry, I couldn't process your request. Please try again."
                            return error_msg
                
                except Exception as api_error:
                    logger.error(f"OpenAI API error: {str(api_error)}")
                    # Return error message instead of fallback
                    error_msg = "عذراً، حدث خطأ في الخدمة. الرجاء المحاولة مرة أخرى." if user_language == 'ar' else "Sorry, there was a service error. Please try again."
                    return error_msg
            
            # If we reached max function calls, get final response
            try:
                final_response = await self._call_openai_with_retry(
                    model="gpt-4",
                    messages=messages,
                    temperature=0.3,
                    max_tokens=400
                )
                
                response_text = final_response.choices[0].message.content
                if response_text:
                    logger.info(f"Final response generated after {function_call_count} function calls")
                    return response_text
                else:
                    max_calls_msg = "تم الوصول للحد الأقصى من العمليات. الرجاء إعادة صياغة السؤال." if user_language == 'ar' else "Maximum operations reached. Please rephrase your question."
                    return max_calls_msg
                    
            except Exception as e:
                logger.error(f"Final response generation failed: {str(e)}")
                error_msg = "عذراً، حدث خطأ في توليد الرد. الرجاء المحاولة مرة أخرى." if user_language == 'ar' else "Sorry, there was an error generating the response. Please try again."
                return error_msg

        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            error_msg = "عذراً، حدث خطأ في معالجة الاستعلام. الرجاء المحاولة مرة أخرى." if user_language == 'ar' else "Sorry, there was an error processing the query. Please try again."
            return error_msg

# Singleton instance
query_agent = QueryAgent() 
