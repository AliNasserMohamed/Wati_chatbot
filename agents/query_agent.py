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
    """
    
    def __init__(self):
        self.api_base_url = "http://localhost:8000/api"
        
        # Initialize OpenAI client
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        
        self.openai_client = AsyncOpenAI(api_key=openai_api_key)
        
        # Define available functions for the LLM
        self.available_functions = {
            "get_all_cities": self.get_all_cities,
            "get_city_id_by_name": self.get_city_id_by_name,
            "get_brands_by_city": self.get_brands_by_city,
            "get_products_by_brand": self.get_products_by_brand,
            "get_products_by_brand_and_city": self.get_products_by_brand_and_city,
            "search_cities": self.search_cities,
            "check_city_availability": self.check_city_availability,
            "calculate_total_price": self.calculate_total_price,
            "find_brand_in_city": self.find_brand_in_city
        }
        
        # Async functions that need special handling
        self.async_functions = {
            "check_city_availability",
            "get_products_by_brand_and_city",
            "find_brand_in_city"
        }
        
        # Classification prompts for message relevance
        self.classification_prompt_ar = """أنت مصنف رسائل ذكي لشركة توصيل المياه. مهمتك تحديد ما إذا كانت الرسالة متعلقة بخدمات الشركة أم لا.

الرسائل المتعلقة بالخدمة تشمل فقط:
✅ أسئلة عن المدن المتاحة للتوصيل
✅ أسئلة عن العلامات التجارية للمياه
✅ أسئلة عن المنتجات والأسعار
✅ طلبات معرفة التوفر في مدينة معينة
✅ أسئلة عن أحجام المياه والعبوات
✅ الاستفسار عن خدمة التوصيل
✅ أسئلة عن شركات المياه

الرسائل غير المتعلقة بالخدمة تشمل:

❌ المواضيع العامة غير المتعلقة بالمياه
❌ الأسئلة الشخصية
❌ طلبات المساعدة في مواضيع أخرى
❌ الرسائل التي تحتوي على روابط

تعليمات خاصة:
- لا تعتبر التحيات والشكر متعلقة بالخدمة حتى لو كانت في سياق محادثة عن المياه
- كن صارم في التصنيف - فقط الأسئلة المباشرة عن المدن والعلامات والمنتجات تعتبر متعلقة

أجب بـ "relevant" إذا كانت الرسالة متعلقة بخدمات المياه، أو "not_relevant" إذا لم تكن متعلقة."""

        self.classification_prompt_en = """You are a smart message classifier for a water delivery company. Your task is to determine if a message is related to the company's services or not.

Service-related messages include ONLY:
✅ Questions about available cities for delivery
✅ Questions about water brands
✅ Questions about products and prices
✅ Requests to check availability in specific cities
✅ Questions about water sizes and packaging
✅ Inquiries about delivery service
✅ Questions about water companies

Non-service-related messages include:
❌ General greetings ("hello", "hi", "good morning", "good evening", "how are you")
❌ Thank you messages ("thanks", "thank you", "appreciate it", "much obliged")
❌ General topics not related to water
❌ Personal questions
❌ Requests for help with other topics
❌ Messages containing links or URLs

Special instructions:
- Do not consider greetings and thanks as service-related even if they appear in water-related conversations
- Be strict in classification - only direct questions about cities, brands, and products count as relevant

