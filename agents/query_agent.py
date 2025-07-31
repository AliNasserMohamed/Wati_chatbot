#!/usr/bin/env python3

import requests
import json
import logging
import asyncio
import time
import re
from typing import Dict, List, Any, Optional, Tuple
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
            "calculate_total_price": self.calculate_total_price,
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
✅ الاستفسار عن خدمة التوصيل
✅ أسئلة عن شركات المياه
✅ طلبات حساب السعر الإجمالي للكميات
✅ الردود البسيطة مثل "نعم" أو "لا" في سياق محادثة عن المياه

الرسائل غير المتعلقة بالخدمة تشمل:
❌ التحيات العامة ("أهلاً", "مرحبا", "السلام عليكم", "صباح الخير", "مساء الخير")  
❌ رسائل الشكر والامتنان ("شكراً", "جزاك الله خير", "مشكور", "الله يعطيك العافية")
❌ المواضيع العامة غير المتعلقة بالمياه
❌ الأسئلة الشخصية
❌ طلبات المساعدة في مواضيع أخرى
❌ الرسائل التي تحتوي على روابط

تعليمات خاصة:
- لا تعتبر التحيات والشكر متعلقة بالخدمة حتى لو كانت في سياق محادثة عن المياه
- كن صارم في التصنيف - فقط الأسئلة المباشرة عن المدن والعلامات والمنتجات تعتبر متعلقة
- الردود البسيطة مثل "نعم" أو "موافق" تعتبر متعلقة إذا كانت في سياق محادثة عن المياه

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
✅ Requests to calculate total price for quantities
✅ Simple replies like "yes" or "no" in water service context

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
- Simple replies like "yes" or "okay" are relevant if they're in water service conversation context

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
                "name": "get_products_by_brand_and_city",
                "description": "Get products from a specific brand in a specific city. Use this when customer mentions only a brand name and you know their city from context or previous conversation. This combines steps 2 and 3 when brand is known.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "brand_name": {
                            "type": "string",
                            "description": "Name of the brand (e.g., 'أكوافينا', 'Aquafina', 'نوفا', 'Nova')"
                        },
                        "city_id": {
                            "type": "integer",
                            "description": "City ID where to look for the brand"
                        }
                    },
                    "required": ["brand_name", "city_id"]
                }
            },
            {
                "name": "calculate_total_price",
                "description": "Calculate total price for a specific quantity of a product. Use this when customer asks for price of multiple units (like '5 cartons', '10 bottles', etc.).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "product_title": {
                            "type": "string",
                            "description": "Exact product title/name"
                        },
                        "unit_price": {
                            "type": "number",
                            "description": "Price per unit/carton/bottle"
                        },
                        "quantity": {
                            "type": "integer",
                            "description": "Number of units requested"
                        },
                        "product_packing": {
                            "type": "string",
                            "description": "Product packaging information (e.g., '24 × 330 مل')"
                        }
                    },
                    "required": ["product_title", "unit_price", "quantity"]
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
    
    def _get_db_session(self):
        """Get database session"""
        from database.db_utils import SessionLocal
        return SessionLocal()
    
    def _extract_context_info(self, user_message: str, conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """
        Enhanced context extraction that finds city, brand names, and conversation context
        including handling simple replies like 'yes' in context of previous bot suggestions
        """
        context_info = {
            "city": None,
            "brand": None,
            "quantity": None,
            "previous_suggestion": None,
            "is_simple_reply": False
        }
        
        try:
            db = self._get_db_session()
            try:
                all_cities = data_api.get_all_cities(db)
                all_brands = []
                
                # Get all brands from all cities for brand detection
                for city in all_cities:
                    try:
                        city_brands = data_api.get_brands_by_city(db, city["id"])
                        all_brands.extend(city_brands)
                    except:
                        continue
                
                # Check if current message is a simple reply (yes/no/موافق etc.)
                simple_replies = ['نعم', 'لا', 'yes', 'no', 'موافق', 'حسناً', 'اوكيه', 'ok', 'okay', 'تمام', 'ممتاز', 'جيد']
                user_message_lower = user_message.lower().strip()
                
                if any(reply in user_message_lower for reply in simple_replies):
                    context_info["is_simple_reply"] = True
                    
                    # Look for previous bot suggestions in conversation history
                    if conversation_history:
                        for msg in reversed(conversation_history[-5:]):  # Check last 5 messages
                            if msg.get("role") == "bot" or msg.get("role") == "assistant":
                                bot_content = msg.get("content", "").lower()
                                # Look for product suggestions in bot messages
                                if any(word in bot_content for word in ['منتج', 'سعر', 'price', 'product', 'ريال']):
                                    context_info["previous_suggestion"] = msg.get("content", "")
                                    break
                
                # Extract quantity from current message
                quantity_patterns = [
                    r'(\d+)\s*(?:كرتون|carton|علبة|صندوق|قطعة|حبة|زجاجة|bottle)',
                    r'(\d+)\s*(?:من|of|pieces?|units?)',
                    r'اريد\s+(\d+)',
                    r'ابي\s+(\d+)',
                    r'أريد\s+(\d+)'
                ]
                
                for pattern in quantity_patterns:
                    match = re.search(pattern, user_message, re.IGNORECASE)
                    if match:
                        context_info["quantity"] = int(match.group(1))
                        break
                
                # PRIORITY 1: Check current user message for city and brand
                current_content = user_message.lower()
                
                # Extract city from current message
                for city in all_cities:
                    city_name_ar = city.get("name", "").lower()
                    city_name_en = city.get("name_en", "").lower()
                    
                    if city_name_ar and city_name_ar in current_content:
                        context_info["city"] = {
                            "city_id": city["id"],
                            "city_name": city["name"],
                            "city_name_en": city["name_en"],
                            "found_in": "current_message"
                        }
                        break
                    elif city_name_en and city_name_en in current_content:
                        context_info["city"] = {
                            "city_id": city["id"],
                            "city_name": city["name"],
                            "city_name_en": city["name_en"],
                            "found_in": "current_message"
                        }
                        break
                
                # Extract brand from current message
                for brand in all_brands:
                    brand_title = brand.get("title", "").lower()
                    if brand_title and brand_title in current_content:
                        context_info["brand"] = {
                            "brand_id": brand["id"],
                            "brand_title": brand["title"],
                            "found_in": "current_message"
                        }
                        break
                
                # PRIORITY 2: Check conversation history if not found in current message
                if conversation_history and (not context_info["city"] or not context_info["brand"]):
                    for message in reversed(conversation_history[-10:]):  # Check last 10 messages
                        content = message.get("content", "").lower()
                        
                        # Look for city in history if not found
                        if not context_info["city"]:
                            for city in all_cities:
                                city_name_ar = city.get("name", "").lower()
                                city_name_en = city.get("name_en", "").lower()
                                
                                if city_name_ar and city_name_ar in content:
                                    context_info["city"] = {
                                        "city_id": city["id"],
                                        "city_name": city["name"],
                                        "city_name_en": city["name_en"],
                                        "found_in": "conversation_history"
                                    }
                                    break
                                elif city_name_en and city_name_en in content:
                                    context_info["city"] = {
                                        "city_id": city["id"],
                                        "city_name": city["name"],
                                        "city_name_en": city["name_en"],
                                        "found_in": "conversation_history"
                                    }
                                    break
                        
                        # Look for brand in history if not found
                        if not context_info["brand"]:
                            for brand in all_brands:
                                brand_title = brand.get("title", "").lower()
                                if brand_title and brand_title in content:
                                    context_info["brand"] = {
                                        "brand_id": brand["id"],
                                        "brand_title": brand["title"],
                                        "found_in": "conversation_history"
                                    }
                                    break
                        
                        # Break if we found both
                        if context_info["city"] and context_info["brand"]:
                            break
                
                return context_info
                
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error extracting context info: {str(e)}")
            return context_info

    def _extract_city_from_context(self, user_message: str, conversation_history: List[Dict] = None) -> Optional[Dict[str, Any]]:
        """Extract city information from current message and conversation history"""
        context_info = self._extract_context_info(user_message, conversation_history)
        return context_info.get("city")
    
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
                        "id": product.get("id"),
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
    
    def get_products_by_brand_and_city(self, brand_name: str, city_id: int) -> Dict[str, Any]:
        """Get products from a specific brand in a specific city"""
        try:
            db = self._get_db_session()
            try:
                # First find the brand in this city
                brands = data_api.get_brands_by_city(db, city_id)
                matching_brand = None
                
                for brand in brands:
                    if brand_name.lower() in brand["title"].lower() or brand["title"].lower() in brand_name.lower():
                        matching_brand = brand
                        break
                
                if not matching_brand:
                    return {
                        "success": False,
                        "error": f"لم أجد العلامة التجارية '{brand_name}' في هذه المدينة",
                        "brand_name": brand_name,
                        "city_id": city_id
                    }
                
                # Get products for this brand
                products = data_api.get_products_by_brand(db, matching_brand["id"])
                filtered_products = [
                    {
                        "id": product.get("id"),
                        "product_title": product["product_title"],
                        "product_contract_price": product["product_contract_price"],
                        "product_packing": product["product_packing"]
                    }
                    for product in products
                ]
                
                return {
                    "success": True,
                    "brand_info": {
                        "id": matching_brand["id"],
                        "title": matching_brand["title"]
                    },
                    "data": filtered_products
                }
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error fetching products for brand {brand_name} in city {city_id}: {str(e)}")
            return {"error": f"Failed to get products: {str(e)}"}
    
    def calculate_total_price(self, product_title: str, unit_price: float, quantity: int, product_packing: str = None) -> Dict[str, Any]:
        """Calculate total price for a given quantity of products"""
        try:
            total_price = unit_price * quantity
            
            result = {
                "success": True,
                "product_title": product_title,
                "unit_price": unit_price,
                "quantity": quantity,
                "total_price": total_price,
                "currency": "ريال سعودي"
            }
            
            if product_packing:
                result["product_packing"] = product_packing
                result["total_description"] = f"{quantity} × {product_packing}"
            
            return result
        except Exception as e:
            logger.error(f"Error calculating total price: {str(e)}")
            return {"error": f"Failed to calculate total price: {str(e)}"}
    
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
        Enhanced to handle simple replies in context
        Returns True if relevant, False if not relevant
        """
        try:
            # Quick check for links - auto-reject messages with URLs
            import re
            url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
            if re.search(url_pattern, user_message):
                logger.info(f"Message contains URL, marking as not relevant: {user_message[:50]}...")
                return False
            
            # Get context information
            context_info = self._extract_context_info(user_message, conversation_history)
            
            # If it's a simple reply and we have previous suggestion, it's likely relevant
            if context_info["is_simple_reply"] and context_info["previous_suggestion"]:
                logger.info(f"Simple reply with previous suggestion context, marking as relevant: {user_message[:50]}...")
                return True
            
            # Prepare context from conversation history
            context = ""
            if conversation_history:
                recent_messages = conversation_history[-3:]  # Last 3 messages for context
                context = "\n".join([f"{msg.get('role', 'user')}: {msg.get('content', '')}" for msg in recent_messages])
                context = f"\nRecent conversation context:\n{context}\n"
            
            # Choose classification prompt based on language
            classification_prompt = self.classification_prompt_ar if user_language == 'ar' else self.classification_prompt_en
            
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
        Enhanced with brand extraction, price calculation, and better context handling
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
        
        # STEP 2: Extract context information
        context_info = self._extract_context_info(user_message, conversation_history)
        print(f"🔍 Extracted context: {context_info}")
        
        max_function_calls = 4  # Increased to handle more complex scenarios
        function_call_count = 0
        
        try:
            # Prepare conversation history
            messages = []
            
            # Enhanced system message with brand handling and price calculation
            city_info = ""
            brand_info = ""
            context_hints = ""
            
            if context_info["city"]:
                found_where = "current message" if context_info['city']['found_in'] == "current_message" else "conversation history"
                city_info = f"\n\nIMPORTANT CONTEXT: The customer is from {context_info['city']['city_name_en']} ({context_info['city']['city_name']}) - detected from {found_where}. You already know their city."
            
            if context_info["brand"]:
                found_where = "current message" if context_info['brand']['found_in'] == "current_message" else "conversation history"
                brand_info = f"\n\nBRAND CONTEXT: Customer mentioned '{context_info['brand']['brand_title']}' - detected from {found_where}."
            
            if context_info["quantity"]:
                context_hints += f"\n\nQUANTITY CONTEXT: Customer wants {context_info['quantity']} units. Use calculate_total_price function when showing prices."
            
            if context_info["is_simple_reply"] and context_info["previous_suggestion"]:
                context_hints += f"\n\nSIMPLE REPLY CONTEXT: Customer is responding to a previous suggestion. Previous bot message: '{context_info['previous_suggestion'][:100]}...'"
            
            if user_language == 'en':
                system_message = {
                    "role": "system",
                    "content": f"""You are a friendly customer service employee at Abar Water Delivery Company in Saudi Arabia.{city_info}{brand_info}{context_hints}

Your job is to help customers with:
1. Finding available cities for water delivery service
2. Showing water brands available in each city
3. Displaying water products and their prices from each brand
4. Handling brand-only queries (when customer mentions just a brand name)
5. Calculating total prices for specific quantities
6. Understanding context from conversation history

Communication Style:
- Talk like a real human customer service representative
- Be natural, warm, and conversational
- Never use phrases like "AI response", "Assistant reply", or "I am an AI"
- Respond as if you're a real person working for the company

ENHANCED WORKFLOW HANDLING:

1. BRAND-ONLY QUERIES:
   - If customer mentions only a brand name AND you know their city → use get_products_by_brand_and_city
   - If customer mentions only a brand name BUT you DON'T know their city → ask for city first
   - Example: "Aquafina" → if city known: show Aquafina products, if not: "Which city are you in? I'll show you Aquafina products there!"

2. PRICE CALCULATIONS:
   - When customer asks for specific quantities (5 cartons, 10 bottles, etc.) → use calculate_total_price function
   - Always show unit price AND total price for quantities
   - Example: "Customer wants 5 cartons of X" → show "Each carton: 20 SAR, Total for 5 cartons: 100 SAR"

3. SIMPLE REPLIES HANDLING:
   - If customer says "yes", "okay", "نعم" in response to previous suggestions → provide the requested information (prices, details, etc.)
   - Use conversation history to understand what they're confirming
   - Example: If you previously asked "Do you want Aquafina?" and they say "yes" → show Aquafina products and prices

4. STANDARD WORKFLOW (when no shortcuts apply):
   🚨 CITY → BRANDS → PRODUCTS → RESPONSE
   🚨 Step 1: Get the customer's city (use get_city_id_by_name or search_cities)
   🚨 Step 2: Show brands available in that city (use get_brands_by_city)
   🚨 Step 3: When customer selects a brand, show products from that brand (use get_products_by_brand)
   🚨 Step 4: Provide final response with complete information

Important rules:
- Always use available functions to get updated information
- For brand + city queries: use get_products_by_brand_and_city
- For quantity requests: use calculate_total_price
- Be patient with typos and spelling variations
- Respond in English since the customer is communicating in English
- Keep responses helpful and conversational like a real person would

Be helpful, understanding, and respond exactly like a friendly human employee would."""
                }
            else:
                system_message = {
                    "role": "system",
                    "content": f"""أنت موظف خدمة عملاء ودود في شركة أبار لتوصيل المياه في السعودية.{city_info}{brand_info}{context_hints}

وظيفتك مساعدة العملاء في:
1. إيجاد المدن المتاحة لخدمة توصيل المياه
2. عرض العلامات التجارية للمياه المتاحة في كل مدينة  
3. عرض منتجات المياه وأسعارها من كل علامة تجارية
4. التعامل مع استفسارات العلامات التجارية فقط (عندما يذكر العميل اسم العلامة فقط)
5. حساب الأسعار الإجمالية للكميات المحددة
6. فهم السياق من تاريخ المحادثة

أسلوب التواصل:
- تكلم مثل موظف خدمة عملاء حقيقي
- كن طبيعي وودود ومحادثي
- لا تستخدم أبداً عبارات مثل "رد الذكاء الاصطناعي" أو "رد المساعد" أو "أنا ذكاء اصطناعي"
- رد كأنك شخص حقيقي يعمل في الشركة

سير العمل المحسن:

1. استفسارات العلامة التجارية فقط:
   - إذا ذكر العميل اسم علامة تجارية فقط وأنت تعرف مدينته → استخدم get_products_by_brand_and_city
   - إذا ذكر العميل اسم علامة تجارية فقط لكن لا تعرف مدينته → اسأل عن المدينة أولاً
   - مثال: "أكوافينا" → إذا كانت المدينة معروفة: اعرض منتجات أكوافينا، إذا لم تكن معروفة: "في أي مدينة أنت؟ راح أعرض لك منتجات أكوافينا هناك!"

2. حساب الأسعار:
   - عندما يسأل العميل عن كميات محددة (5 كراتين، 10 زجاجات، إلخ) → استخدم وظيفة calculate_total_price
   - اعرض دائماً سعر الوحدة والسعر الإجمالي للكميات
   - مثال: "العميل يريد 5 كراتين من X" → اعرض "الكرتون الواحد: 20 ريال، الإجمالي لـ 5 كراتين: 100 ريال"

3. التعامل مع الردود البسيطة:
   - إذا قال العميل "نعم"، "موافق", "اوكيه" رداً على اقتراحات سابقة → قدم المعلومات المطلوبة (الأسعار، التفاصيل، إلخ)
   - استخدم تاريخ المحادثة لفهم ما يؤكدونه
   - مثال: إذا سألت سابقاً "تريد أكوافينا؟" وقالوا "نعم" → اعرض منتجات وأسعار أكوافينا

4. سير العمل القياسي (عندما لا تنطبق الاختصارات):
   🚨 المدينة ← العلامات التجارية ← المنتجات ← الرد
   🚨 الخطوة 1: احصل على مدينة العميل (استخدم get_city_id_by_name أو search_cities)
   🚨 الخطوة 2: اعرض العلامات التجارية المتاحة في تلك المدينة (استخدم get_brands_by_city)
   🚨 الخطوة 3: عندما يختار العميل علامة تجارية، اعرض منتجات تلك العلامة (استخدم get_products_by_brand)
   🚨 الخطوة 4: قدم الرد النهائي مع المعلومات الكاملة

قواعد مهمة:
- استخدم دائماً الوظائف المتاحة للحصول على معلومات حديثة
- لاستفسارات العلامة + المدينة: استخدم get_products_by_brand_and_city
- لطلبات الكميات: استخدم calculate_total_price
- كن صبور مع الأخطاء الإملائية والتنويعات
- أجب باللغة العربية لأن العميل يتواصل بالعربية
- خلي ردودك مفيدة وودودة مثل أي شخص حقيقي

معلومات اضافية 
ابو ربع هي  ٢٠٠ مل او ٢٥٠
ابو نص هي  ٣٣٠ او ٣٠٠
ابو ريال  هي  ٦٠٠ مل  او ٥٥٠ مل 
ابو ريالين هي  ١.٥ لتر

كن مساعد ومتفهم ورد تماماً مثل موظف ودود حقيقي."""
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
