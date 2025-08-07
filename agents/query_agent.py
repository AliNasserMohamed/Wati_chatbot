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
            "get_brands_by_city_name": self.get_brands_by_city_name,
            "get_products_by_brand_and_city_name": self.get_products_by_brand_and_city_name,
            "search_cities": self.search_cities,
            "search_brands_in_city": self.search_brands_in_city,
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
                "description": "Get complete list of all cities we serve with water delivery. Use this when user asks about available cities, locations we serve, or wants to see all cities. Returns city names in Arabic and English.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "get_brands_by_city_name",
                "description": "STEP 1 in workflow: Get all water brands available in a specific city using city name. This handles fuzzy matching for incomplete or misspelled city names. Use this when customer mentions a city and you want to show available brands.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city_name": {
                            "type": "string",
                            "description": "Name of the city in Arabic or English (e.g., 'الرياض', 'Riyadh', 'جدة', 'Jeddah'). Supports partial matches and fuzzy matching."
                        }
                    },
                    "required": ["city_name"]
                }
            },
            {
                "name": "get_products_by_brand_and_city_name",
                "description": "STEP 2 in workflow: Get all water products for a specific brand in a specific city using names. This handles fuzzy matching for incomplete or misspelled brand/city names. Use this when customer has specified both a brand and city.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "brand_name": {
                            "type": "string",
                            "description": "Name of the brand in Arabic or English (e.g., 'نستله', 'Nestle', 'أكوافينا', 'Aquafina'). Supports partial matches."
                        },
                        "city_name": {
                            "type": "string",
                            "description": "Name of the city in Arabic or English (e.g., 'الرياض', 'Riyadh', 'جدة', 'Jeddah'). Supports partial matches."
                        }
                    },
                    "required": ["brand_name", "city_name"]
                }
            },
            {
                "name": "search_cities",
                "description": "Search for cities by name when you need to find cities with fuzzy matching. This helps handle typos or find similar city names when the exact city name is unclear.",
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
                "name": "search_brands_in_city",
                "description": "Search for brands by name within a specific city only. Use this when customer mentions a brand name that might be incomplete or misspelled and you know their city.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "brand_name": {
                            "type": "string",
                            "description": "Brand name to search for (Arabic or English). Supports partial matches."
                        },
                        "city_name": {
                            "type": "string",
                            "description": "City name where to search for brands. This is required - we only search within specific cities."
                        }
                    },
                    "required": ["brand_name", "city_name"]
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

    def _extract_brand_from_context(self, user_message: str, conversation_history: List[Dict] = None, city_name: str = None) -> Optional[Dict[str, Any]]:
        """Extract brand information from current message and conversation history
        IMPORTANT: Only returns brands if city_name is provided (city must be known first)
        IMPORTANT: Ignores size terms like ابو ربع, ابو نص, ابو ريال as they are NOT brand names
        """
        # Do not extract brands without knowing the city first
        if not city_name:
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
                # Get brands only for the specific city using city name
                brands = data_api.get_brands_by_city_name(db, city_name)
                
                # PRIORITY 1: Check current user message first
                if user_message:
                    current_content = user_message.lower()
                    for brand in brands:
                        brand_title = brand.get("title", "").lower()
                        
                        if brand_title and brand_title in current_content:
                            return {
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
            for message in reversed(conversation_history[-5:]):  # Check last 5 messages
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
    
    def get_brands_by_city_name(self, city_name: str) -> Dict[str, Any]:
        """Get brands available in a specific city using city name with fuzzy matching"""
        try:
            db = self._get_db_session()
            try:
                brands = data_api.get_brands_by_city_name(db, city_name)
                if not brands:
                    return {
                        "success": False,
                        "error": f"لم أجد مدينة باسم '{city_name}' أو لا توجد علامات تجارية متاحة في هذه المدينة.",
                        "original_input": city_name
                    }
                
                # Return brands with city information
                filtered_brands = [
                    {
                        "title": brand["title"],                    # Brand name in Arabic
                        "title_en": brand.get("title_en", ""),     # Brand name in English
                        "city_name": brand["city_name"],           # City name in Arabic
                        "city_name_en": brand.get("city_name_en", "")  # City name in English
                    }
                    for brand in brands
                ]
                
                return {
                    "success": True, 
                    "data": filtered_brands,
                    "city_found": brands[0]["city_name"] if brands else city_name
                }
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error fetching brands for city {city_name}: {str(e)}")
            return {"error": f"Failed to get brands: {str(e)}"}
    
    def get_products_by_brand_and_city_name(self, brand_name: str, city_name: str) -> Dict[str, Any]:
        """Get products for a specific brand in a specific city using names with fuzzy matching"""
        try:
            db = self._get_db_session()
            try:
                products = data_api.get_products_by_brand_and_city_name(db, brand_name, city_name)
                if not products:
                    return {
                        "success": False,
                        "error": f"لم أجد منتجات للعلامة التجارية '{brand_name}' في مدينة '{city_name}'. يرجى التحقق من الأسماء أو جرب علامة تجارية أخرى.",
                        "original_brand": brand_name,
                        "original_city": city_name
                    }
                
                # Return products with brand and pricing information
                filtered_products = [
                    {
                        "product_title": product["product_title"],                      # Product name
                        "product_contract_price": product["product_contract_price"],    # Price
                        "product_packing": product["product_packing"],                  # Amount/packaging
                        "brand_title": product["brand_title"],                          # Brand name
                        "brand_title_en": product.get("brand_title_en", "")            # Brand name in English
                    }
                    for product in products
                ]
                
                return {
                    "success": True, 
                    "data": filtered_products,
                    "brand_found": products[0]["brand_title"] if products else brand_name,
                    "total_products": len(filtered_products)
                }
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error fetching products for brand {brand_name} in city {city_name}: {str(e)}")
            return {"error": f"Failed to get products: {str(e)}"}
    
    def search_brands_in_city(self, brand_name: str, city_name: str) -> Dict[str, Any]:
        """Search for brands by name within a specific city only"""
        try:
            db = self._get_db_session()
            try:
                brands = data_api.search_brands_in_city(db, brand_name, city_name)
                if not brands:
                    error_msg = f"لم أجد علامة تجارية باسم '{brand_name}' في مدينة '{city_name}'. يرجى التحقق من الاسم أو جرب علامة تجارية أخرى."
                    
                    return {
                        "success": False,
                        "error": error_msg,
                        "original_brand": brand_name,
                        "original_city": city_name
                    }
                
                # Return found brands
                filtered_brands = [
                    {
                        "title": brand["title"],                    # Brand name in Arabic
                        "title_en": brand.get("title_en", ""),     # Brand name in English
                        "image_url": brand.get("image_url", "")    # Brand image
                    }
                    for brand in brands
                ]
                
                return {
                    "success": True, 
                    "data": filtered_brands,
                    "total_brands": len(filtered_brands)
                }
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error searching brands for {brand_name}: {str(e)}")
            return {"error": f"Failed to search brands: {str(e)}"}
    
    def search_cities(self, query: str) -> Dict[str, Any]:
        """Search cities by name with """
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
        """Check if a brand or product is available in a specific city using name-based approach"""
        try:
            db = self._get_db_session()
            try:
                if item_type == "brand":
                    # Check if brand exists in this city using name-based search
                    brands = data_api.search_brands_in_city(db, item_name, city_name)
                    if brands:
                        return {
                            "success": True,
                            "available": True,
                            "city_name": city_name,
                            "item_type": item_type,
                            "item_name": item_name,
                            "brand_info": {
                                "title": brands[0]["title"],
                                "title_en": brands[0].get("title_en", "")
                            }
                        }
                    
                    return {
                        "success": True,
                        "available": False,
                        "city_name": city_name,
                        "item_type": item_type,
                        "item_name": item_name,
                        "message": f"للأسف، العلامة التجارية '{item_name}' غير متوفرة في {city_name}"
                    }
                
                elif item_type == "product":
                    # Check if product exists by searching brands and their products
                    brands = data_api.get_brands_by_city_name(db, city_name)
                    if not brands:
                        return {
                            "success": False,
                            "error": f"لم أجد مدينة باسم '{city_name}'. يرجى التحقق من الاسم.",
                            "item_type": item_type,
                            "item_name": item_name
                        }
                    
                    found_products = []
                    
                    # Search through each brand's products
                    for brand in brands:
                        # Try to get products using the existing method that requires brand name and city name
                        # We'll search through all brands to find products matching the item_name
                        products = data_api.get_products_by_brand_and_city_name(db, brand["title"], city_name)
                        for product in products:
                            if item_name.lower() in product["product_title"].lower():
                                found_products.append({
                                    "brand_name": product["brand_title"],
                                    "product_title": product["product_title"],
                                    "product_contract_price": product["product_contract_price"],
                                    "product_packing": product["product_packing"]
                                })
                    
                    if found_products:
                        return {
                            "success": True,
                            "available": True,
                            "city_name": city_name,
                            "item_type": item_type,
                            "item_name": item_name,
                            "products": found_products
                        }
                    else:
                        return {
                            "success": True,
                            "available": False,
                            "city_name": city_name,
                            "item_type": item_type,
                            "item_name": item_name,
                            "message": f"للأسف، المنتج '{item_name}' غير متوفر في {city_name}"
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
                recent_messages = conversation_history[-5:]  # Last 5 messages for context
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
                model="gpt-4o-mini",
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
                city_context.get("city_name") if city_context else None
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

🚨 ENHANCED CONVERSATION HISTORY ATTENTION - CRITICAL:
- Always thoroughly review conversation history to find previously mentioned cities and brands
- Search through the last 10 messages for any mention of city names or brand names
- Do not ask for information that already exists in conversation history
- Use extracted information from history even if it's from older messages

CITY DETECTION PRIORITY - WITH STRONG FOCUS ON HISTORY:
1. Check if city is mentioned in current user message
2. 🚨 Search thoroughly through conversation history (last 10 messages) for any city mentions
3. Only if NO city found in current message OR history - ask for city
- Use this phrase to ask about city: "Which city are you in? I need to know your location."

BRAND DETECTION PRIORITY - WITH STRONG FOCUS ON HISTORY:
1. Check if brand is mentioned in current user message
2. 🚨 Search thoroughly through conversation history (last 10 messages) for any brand mentions
3. If brand is mentioned but city unknown - ask for city
4. If both city and brand known - show products directly
5. Only if NO brand found in current message OR history - ask for brand

🚨 SPECIAL HANDLING FOR PRICE QUESTIONS - CRITICAL INSTRUCTIONS:
When customer asks about prices with "how much" or "what's the price":
- The word after "how much" or "what's the price of" is usually either a brand or size
- If you don't understand the word that comes after price questions, it's likely a brand name
- Use search_brands_in_city function to search for the brand in the known city
- Examples: "How much is Nestle?" - "What's the price of Aquafina?" - "How much Volvic?"
- Even if the brand name is misspelled or unfamiliar, try searching for it

PROACTIVE HANDLING:
- "Nestle" + known city → Show Nestle products in that city
- "Aquafina" + no known city → "Which city are you in? I'll show you Aquafina products there!"
- "yes" after product question → Provide price and details
- General price questions → Direct to app/website links
- "How much [unknown word]?" → Try searching it as a brand name first

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

🚨 SPECIFIC BUSINESS RULES - CRITICAL:

1. APARTMENT DOOR DELIVERY:
   - When customer specifically asks about delivery TO THE APARTMENT DOOR (not general delivery), answer: "We deliver to apartment doors if there is an elevator, and if there is no elevator we deliver to the 1st, 2nd, and 3rd floors maximum with a request to add a note with your order through the app."

2. JUG EXCHANGE SERVICE:
   - Jug exchange is ONLY available in specified cities, not outside them
   - Jug exchange is NOT available for Al-Manhal brand yet
   - Always mention these limitations when discussing jug exchange

3. BRANCHES QUESTION:
   - If customer asks if we have branches: "We don't have physical branches, but we deliver to many cities."

4. PRICE DISPUTES:
   - If customer asks about product price and claims it's available at a lower price elsewhere, DO NOT agree or confirm lower prices
   - ONLY provide prices from our official data - never generate or estimate prices
   - Always use the get_products_by_brand function for accurate pricing information

Important rules:
- Always use available functions to get updated information
- For city queries: use search_cities to handle typos and fuzzy matching
- Be patient with typos and spelling variations
- Respond in English since the customer is communicating in English
- Keep responses helpful and conversational like a real person would
- Use context smartly - don't ask for information you already have

🚨 CRITICAL RULE - USE NAMES, NOT IDs:
- NEVER mention or use internal database ID numbers in your responses
- ALWAYS work with city names and brand names directly
- Use get_brands_by_city_name to get brands for a specific city by name
- Use get_products_by_brand_and_city_name to get products for a brand in a city by names
- Use search_brands_in_city to find brands with fuzzy matching
- The system handles incomplete and misspelled names automatically
- Always use descriptive names that customers understand

🚨 DISPLAY ALL PRODUCTS - CRITICAL:
- When showing products for a specific brand, you MUST display ALL products without exception
- Do not abbreviate or limit to only some products
- Show the complete list of all available products for the brand in the city
- Ensure you display product name, size, and price for each product

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

🚨 الانتباه الفائق لتاريخ المحادثة - مهم جداً:
- راجع دائماً تاريخ المحادثة بعناية للعثور على المدن والعلامات التجارية المذكورة سابقاً
- ابحث في آخر 5 رسائل للعميل والمساعد عن أي ذكر لأسماء المدن أو العلامات التجارية
- لا تسأل عن معلومات موجودة بالفعل في تاريخ المحادثة
- استخدم المعلومات المستخرجة من التاريخ حتى لو كانت من رسائل قديمة

سير العمل المحسن - استخراج السياق الذكي:
🚨 اتبع دائماً هذا التسلسل مع الانتباه الشديد لتاريخ المحادثة: المدينة → العلامة التجارية → المنتجات → الرد

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

أولوية اكتشاف المدينة - مع التركيز القوي على التاريخ:
1. تحقق إذا كانت المدينة مذكورة في رسالة العميل الحالية
2. 🚨 ابحث بعناية فائقة في تاريخ المحادثة (آخر 5 رسائل) عن أي ذكر لأسماء المدن
3. فقط إذا لم تجد مدينة في الرسالة الحالية أو في تاريخ المحادثة - اسأل عن المدينة
- استخدم هذه العبارة للسؤال عن المدينة: "انت متواجد باي مدينة طال عمرك؟"

أولوية اكتشاف العلامة التجارية - مع التركيز القوي على المحادثة :
1. تحقق إذا كانت العلامة التجارية مذكورة في رسالة العميل الحالية
2. 🚨 ابحث بعناية فائقة في تاريخ المحادثة (آخر 10 رسائل) عن أي ذكر لأسماء العلامات التجارية
3. إذا ذكرت العلامة التجارية لكن المدينة غير معروفة - اسأل عن المدينة
4. إذا كنت تعرف المدينة والعلامة التجارية - اعرض المنتجات مباشرة
5. فقط إذا لم تجد علامة تجارية في الرسالة الحالية أو في تاريخ المحادثة - اسأل عنها
- استخدم هذه العبارة للسؤال عن العلامة التجارية: "اي ماركة او شركة تريد طال عمرك؟"

🚨 التعامل الخاص مع أسئلة الأسعار - تعليمات مهمة جداً:
عندما يسأل العميل بـ "كم" أو "بكم":
- ما بعد "كم" أو "بكم" يكون إما علامة تجارية أو حجم
- إذا لم تفهم الكلمة التي تأتي بعد "كم" أو "بكم"، فهي على الأغلب علامة تجارية
- استخدم وظيفة search_brands_in_city للبحث عن العلامة التجارية في المدينة المعروفة
- أمثلة: "كم نستله؟" - "بكم أكوافينا؟" - "كم فولفيك؟"
- حتى لو كانت العلامة التجارية مكتوبة خطأ أو غير مألوفة، جرب البحث عنها

التعامل الاستباقي:
- "نستله" + مدينة معروفة → اعرض منتجات نستله في هذه المدينة
- "أكوافينا" + مدينة غير معروفة → "انت متواجد باي مدينة طال عمرك؟ راح أعرض لك منتجات أكوافينا هناك!"
- "نعم" بعد سؤال عن منتج → قدم السعر والتفاصيل
- أسئلة الأسعار العامة → وجه للتطبيق/الموقع
- إذا سأل عن السعر بدون ذكر العلامة التجارية → "اي ماركة او شركة تريد طال عمرك؟"
- "كم [كلمة غير مفهومة]؟" → جرب البحث عنها كعلامة تجارية أولاً

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

🚨 قواعد العمل المحددة - مهمة جداً:

1. التوصيل لباب الشقة:
   - عندما يسأل العميل عن التوصيل لباب الشقة تحديداً (وليس التوصيل بشكل عام)، أجب: "نحن نوصل لباب الشقة إذا كان هناك اسانسير، وإذا لم يكن هناك اسانسير فنحن نوصل للدور الأول والثاني والثالث بحد أقصى مع طلب إضافة ملاحظة مع الطلب من خلال التطبيق"

2. تبديل الجوالين:
   - التبديل لدينا يتم فقط في المدن المحددة وليس خارجها
   - لا يتوفر لدينا تبديل لماركة المنهل حتى الآن

3. سؤال الفروع:
   - إذا سأل العميل هل لدينا فروع: "نحن ليس لدينا فروع ولكن نوصل للعديد من المدن"

4. خلافات الأسعار:
   - إذا سأل العميل عن سعر منتج وقال المستخدم أنه بسعر أقل، لا يجب أن ترد بأنه فعلاً بسعر أقل
   - يأخذ البوت الأسعار من الداتا المحددة به فقط ولا يقوم بجلب أي أسعار من نفسه
   - استخدم دائماً وظيفة get_products_by_brand للحصول على معلومات الأسعار الدقيقة

قواعد مهمة:
- استخدم دائماً الوظائف المتاحة للحصول على معلومات حديثة
- للاستفسارات عن المدن: استخدم search_cities للتعامل مع الأخطاء الإملائية والمطابقة الضبابية
- كن صبور مع الأخطاء الإملائية والتنويعات
- أجب باللغة العربية لأن العميل يتواصل بالعربية
- خلي ردودك مفيدة وودودة مثل أي شخص حقيقي
- استخدم السياق بذكاء - لا تسأل عن معلومات تعرفها بالفعل

🚨 قاعدة مهمة جداً - استخدم الأسماء وليس المعرفات:
- لا تذكر أبداً أو تستخدم أرقام معرفات قاعدة البيانات الداخلية في ردودك
- اعمل دائماً مع أسماء المدن وأسماء العلامات التجارية مباشرة
- استخدم get_brands_by_city_name للحصول على العلامات التجارية لمدينة معينة بالاسم
- استخدم get_products_by_brand_and_city_name للحصول على المنتجات لعلامة تجارية في مدينة بالأسماء
- استخدم search_brands_in_city للبحث عن العلامات التجارية مع المطابقة الضبابية
- النظام يتعامل مع الأسماء الناقصة والمكتوبة خطأ تلقائياً
- استخدم دائماً أسماء وصفية يفهمها العملاء

🚨 عرض جميع المنتجات - مهم جداً:
- عندما تعرض منتجات علامة تجارية معينة، يجب عرض جميع المنتجات بلا استثناء
- لا تختصر أو تقتصر على بعض المنتجات فقط
- اعرض القائمة الكاملة لجميع المنتجات المتاحة للعلامة التجارية في المدينة
- تأكد من عرض اسم المنتج والحجم والسعر لكل منتج

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
            if " جوالين" in all_conversation_text or "جالون" in all_conversation_text or "تبديل" in all_conversation_text: 
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
                        prompt_text = "\n".join([f"{msg['role']}: {msg.get('content', 'Function call')}" for msg in messages[-5:]])  # Last 5 messages for context
                        
                    response = await self._call_openai_with_retry(
                        model="gpt-4o-mini",
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
                            model="gpt-4o-mini",
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
                                # Record function call start time for duration measurement
                                func_start_time = time.time()
                                
                                function_result = self.available_functions[function_name](**function_args)
                                
                                # Calculate function execution duration
                                func_duration = int((time.time() - func_start_time) * 1000)
                                
                                # Log the function call and response in detail
                                if LOGGING_AVAILABLE and journey_id:
                                    message_journey_logger.log_function_call(
                                        journey_id=journey_id,
                                        function_name=function_name,
                                        function_args=function_args,
                                        function_result=function_result,
                                        duration_ms=func_duration,
                                        status="completed"
                                    )
                                
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
                                # Calculate function execution duration even for errors
                                func_duration = int((time.time() - func_start_time) * 1000) if 'func_start_time' in locals() else None
                                
                                logger.error(f"Function {function_name} failed: {str(func_error)}")
                                
                                # Log the function error in detail
                                if LOGGING_AVAILABLE and journey_id:
                                    message_journey_logger.log_function_call(
                                        journey_id=journey_id,
                                        function_name=function_name,
                                        function_args=function_args,
                                        function_result=None,
                                        duration_ms=func_duration,
                                        status="failed",
                                        error=str(func_error)
                                    )
                                
                                # Add error result to conversation
                                error_result = {"error": f"Function failed: {str(func_error)}"}
                                messages.append({
                                    "role": "function",
                                    "name": function_name,
                                    "content": json.dumps(error_result, ensure_ascii=False)
                                })
                        else:
                            logger.error(f"Unknown function: {function_name}")
                            
                            # Log the unknown function call
                            if LOGGING_AVAILABLE and journey_id:
                                message_journey_logger.log_function_call(
                                    journey_id=journey_id,
                                    function_name=function_name,
                                    function_args=function_args,
                                    function_result=None,
                                    status="failed",
                                    error=f"Unknown function: {function_name}"
                                )
                            
                            error_msg = f"خطأ: الوظيفة '{function_name}' غير متاحة." if user_language == 'ar' else f"Error: Function '{function_name}' is not available."
                            return error_msg
                    else:
                        # No function call, return the response
                        final_response = message.content
                        if final_response:
                            logger.info(f"Query completed after {function_call_count} function calls")
                            
                            # Log successful query completion
                            if LOGGING_AVAILABLE and journey_id:
                                message_journey_logger.add_step(
                                    journey_id=journey_id,
                                    step_type="query_completion",
                                    description=f"Query completed successfully with {function_call_count} function calls",
                                    data={
                                        "total_function_calls": function_call_count,
                                        "final_response_length": len(final_response),
                                        "completion_status": "success",
                                        "completion_method": "natural_completion"
                                    }
                                )
                            
                            return final_response
                        else:
                            error_msg = "عذراً، لم أتمكن من معالجة طلبك. الرجاء المحاولة مرة أخرى." if user_language == 'ar' else "Sorry, I couldn't process your request. Please try again."
                            
                            # Log empty response error
                            if LOGGING_AVAILABLE and journey_id:
                                message_journey_logger.add_step(
                                    journey_id=journey_id,
                                    step_type="query_completion",
                                    description="Query failed - empty response from LLM",
                                    data={
                                        "total_function_calls": function_call_count,
                                        "completion_status": "failed",
                                        "error": "Empty response from LLM"
                                    },
                                    status="failed"
                                )
                            
                            return error_msg
                
                except Exception as api_error:
                    logger.error(f"OpenAI API error: {str(api_error)}")
                    # Return error message instead of fallback
                    error_msg = "عذراً، حدث خطأ في الخدمة. الرجاء المحاولة مرة أخرى." if user_language == 'ar' else "Sorry, there was a service error. Please try again."
                    return error_msg
            
            # If we reached max function calls, get final response
            try:
                final_api_start_time = time.time()
                
                final_response = await self._call_openai_with_retry(
                    model="gpt-4o-mini",
                    messages=messages,
                    temperature=0.3,
                    max_tokens=400
                )
                
                final_api_duration = int((time.time() - final_api_start_time) * 1000)
                response_text = final_response.choices[0].message.content
                
                # Log final response generation
                if LOGGING_AVAILABLE and journey_id:
                    message_journey_logger.log_llm_interaction(
                        journey_id=journey_id,
                        llm_type="openai",
                        prompt="Final response generation after function calls",
                        response=response_text or "No response generated",
                        model="gpt-4o-mini",
                        duration_ms=final_api_duration,
                        tokens_used={"total_tokens": final_response.usage.total_tokens if final_response.usage else None}
                    )
                
                if response_text:
                    logger.info(f"Final response generated after {function_call_count} function calls")
                    
                    # Log query completion summary
                    if LOGGING_AVAILABLE and journey_id:
                        message_journey_logger.add_step(
                            journey_id=journey_id,
                            step_type="query_completion",
                            description=f"Query completed with {function_call_count} function calls",
                            data={
                                "total_function_calls": function_call_count,
                                "final_response_length": len(response_text),
                                "completion_status": "success"
                            }
                        )
                    
                    return response_text
                else:
                    max_calls_msg = "تم الوصول للحد الأقصى من العمليات. الرجاء إعادة صياغة السؤال." if user_language == 'ar' else "Maximum operations reached. Please rephrase your question."
                    
                    # Log max calls reached
                    if LOGGING_AVAILABLE and journey_id:
                        message_journey_logger.add_step(
                            journey_id=journey_id,
                            step_type="query_completion",
                            description="Query terminated - maximum function calls reached",
                            data={
                                "total_function_calls": function_call_count,
                                "completion_status": "max_calls_reached"
                            }
                        )
                    
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