Reply with "relevant" if the message is related to water services, or "not_relevant" if it's not related."""
        
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
                "description": "Check if a product or brand is available in a specific city. NOW WITH AI-POWERED EXTRACTION: Handles variations like 'امياه حلوه' or 'موية حلوه' to extract correct brand names. Use this when user asks about product/brand availability.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city_name": {
                            "type": "string",
                            "description": "Name of the city in Arabic or English (AI will extract correct city name from variations)"
                        },
                        "item_type": {
                            "type": "string",
                            "description": "Type of item being checked: 'brand' or 'product'",
                            "enum": ["brand", "product"]
                        },
                        "item_name": {
                            "type": "string",
                            "description": "Name of the brand or product as user typed it (AI will extract correct brand name from variations like 'امياه حلوه' → 'حلوه')"
                        }
                    },
                    "required": ["city_name", "item_type", "item_name"]
                }
            },
            {
                "name": "find_brand_in_city",
                "description": "Find if a specific brand exists in a known city and get its products. NOW WITH AI-POWERED EXTRACTION: Handles variations like 'امياه حلوه' → 'حلوه'. Use this when customer mentions ONLY a brand name and you already know their city from context.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "brand_name": {
                            "type": "string",
                            "description": "Name of the brand as customer typed it (e.g., 'أكوافينا', 'امياه حلوه', 'موية نوفا') - AI will extract correct brand name"
                        },
                        "city_id": {
                            "type": "integer",
                            "description": "ID of the city where to search for the brand (must be known from context)"
                        }
                    },
                    "required": ["brand_name", "city_id"]
                }
            },
            {
                "name": "get_products_by_brand_and_city",
                "description": "Get all products from a specific brand in a specific city. NOW WITH AI-POWERED EXTRACTION: Handles brand variations like 'امياه حلوه' → 'حلوه' and city variations. Use this when you know both the brand name and city.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "brand_name": {
                            "type": "string",
                            "description": "Name of the brand as customer typed it (AI will extract correct brand name from variations)"
                        },
                        "city_name": {
                            "type": "string", 
                            "description": "Name of the city in Arabic or English (AI will extract correct city name from variations)"
                        }
                    },
                    "required": ["brand_name", "city_name"]
                }
            },
            {
                "name": "calculate_total_price",
                "description": "Calculate total price when customer asks about cost for specific quantities (e.g., '5 bottles', '10 units'). IMPORTANT: API prices are per CARTON/BOX, not per individual unit. So if customer wants 5 cartons, multiply carton_price × 5.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "unit_price": {
                            "type": "number",
                            "description": "Price per CARTON/BOX from API (NOT per individual bottle) in SAR"
                        },
                        "quantity": {
                            "type": "integer", 
                            "description": "Number of CARTONS customer wants (NOT individual units)"
                        },
                        "product_name": {
                            "type": "string",
                            "description": "Name of the product being calculated"
                        }
                    },
                    "required": ["unit_price", "quantity", "product_name"]
                }
            }
        ]
    
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
    
    def _extract_brand_from_message(self, user_message: str) -> Optional[str]:
        """Extract brand name from user message if mentioned"""
        try:
            db = self._get_db_session()
            try:
                # Get all brands to check against
                all_brands = data_api.get_all_brands(db)
                
                message_lower = user_message.lower()
                
                # Check if any brand name appears in the message
                for brand in all_brands:
                    brand_title = brand.get("title", "").lower()
                    if brand_title and brand_title in message_lower:
                        return brand["title"]  # Return original case brand name
                
                # Check for common Arabic brand name variations
                brand_mappings = {
                    "اكوافينا": "أكوافينا",
                    "نوفا": "نوفا", 
                    "الهدا": "الهدا",
                    "نستله": "نستلة",
                    "هنا": "هنا",
                    "اروى": "أروى",
                    "بيرين": "بيريه"
                }
                
                for variation, correct_name in brand_mappings.items():
                    if variation in message_lower:
                        return correct_name
                
                return None
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error extracting brand from message: {str(e)}")
            return None
    
    async def _ai_extract_brand_from_message(self, user_message: str) -> Optional[str]:
        """Use AI to intelligently extract brand name from user message"""
        try:
            db = self._get_db_session()
            try:
                # Get all available brands for context
                all_brands = data_api.get_all_brands(db)
                brands_list = [brand.get("title", "") for brand in all_brands if brand.get("title")]
                
                if not brands_list:
                    return None
                
                # Create prompt for brand extraction
                brands_text = "، ".join(brands_list)
                
                prompt = f"""أنت خبير في استخراج أسماء العلامات التجارية للمياه من رسائل العملاء.

العلامات التجارية المتاحة: {brands_text}

رسالة العميل: "{user_message}"

مهمتك:
1. ابحث عن أي إشارة لعلامة تجارية في الرسالة
2. العملاء قد يكتبون "امياه حلوه" أو "موية حلوه" ويقصدون "حلوه"
3. العملاء قد يكتبون أسماء مختصرة أو بأخطاء إملائية
4. إذا وجدت علامة تجارية، أرجع الاسم الصحيح بالضبط كما هو في القائمة
5. إذا لم تجد أي علامة تجارية، أرجع "لا يوجد"

أرجع فقط اسم العلامة التجارية أو "لا يوجد":"""

                response = await self.openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=50
                )
                
                result = response.choices[0].message.content.strip()
                
                # Validate the result against available brands
                if result and result != "لا يوجد":
                    for brand in brands_list:
                        if result.lower() == brand.lower():
                            return brand
                
                return None
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error in AI brand extraction: {str(e)}")
            # Fallback to original method
            return self._extract_brand_from_message_fallback(user_message)
    
    def _extract_brand_from_message_fallback(self, user_message: str) -> Optional[str]:
        """Fallback method for brand extraction (original hardcoded approach)"""
        try:
            db = self._get_db_session()
            try:
                # Get all brands to check against
                all_brands = data_api.get_all_brands(db)
                
                message_lower = user_message.lower()
                
                # Check if any brand name appears in the message
                for brand in all_brands:
                    brand_title = brand.get("title", "").lower()
                    if brand_title and brand_title in message_lower:
                        return brand["title"]  # Return original case brand name
                
                # Check for common Arabic brand name variations
                brand_mappings = {
                    "اكوافينا": "أكوافينا",
                    "نوفا": "نوفا", 
                    "الهدا": "الهدا",
                    "نستله": "نستلة",
                    "هنا": "هنا",
                    "اروى": "أروى",
                    "بيرين": "بيريه",
                    "امياه حلوه": "حلوه",
                    "موية حلوه": "حلوه",
                    "مياه حلوه": "حلوه"
                }
                
                for variation, correct_name in brand_mappings.items():
                    if variation in message_lower:
                        return correct_name
                
                return None
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error extracting brand from message: {str(e)}")
            return None
    
    async def _ai_extract_city_from_message(self, user_message: str) -> Optional[Dict[str, Any]]:
        """Use AI to intelligently extract city name from user message"""
        try:
            db = self._get_db_session()
            try:
                # Get all available cities for context
                all_cities = data_api.get_all_cities(db)
                cities_list = []
                for city in all_cities:
                    city_ar = city.get("name", "")
                    city_en = city.get("name_en", "")
                    if city_ar:
                        cities_list.append(f"{city_ar} ({city_en})")
                
                if not cities_list:
                    return None
                
                # Create prompt for city extraction
                cities_text = "، ".join(cities_list)
                
                prompt = f"""أنت خبير في استخراج أسماء المدن من رسائل العملاء.

المدن المتاحة: {cities_text}

رسالة العميل: "{user_message}"

مهمتك:
1. ابحث عن أي إشارة لمدينة في الرسالة
2. العملاء قد يكتبون بأخطاء إملائية (مثل "رياص" بدلاً من "رياض")
3. العملاء قد يستخدمون أسماء مختصرة أو عامية
4. إذا وجدت مدينة، أرجع الاسم العربي الصحيح بالضبط كما هو في القائمة فقط
5. إذا لم تجد أي مدينة، أرجع "لا يوجد"

أرجع فقط الاسم العربي للمدينة أو "لا يوجد":"""

                response = await self.openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=50
                )
                
                result = response.choices[0].message.content.strip()
                
                # Validate and find the matching city
                if result and result != "لا يوجد":
                    for city in all_cities:
                        if result.lower() == city.get("name", "").lower():
                            return {
                                "city_id": city["id"],
                                "city_name": city["name"],
                                "city_name_en": city["name_en"],
                                "found_in": "ai_extraction"
                            }
                
                return None
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error in AI city extraction: {str(e)}")
            return None
    
    def _extract_quantity_from_message(self, user_message: str) -> Optional[Dict[str, Any]]:
        """Extract quantity information from user message"""
        try:
            import re
            
            # Patterns to match quantities in Arabic and English (focusing on cartons/boxes)
            quantity_patterns = [
                r'(\d+)\s*(?:كرتونة|كراتين|كرتون|عبوة|عبوات|وحدة|وحدات|كيس|أكياس)',  # Arabic - added cartons
                r'(\d+)\s*(?:cartons?|boxes?|packs?|units?|bottles?|pieces?|bags?)',  # English - prioritize cartons
                r'(?:كم\s*سعر|كم\s*يكلف|كم\s*ثمن)\s*(\d+)',  # "How much for X" patterns
                r'(?:أريد|عايز|أبي|ابغي|أشتري)\s*(\d+)',  # "I want X" patterns
                r'(\d+)\s*×',  # Multiplication sign
                r'(\d+)\s*من',  # "X from" pattern
                r'اختار\s*(\d+)',  # "I choose X" pattern
            ]
            
            message_lower = user_message.lower()
            
            for pattern in quantity_patterns:
                match = re.search(pattern, message_lower)
                if match:
                    try:
                        quantity = int(match.group(1))
                        if quantity > 0 and quantity <= 1000:  # Reasonable quantity limits
                            return {
                                "quantity": quantity,
                                "original_text": match.group(0),
                                "pattern_matched": pattern
                            }
                    except ValueError:
                        continue
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting quantity from message: {str(e)}")
            return None
    
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
        """Get city ID by name (helper function) with typo handling"""
        try:
            db = self._get_db_session()
            try:
                # Get all cities and find matching one
                cities = data_api.get_all_cities(db)
                
                # First try exact match (case insensitive)
                for city in cities:
                    # Check if city name matches (case insensitive)
                    if (city_name.lower() in city.get("name", "").lower() or 
                        city_name.lower() in city.get("name_en", "").lower()):
                        return {
                            "success": True,
                            "city_id": city["id"],
                            "city_name": city["name"],
                            "city_name_en": city["name_en"],
                            "match_type": "exact"
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
                        "city_name_en": first_result["name_en"],
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
        """Search cities by name"""
        try:
            db = self._get_db_session()
            try:
                cities = data_api.search_cities(db, query)
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
            logger.error(f"Error searching cities: {str(e)}")
            return {"error": f"Failed to search cities: {str(e)}"}
    

    async def check_city_availability(self, city_name: str, item_type: str, item_name: str) -> Dict[str, Any]:
        """Check if a brand or product is available in a specific city - Now with AI-powered brand extraction"""
        try:
            db = self._get_db_session()
            try:
                # First get the city ID - try AI extraction if regular method fails
                city_result = self.get_city_id_by_name(city_name)
                if not city_result.get("success"):
                    # Try AI city extraction as fallback
                    ai_city = await self._ai_extract_city_from_message(city_name)
                    if ai_city:
                        city_result = {
                            "success": True,
                            "city_id": ai_city["city_id"],
                            "city_name": ai_city["city_name"],
                            "city_name_en": ai_city["city_name_en"],
                            "match_type": "ai_extracted"
                        }
                    else:
                        return {
                            "success": False,
                            "error": f"لم أجد مدينة باسم '{city_name}'. يرجى التحقق من الاسم.",
                            "item_type": item_type,
                            "item_name": item_name
                        }
                
                city_id = city_result["city_id"]
                
                if item_type == "brand":
                    # Use AI to extract the actual brand name from user input
                    # This handles cases like "امياه حلوه" → "حلوه"
                    actual_brand_name = await self._ai_extract_brand_from_message(item_name)
                    if not actual_brand_name:
                        # Fallback to original input
                        actual_brand_name = item_name
                    
                    # Check if brand exists in this city
                    brands = data_api.get_brands_by_city(db, city_id)
                    found_brand = None
                    
                    # First try exact match with AI-extracted brand name
                    for brand in brands:
                        if actual_brand_name.lower() == brand["title"].lower():
                            found_brand = brand
                            break
                    
                    # If not found, try partial match
                    if not found_brand:
                        for brand in brands:
                            if actual_brand_name.lower() in brand["title"].lower() or brand["title"].lower() in actual_brand_name.lower():
                                found_brand = brand
                                break
                    
                    if found_brand:
                        return {
                            "success": True,
                            "available": True,
                            "city_name": city_result["city_name"],
                            "item_type": item_type,
                            "item_name": item_name,
                            "actual_brand_name": actual_brand_name,
                            "brand_info": {
                                "id": found_brand["id"],
                                "title": found_brand["title"]
                            }
                        }
                    
                    return {
                        "success": True,
                        "available": False,
                        "city_name": city_result["city_name"],
                        "item_type": item_type,
                        "item_name": item_name,
                        "actual_brand_name": actual_brand_name,
                        "message": f"للأسف، العلامة التجارية '{actual_brand_name}' غير متوفرة في {city_result['city_name']}"
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
    
    async def find_brand_in_city(self, brand_name: str, city_id: int) -> Dict[str, Any]:
        """Find if a specific brand exists in a city and return its products - Now with AI-powered brand matching"""
        try:
            db = self._get_db_session()
            try:
                # Get all brands in the city
                brands = data_api.get_brands_by_city(db, city_id)
                
                # Use AI to extract/correct the brand name first
                actual_brand_name = await self._ai_extract_brand_from_message(brand_name)
                if not actual_brand_name:
                    actual_brand_name = brand_name  # Fallback to original
                
                # Find the brand by name (case insensitive search)
                found_brand = None
                
                # First try exact match with AI-extracted name
                for brand in brands:
                    if actual_brand_name.lower() == brand["title"].lower():
                        found_brand = brand
                        break
                
                # If not found, try partial match
                if not found_brand:
                    for brand in brands:
                        if actual_brand_name.lower() in brand["title"].lower() or brand["title"].lower() in actual_brand_name.lower():
                            found_brand = brand
                            break
                
                if not found_brand:
                    # Get city info for error message
                    all_cities = data_api.get_all_cities(db)
                    city_name = "المدينة المحددة"
                    for city in all_cities:
                        if city["id"] == city_id:
                            city_name = city["name"]
                            break
                    
                    return {
                        "success": False,
                        "brand_found": False,
                        "brand_name": brand_name,
                        "ai_extracted_brand": actual_brand_name,
                        "city_id": city_id,
                        "message": f"للأسف، العلامة التجارية '{actual_brand_name}' غير متوفرة في {city_name}",
                        "available_brands": [{"id": b["id"], "title": b["title"]} for b in brands[:5]]  # Show first 5 brands as alternatives
                    }
                
                # Get products for the found brand
                products = data_api.get_products_by_brand(db, found_brand["id"])
                
                # Filter products to show only essential information
                filtered_products = [
                    {
                        "product_title": product["product_title"],
                        "product_contract_price": product["product_contract_price"],
                        "product_packing": product["product_packing"]
                    }
                    for product in products
                ]
                
                return {
                    "success": True,
                    "brand_found": True,
                    "brand_info": {
                        "id": found_brand["id"],
                        "title": found_brand["title"]
                    },
                    "original_brand_input": brand_name,
                    "ai_extracted_brand": actual_brand_name,
                    "city_id": city_id,
                    "products": filtered_products,
                    "product_count": len(filtered_products)
                }
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error finding brand {brand_name} in city {city_id}: {str(e)}")
            return {"error": f"حدث خطأ في البحث عن العلامة التجارية: {str(e)}"}
    
    async def get_products_by_brand_and_city(self, brand_name: str, city_name: str) -> Dict[str, Any]:
        """Get products from a specific brand in a specific city - Now with AI-powered extraction"""
        try:
            # First get city ID - try AI extraction if needed
            city_result = self.get_city_id_by_name(city_name)
            if not city_result.get("success"):
                # Try AI city extraction as fallback
                ai_city = await self._ai_extract_city_from_message(city_name)
                if ai_city:
                    city_result = {
                        "success": True,
                        "city_id": ai_city["city_id"],
                        "city_name": ai_city["city_name"],
                        "city_name_en": ai_city["city_name_en"],
                        "match_type": "ai_extracted"
                    }
                else:
                    return city_result  # Return the original error
            
            city_id = city_result["city_id"]
            
            # Use AI to extract actual brand name from user input
            actual_brand_name = await self._ai_extract_brand_from_message(brand_name)
            if not actual_brand_name:
                actual_brand_name = brand_name  # Fallback to original
            
            # Use find_brand_in_city to get the products with the AI-extracted brand name
            result = await self.find_brand_in_city(actual_brand_name, city_id)
            
            # Add city information and AI extraction info to the result
            if result.get("success"):
                result["city_info"] = {
                    "city_id": city_id,
                    "city_name": city_result["city_name"],
                    "city_name_en": city_result["city_name_en"]
                }
                result["original_brand_input"] = brand_name
                result["ai_extracted_brand"] = actual_brand_name
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting products for brand {brand_name} in city {city_name}: {str(e)}")
            return {"error": f"حدث خطأ في البحث عن منتجات العلامة التجارية: {str(e)}"}
    
    def calculate_total_price(self, unit_price: float, quantity: int, product_name: str) -> Dict[str, Any]:
        """Calculate total price for specific quantity of a product - NOTE: Prices from API are per CARTON, not per unit"""
        try:
            if unit_price <= 0:
                return {
                    "success": False,
                    "error": "سعر الكرتونة يجب أن يكون أكثر من صفر"
                }
            
            if quantity <= 0:
                return {
                    "success": False,
                    "error": "الكمية يجب أن تكون أكثر من صفر"
                }
            
            # API prices are per CARTON, so total = carton_price × number_of_cartons
            total_price = unit_price * quantity
            
            # Format numbers to be user-friendly
            carton_price_formatted = f"{unit_price:.2f}".rstrip('0').rstrip('.')
            total_price_formatted = f"{total_price:.2f}".rstrip('0').rstrip('.')
            
            return {
                "success": True,
                "product_name": product_name,
                "carton_price": unit_price,  # This is actually carton price from API
                "quantity_cartons": quantity,
                "total_price": total_price,
                "calculation_details": {
                    "carton_price_formatted": carton_price_formatted,
                    "total_price_formatted": total_price_formatted,
                    "currency": "ريال سعودي"
                },
                "summary": f"{product_name}: {quantity} كرتونة × {carton_price_formatted} ريال = {total_price_formatted} ريال سعودي",
                "note": "السعر المعروض هو لكراتين كاملة وليس وحدات فردية"
            }
            
        except Exception as e:
            logger.error(f"Error calculating total price: {str(e)}")
            return {"error": f"حدث خطأ في حساب السعر الإجمالي: {str(e)}"}
    
    def _check_question_already_answered(self, user_message: str, conversation_history: List[Dict] = None) -> bool:
        """Check if the user's question was already answered in recent conversation history"""
        if not conversation_history or len(conversation_history) < 2:
            return False
        
        try:
            import re
            
            # Clean and normalize the current question
            current_question = user_message.lower().strip()
            
            # Common question patterns that might be repeated
            repeated_question_patterns = [
                r'كم\s*الإجمالي',
                r'كم\s*المجموع', 
                r'كم\s*السعر\s*الكلي',
                r'كم\s*التكلفة',
                r'ما\s*هو\s*الإجمالي',
                r'what.*total',
                r'how.*much.*total',
                r'total.*cost',
                r'total.*price'
            ]
            
            # Check if current message matches any repeated question pattern
            is_repetitive_question = False
            for pattern in repeated_question_patterns:
                if re.search(pattern, current_question):
                    is_repetitive_question = True
                    break
            
            if not is_repetitive_question:
                return False
            
            # Look for answers to similar questions in recent conversation history
            # Check last 5 messages for pricing/total information
            recent_messages = conversation_history[-5:]
            
            for msg in recent_messages:
                content = msg.get('content', '').lower()
                role = msg.get('role', '')
                
                # Skip user messages, only check bot responses
                if role == 'user':
                    continue
                
                # Check if the bot response contains pricing information
                pricing_indicators = [
                    r'\d+\s*ريال',  # Contains "X ريال"
                    r'\d+\s*×\s*\d+',  # Contains multiplication (5 × 16)
                    r'السعر\s*الإجمالي',  # Contains "total price"
                    r'المجموع',  # Contains "total"
                    r'الإجمالي',  # Contains "total"
                    r'كرتونة\s*×',  # Contains "carton ×"
                    r'\d+\s*كرتونة',  # Contains "X cartons"
                ]
                
                for indicator in pricing_indicators:
                    if re.search(indicator, content):
                        print(f"🔄 Question already answered - found pricing info in recent conversation")
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking repeated questions: {str(e)}")
            return False
    
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
            
            # Call OpenAI for classification
            response = await self.openai_client.chat.completions.create(
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
            
            # Return True if relevant, False if not relevant
            return "relevant" in classification_result
            
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
        """
        print(f"Processing query: {user_message} (Language: {user_language})")
        
        # STEP 1: Check if message is relevant to water delivery services
        print("🔍 Checking message relevance...")
        is_relevant = await self._classify_message_relevance(user_message, conversation_history, user_language)
        
        if not is_relevant:
            print(f"❌ Message not relevant to water delivery services: {user_message[:50]}...")
            # Return None or empty string to indicate the agent should not reply
            return ""
        
        print("✅ Message is relevant to water delivery services")
        
        # STEP 2: Check if this question was already answered in recent conversation
        print("🔄 Checking for repeated questions...")
        already_answered = self._check_question_already_answered(user_message, conversation_history)
        
        if already_answered:
            print(f"🔄 Question already answered in recent conversation: {user_message[:50]}...")
            # Return empty string to indicate no reply needed
            return ""
        
        print("✅ Question is new or needs fresh answer")
        
        max_function_calls = 5
        function_call_count = 0
        
        try:
            # Check if we already have city information from current message or conversation history
            city_context = self._extract_city_from_context(user_message, conversation_history)
            
            # Extract brand and quantity information for enhanced processing using AI
            brand_mentioned = await self._ai_extract_brand_from_message(user_message)
            quantity_info = self._extract_quantity_from_message(user_message)
            
            # Also try AI city extraction from current message if context method didn't find anything
            ai_city_context = None
            if not city_context:
                ai_city_context = await self._ai_extract_city_from_message(user_message)
                if ai_city_context:
                    city_context = ai_city_context
            
            # Log detection results
            if brand_mentioned:
                print(f"🏷️ Brand detected in message: {brand_mentioned}")
            if quantity_info:
                print(f"💰 Quantity detected: {quantity_info['quantity']} cartons")
            if city_context:
                print(f"📍 City detected: {city_context['city_name']} (from {city_context['found_in']})")
            
            # Prepare conversation history
            messages = []
            
            # System message with instructions based on user language
            city_info = ""
            brand_info = ""
            quantity_info_text = ""
            
            if city_context:
                found_where = "current message" if city_context['found_in'] == "current_message" else "conversation history"
                city_info = f"\n\nIMPORTANT CONTEXT: The customer is from {city_context['city_name_en']} ({city_context['city_name']}) - detected from {found_where}. You already know their city, so you can show products and brands for this city without asking again."
            
            if brand_mentioned:
                brand_info = f"\n\nBRAND CONTEXT: The customer mentioned '{brand_mentioned}' in their message. "
                if city_context:
                    brand_info += f"Since you know their city ({city_context['city_name']}), use find_brand_in_city to show {brand_mentioned} products available there."
                else:
                    brand_info += "You need to ask for their city first to show products from this brand."
            
            if quantity_info:
                quantity_info_text = f"\n\nQUANTITY CONTEXT: The customer asked about {quantity_info['quantity']} cartons. When you get product pricing, use calculate_total_price to show the total cost for this quantity. Remember: API prices are per CARTON, not per individual bottle."
            
            if user_language == 'en':
                system_message = {
                    "role": "system",
                    "content": f"""You are a friendly customer service employee at Abar Water Delivery Company in Saudi Arabia.{city_info}{brand_info}{quantity_info_text}

Your job is to help customers with:
1. Finding available cities for water delivery service
2. Showing water brands available in each city
3. Displaying water products and their prices from each brand
4. Answering questions naturally and helpfully
5. Asking friendly questions when you need more information
6. Calculating total prices when specific quantities are requested
7. Handling specific brand name requests

Communication Style:
- Talk like a real human customer service representative
- Be natural, warm, and conversational
- Never use phrases like "AI response", "Assistant reply", or "I am an AI"
- Respond as if you're a real person working for the company

CRITICAL WORKFLOW - MANDATORY ORDER:
🚨 ALWAYS follow this exact sequence: CITY → BRANDS → PRODUCTS → RESPONSE
🚨 Step 1: Get the customer's city (use get_city_id_by_name or search_cities)
🚨 Step 2: Show brands available in that city (use get_brands_by_city)
🚨 Step 3: When customer selects a brand, show products from that brand (use get_products_by_brand)
🚨 Step 4: Provide final response with complete information

✨ NEW SPECIAL CASES:

🏷️ Brand Name Only Requests (with AI-powered extraction):
- When customer mentions ONLY a brand name (like "Aquafina" or "Nova" or "Al-Hada" or variations like "امياه حلوه"):
  - System now uses AI to extract correct brand names from different expressions and variations
  - If you know their city from context: use find_brand_in_city to show products from that brand in their city
  - If you don't know the city: ask "Which city are you in? I'll show you [brand name] products available there!"

💰 Quantity and Price Calculations:
- When customer asks about price for specific quantities (like "How much for 5 cartons of Aquafina?"):
  - Get the carton price first (API prices are per CARTON, not per individual bottle)
  - Use calculate_total_price to compute total cost
  - Show breakdown: "Carton price × Quantity = Total price"
  - Important: Clarify to customer that prices are for full cartons, not individual bottles

🔄 Avoid Repeated Answers:
- If customer asks a question that was already answered in recent conversation (like "what's the total" after total was shown)
- Don't reply to the same question again - system will automatically check and not send a response

CITY DETECTION PRIORITY:
1. Check if city is mentioned in current user message
2. Check if city is available in conversation history context
3. If NO city found in either - IMMEDIATELY ask for city before proceeding

NEVER skip steps or show information out of order:
❌ Don't show brands without knowing the city
❌ Don't show products without knowing both city and brand
❌ Don't use general product searches - always go through the city→brand→product flow
❌ Don't make assumptions about city - always confirm first

PROACTIVE CITY ASKING - When user asks about brands/products but no city is known:
- "What brands are available?" → "Which city are you in? I'll show you all the brands we deliver there!"
- "What are your prices?" → "Which city would you like delivery to? I'll show you the brands and their prices there."
- "Do you have Aquafina?" → "Which city are you in? I'll check if Aquafina is available there and show you their products!"
- "Show me water options" → "What city are you located in? I'll show you all brands and their products available there!"
- "What products do you have?" → "Which city are you in? I'll show you all available products there!"
- "Aquafina" (just brand name) → "Which city are you in? I'll show you Aquafina products available there!"

Examples for Quantity Requests:
- "How much for 5 Nova cartons?" → Get Nova carton price, then calculate 5 × price
- "I want 10 cartons of Al-Hada, how much?" → Get Al-Hada carton price, then calculate 10 × price
- "If I buy 3 large Aquafina cartons?" → Get large Aquafina carton price, then calculate 3 × price
- Important: Always clarify to customer that prices are for full cartons, not individual bottles

Typo and Spelling Handling:
- Customers often make typos in city names (e.g., "Riyadh" variations)
- When a city name doesn't match exactly, use search_cities function to find similar cities
- Be understanding and helpful with spelling mistakes
- If you find a similar city, confirm naturally: "Did you mean [correct city name]?"

IMPORTANT - Unsupported Cities:
- Sometimes users ask about cities that are not in our database
- When a city is not found (even after searching), politely explain that we don't support that city for now
- Example: "I'm sorry, we don't deliver to [city name] for now."
- Always be apologetic and helpful when explaining unsupported cities

Important rules:
- Always use available functions to get updated information
- For city queries: try get_city_id_by_name first, if fails use search_cities
- Be patient with typos and spelling variations
- Respond in English since the customer is communicating in English
- Keep responses helpful and conversational like a real person would
        - REMEMBER: No products or brands without city information!
        - If you can't find the city in current message or conversation history, ask for it immediately!

Be helpful, understanding, and respond exactly like a friendly human employee would."""
                }
            else:
                city_info_ar = ""
                brand_info_ar = ""
                quantity_info_ar = ""
                
                if city_context:
                    found_where_ar = "الرسالة الحالية" if city_context['found_in'] == "current_message" else "تاريخ المحادثة"
                    city_info_ar = f"\n\nسياق مهم: العميل من {city_context['city_name']} ({city_context['city_name_en']}) - تم اكتشافها من {found_where_ar}. أنت تعرف مدينتهم بالفعل، لذا يمكنك عرض المنتجات والعلامات التجارية لهذه المدينة بدون السؤال مرة أخرى."
                
                if brand_mentioned:
                    brand_info_ar = f"\n\nسياق العلامة التجارية: العميل ذكر '{brand_mentioned}' في رسالته. "
                    if city_context:
                        brand_info_ar += f"بما أنك تعرف مدينتهم ({city_context['city_name']})، استخدم find_brand_in_city لعرض منتجات {brand_mentioned} المتاحة هناك."
                    else:
                        brand_info_ar += "تحتاج لتسأل عن مدينتهم أولاً لعرض منتجات هذه العلامة التجارية."
                
                if quantity_info:
                    quantity_info_ar = f"\n\nسياق الكمية: العميل سأل عن {quantity_info['quantity']} كرتونة. عندما تحصل على أسعار المنتجات، استخدم calculate_total_price لعرض التكلفة الإجمالية لهذه الكمية. تذكر: أسعار API هي للكراتين وليس للقناني الفردية."
                
                system_message = {
                    "role": "system",
                    "content": f"""أنت موظف خدمة عملاء ودود في شركة أبار لتوصيل المياه في السعودية.{city_info_ar}{brand_info_ar}{quantity_info_ar}

وظيفتك مساعدة العملاء في:
1. إيجاد المدن المتاحة لخدمة توصيل المياه
2. عرض العلامات التجارية للمياه المتاحة في كل مدينة  
3. عرض منتجات المياه وأسعارها من كل علامة تجارية
4. الإجابة على الأسئلة بطريقة طبيعية ومفيدة
5. طرح أسئلة ودودة عندما تحتاج معلومات أكثر
6. حساب الأسعار الإجمالية عند طلب كميات محددة
7. التعامل مع طلبات العلامات التجارية المحددة

أسلوب التواصل:
- تكلم مثل موظف خدمة عملاء حقيقي
- كن طبيعي وودود ومحادثي
- لا تستخدم أبداً عبارات مثل "رد الذكاء الاصطناعي" أو "رد المساعد" أو "أنا ذكاء اصطناعي"
- رد كأنك شخص حقيقي يعمل في الشركة

سير العمل الحاسم - الترتيب الإجباري:
🚨 اتبع دائماً هذا التسلسل بالضبط: المدينة ← العلامات التجارية ← المنتجات ← الرد
🚨 الخطوة 1: احصل على مدينة العميل (استخدم get_city_id_by_name أو search_cities)
🚨 الخطوة 2: اعرض العلامات التجارية المتاحة في تلك المدينة (استخدم get_brands_by_city)
🚨 الخطوة 3: عندما يختار العميل علامة تجارية، اعرض منتجات تلك العلامة (استخدم get_products_by_brand)
🚨 الخطوة 4: قدم الرد النهائي مع المعلومات الكاملة

✨ حالات خاصة جديدة:

🏷️ طلبات العلامة التجارية فقط (مع استخراج ذكي):
- عندما يذكر العميل فقط اسم علامة تجارية (مثل "أكوافينا" أو "نوفا" أو "الهدا" أو "امياه حلوه" أو "موية حلوه"):
  - النظام الآن يستخدم الذكاء الاصطناعي لاستخراج اسم العلامة التجارية الصحيح من تعبيرات مختلفة
  - إذا كنت تعرف مدينته من السياق: استخدم find_brand_in_city لعرض منتجات هذه العلامة في مدينته
  - إذا لم تعرف المدينة: اسأل "في أي مدينة أنت؟ راح أعرض لك منتجات [اسم العلامة] المتاحة هناك!"

💰 حسابات الكميات والأسعار:
- عندما يسأل العميل عن سعر كمية محددة (مثل "كم سعر 5 كراتين أكوافينا؟"):
  - احصل على سعر الكرتونة الواحدة أولاً (الأسعار في API هي للكراتين وليس للوحدات الفردية)
  - استخدم calculate_total_price لحساب السعر الإجمالي
  - اعرض التفاصيل: "سعر الكرتونة × الكمية = السعر الإجمالي"
  - مهم: وضح للعميل أن السعر للكرتونة الكاملة وليس للقنينة الواحدة

🔄 تجنب تكرار الإجابات:
- إذا سأل العميل سؤال تمت إجابته في المحادثة السابقة (مثل "كم الإجمالي" بعد أن تم عرض الإجمالي)
- لا ترد على نفس السؤال مرة أخرى - النظام سيتحقق تلقائياً ولن يرسل رد

أولوية اكتشاف المدينة:
1. تحقق إذا كانت المدينة مذكورة في رسالة العميل الحالية
2. تحقق إذا كانت المدينة متوفرة في سياق تاريخ المحادثة
3. إذا لم تجد مدينة في أي منهما - اسأل فوراً عن المدينة قبل المتابعة

لا تتجاوز أي خطوة أو تعرض معلومات خارج الترتيب:
❌ لا تعرض العلامات التجارية بدون معرفة المدينة
❌ لا تعرض المنتجات بدون معرفة المدينة والعلامة التجارية
❌ لا تستخدم البحث العام للمنتجات - اتبع دائماً تدفق المدينة→العلامة→المنتج
❌ لا تفترض المدينة - تأكد دائماً أولاً

السؤال الاستباقي عن المدينة - عندما يسأل العميل عن العلامات/المنتجات بدون معرفة المدينة:
- "ما هي العلامات التجارية المتاحة؟" → "في أي مدينة أنت؟ راح أعرض لك كل العلامات التجارية اللي نوصلها هناك!"
- "ما هي أسعاركم؟" → "أي مدينة تريد التوصيل لها؟ راح أعرض لك العلامات التجارية وأسعارها هناك."
- "هل عندكم أكوافينا؟" → "في أي مدينة أنت؟ راح أتأكد لك إذا أكوافينا متوفرة هناك وأعرض منتجاتها!"
- "وريني خيارات المياه" → "في أي مدينة أنت؟ راح أعرض لك كل العلامات التجارية ومنتجاتها المتاحة هناك!"
- "ما هي المنتجات عندكم؟" → "في أي مدينة أنت؟ راح أعرض لك كل المنتجات المتاحة هناك!"
- "أكوافينا" (فقط اسم العلامة) → "في أي مدينة أنت؟ راح أعرض لك منتجات أكوافينا المتاحة هناك!"

أمثلة للتعامل مع طلبات الكميات:
- "كم سعر 5 كراتين نوفا؟" → احصل على سعر كرتونة نوفا واحدة، ثم احسب 5 × السعر
- "أريد 10 كراتين من الهدا، كم يكلف؟" → احصل على سعر كرتونة الهدا، ثم احسب 10 × السعر
- "لو أشتري 3 كراتين أكوافينا كبيرة؟" → احصل على سعر كرتونة أكوافينا الكبيرة، ثم احسب 3 × السعر
- مهم: وضح دائماً للعميل أن الأسعار للكراتين الكاملة وليس للقناني الفردية

التعامل مع الأخطاء الإملائية:
- العملاء غالباً يكتبون أسماء المدن بأخطاء إملائية (مثل "رياص" بدلاً من "رياض")
- عندما لا يتطابق اسم المدينة تماماً، استخدم وظيفة search_cities للبحث عن مدن مشابهة
- كن متفهماً ومساعداً مع الأخطاء الإملائية
- إذا وجدت مدينة مشابهة، تأكد بطريقة طبيعية: "تقصد [اسم المدينة الصحيح]؟"

قواعد مهمة:
- استخدم دائماً الوظائف المتاحة للحصول على معلومات حديثة
- للاستفسارات عن المدن: جرب get_city_id_by_name أولاً، إذا فشل استخدم search_cities
- كن صبور مع الأخطاء الإملائية والتنويعات
- أجب باللغة العربية لأن العميل يتواصل بالعربية
- خلي ردودك مفيدة وودودة مثل أي شخص حقيقي
        - تذكر: لا منتجات ولا علامات تجارية بدون معلومات المدينة!
        - إذا لم تجد المدينة في الرسالة الحالية أو تاريخ المحادثة، اسأل عنها فوراً!

كن مساعد ومتفهم ورد تماماً مثل موظف ودود حقيقي.

معلومات اضافية 
ابو ربع هي  ٢٠٠ مل او ٢٥٠
ابو نص هي  ٣٣٠ او ٣٠٠
ابو ريال  هي  ٦٠٠ مل  او ٥٥٠ مل 
ابو ريالين هي  ١.٥ لتر

"""
                }
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
                        
                    response = await self.openai_client.chat.completions.create(
                        model="gpt-3.5-turbo",
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
                            model="gpt-3.5-turbo",
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
                                # Check if this is an async function
                                if function_name in self.async_functions:
                                    function_result = await self.available_functions[function_name](**function_args)
                                else:
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
                final_response = await self.openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
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
