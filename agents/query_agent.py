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
from agents.query_config import (
    SIZE_TERMS, SIZE_KEYWORDS, YES_WORDS, PRICE_KEYWORDS,
    UNDERGROUND_BRANDS, GALLON_EXCHANGE, UNDERGROUND_KEYWORDS, 
    GALLON_KEYWORDS, CLASSIFICATION_PROMPTS, SYSTEM_MESSAGES,
    FUNCTION_DEFINITIONS
)

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
    Optimized Query Agent with function calling capabilities for water delivery services.
    Significantly reduced from 1073 to ~400 lines while maintaining all functionality.
    """
    
    def __init__(self):
        self.api_base_url = "http://localhost:8000/api"
        
        # Initialize OpenAI client
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        
        self.openai_client = AsyncOpenAI(api_key=openai_api_key)
        
        # Set up function definitions and available functions
        self.function_definitions = FUNCTION_DEFINITIONS
        self.available_functions = {
            "get_all_cities": self.get_all_cities,
            "get_city_id_by_name": self.get_city_id_by_name,
            "get_brands_by_city": self.get_brands_by_city,
            "get_products_by_brand": self.get_products_by_brand,
            "search_cities": self.search_cities,
            "check_city_availability": self.check_city_availability
        }
    
    def _get_db_session(self):
        """Get database session"""
        from database.db_utils import SessionLocal
        return SessionLocal()
    
    def _extract_context(self, user_message: str, conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """Extract city and brand context from message and conversation history"""
        context = {"city": None, "brand": None}
        
        try:
            db = self._get_db_session()
            try:
                all_cities = data_api.get_all_cities(db)
                
                # Check current message and recent history for city
                check_content = user_message.lower()
                if conversation_history:
                    for msg in conversation_history[-3:]:  # Only check last 3 messages
                        check_content += " " + msg.get("content", "").lower()
                
                # Find city
                for city in all_cities:
                    city_name_ar = city.get("name", "").lower()
                    city_name_en = city.get("name_en", "").lower()
                    
                    if (city_name_ar and city_name_ar in check_content) or \
                       (city_name_en and city_name_en in check_content):
                        context["city"] = {
                            "city_id": city["id"],
                            "city_name": city["name"],
                            "city_name_en": city["name_en"]
                        }
                        break
                
                # Find brand (only if city is known)
                if context["city"]:
                    brands = data_api.get_brands_by_city(db, context["city"]["city_id"])
                    for brand in brands:
                        brand_title = brand.get("title", "").lower()
                        if brand_title and brand_title in check_content:
                            context["brand"] = {
                                "brand_id": brand["id"],
                                "brand_title": brand["title"]
                            }
                            break
                
                return context
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error extracting context: {str(e)}")
            return context

    async def _classify_message_relevance(self, user_message: str, conversation_history: List[Dict] = None, user_language: str = 'ar') -> bool:
        """Check if message is relevant using simplified classification"""
        try:
            prompt = CLASSIFICATION_PROMPTS[user_language]
            
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_message}
            ]
            
            response = await self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=messages,
                temperature=0,
                max_tokens=20
            )
            
            result = response.choices[0].message.content.strip().lower()
            return "relevant" in result
            
        except Exception as e:
            logger.error(f"Classification error: {str(e)}")
            return True  # Default to relevant if classification fails

    def _check_special_cases(self, user_message: str, user_language: str) -> Optional[str]:
        """Check for special cases that need immediate responses"""
        user_msg_lower = user_message.lower()
        
        # Check for total price questions
        if any(keyword.lower() in user_msg_lower for keyword in PRICE_KEYWORDS):
            if user_language == 'ar':
                return "بتحصل الاصناف والاسعار في التطبيق وهذا هو الرابط https://onelink.to/abar_app https://abar.app/en/store/ وايضا عن طريق الموقع الالكتروني"
            else:
                return "You can find all products and prices in our app: https://onelink.to/abar_app or on our website: https://abar.app/en/store/"
        
        return None

    def _build_system_message(self, user_language: str, context: Dict[str, Any], all_conversation_text: str) -> Dict[str, str]:
        """Build optimized system message with context"""
        base_message = SYSTEM_MESSAGES[user_language]
        
        # Add context information
        if context["city"]:
            city_info = f"\n\nContext: Customer is in {context['city']['city_name']}"
            if context["brand"]:
                city_info += f" and mentioned {context['brand']['brand_title']}"
            base_message += city_info
        
        # Add special information based on conversation content
        if any(keyword in all_conversation_text for keyword in SIZE_KEYWORDS):
            if user_language == 'ar':
                size_info = "\n\nأحجام المياه: " + ", ".join([f"{k} = {v}" for k, v in SIZE_TERMS.items()])
                base_message += size_info
        
        if any(keyword in all_conversation_text for keyword in UNDERGROUND_KEYWORDS):
            if user_language == 'ar':
                underground_info = f"\n\nعلامات المياه الجوفية: {', '.join(UNDERGROUND_BRANDS)}"
                base_message += underground_info
        
        if any(keyword in all_conversation_text for keyword in GALLON_KEYWORDS):
            if user_language == 'ar':
                gallon_info = "\n\nخدمة تبديل الجوالين:\n" + \
                             "\n".join([f"{brand} - {', '.join(cities)}" for brand, cities in GALLON_EXCHANGE.items()])
                base_message += gallon_info
        
        return {"role": "system", "content": base_message}

    async def process_query(self, user_message: str, conversation_history: List[Dict] = None, user_language: str = 'ar', journey_id: str = None) -> str:
        """Process user query with optimized workflow"""
        print(f"Processing query: {user_message} (Language: {user_language})")
        
        # STEP 1: Check relevance
        is_relevant = await self._classify_message_relevance(user_message, conversation_history, user_language)
        if not is_relevant:
            print(f"❌ Message not relevant to water delivery services")
            return ""
        
        # STEP 2: Check special cases
        special_response = self._check_special_cases(user_message, user_language)
        if special_response:
            return special_response
        
        # STEP 3: Extract context
        context = self._extract_context(user_message, conversation_history)
        
        # STEP 4: Build conversation for LLM
        all_conversation_text = user_message
        if conversation_history:
            for msg in conversation_history[-3:]:  # Only use last 3 messages
                all_conversation_text += " " + msg.get("content", "")
        
        messages = [self._build_system_message(user_language, context, all_conversation_text)]
        
        # Add recent conversation history
        if conversation_history:
            for msg in conversation_history[-3:]:
                if msg.get("content", "").strip():
                    messages.append({
                        "role": msg.get("role", "user"),
                        "content": msg.get("content", "")
                    })
        
        messages.append({"role": "user", "content": user_message})
        
        # STEP 5: Function calling loop
        max_function_calls = 5
        function_call_count = 0
        
        try:
            while function_call_count < max_function_calls:
                response = await self.openai_client.chat.completions.create(
                    model="gpt-4",
                    messages=messages,
                    functions=self.function_definitions,
                    function_call="auto",
                    temperature=0.3,
                    max_tokens=800
                )
                
                message = response.choices[0].message
                
                # Log LLM interaction if available
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
                        prompt=user_message,
                        response=message.content or f"Function call: {message.function_call.name}" if message.function_call else "",
                        model="gpt-4",
                        function_calls=function_calls_info,
                        duration_ms=0,
                        tokens_used={"total_tokens": response.usage.total_tokens if response.usage else None}
                    )
                
                # Handle function calls
                if message.function_call:
                    function_call_count += 1
                    function_name = message.function_call.name
                    
                    try:
                        function_args = json.loads(message.function_call.arguments)
                        logger.info(f"Calling function #{function_call_count}: {function_name}")
                        
                        if function_name in self.available_functions:
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
                        else:
                            logger.error(f"Unknown function: {function_name}")
                            return "عذراً، حدث خطأ في الخدمة" if user_language == 'ar' else "Sorry, service error"
                            
                    except Exception as func_error:
                        logger.error(f"Function {function_name} failed: {str(func_error)}")
                        messages.append({
                            "role": "function",
                            "name": function_name,
                            "content": json.dumps({"error": str(func_error)}, ensure_ascii=False)
                        })
                else:
                    # No function call, return response
                    if message.content:
                        logger.info(f"Query completed after {function_call_count} function calls")
                        return message.content
                    else:
                        return "عذراً، لم أتمكن من معالجة طلبك" if user_language == 'ar' else "Sorry, couldn't process your request"
            
            # Max function calls reached, get final response
            final_response = await self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=messages,
                temperature=0.3,
                max_tokens=400
            )
            
            response_text = final_response.choices[0].message.content
            return response_text if response_text else ("تم الوصول للحد الأقصى من العمليات" if user_language == 'ar' else "Maximum operations reached")
            
        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            return "عذراً، حدث خطأ في معالجة الاستعلام" if user_language == 'ar' else "Sorry, error processing query"

    # Simplified API functions
    def get_all_cities(self) -> Dict[str, Any]:
        """Get complete list of all cities we serve"""
        try:
            db = self._get_db_session()
            try:
                cities = data_api.get_all_cities(db)
                filtered_cities = [
                    {"id": city["id"], "name": city["name"], "name_en": city["name_en"]}
                    for city in cities
                ]
                return {"success": True, "data": filtered_cities}
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error fetching cities: {str(e)}")
            return {"error": f"Failed to get cities: {str(e)}"}
    
    def get_city_id_by_name(self, city_name: str) -> Dict[str, Any]:
        """Get city ID by name with typo handling"""
        try:
            db = self._get_db_session()
            try:
                cities = data_api.get_all_cities(db)
                
                # Try exact match first
                for city in cities:
                    if (city_name.lower() in city.get("name", "").lower() or 
                        city_name.lower() in city.get("name_en", "").lower()):
                        return {
                            "success": True,
                            "city_id": city["id"],
                            "city_name": city["name"],
                            "city_name_en": city["name_en"]
                        }
                
                # Try fuzzy search
                search_results = data_api.search_cities(db, city_name)
                if search_results:
                    first_result = search_results[0]
                    return {
                        "success": True,
                        "city_id": first_result["id"],
                        "city_name": first_result["name"],
                        "city_name_en": first_result["name_en"],
                        "suggested": True
                    }
                
                return {"success": False, "error": f"City '{city_name}' not found"}
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error getting city ID: {str(e)}")
            return {"error": str(e)}
    
    def get_brands_by_city(self, city_id: int) -> Dict[str, Any]:
        """Get brands available in city"""
        try:
            db = self._get_db_session()
            try:
                brands = data_api.get_brands_by_city(db, city_id)
                return {"success": True, "data": brands}
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error fetching brands: {str(e)}")
            return {"error": str(e)}
    
    def get_products_by_brand(self, brand_id: int) -> Dict[str, Any]:
        """Get products by brand"""
        try:
            db = self._get_db_session()
            try:
                products = data_api.get_products_by_brand(db, brand_id)
                return {"success": True, "data": products}
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error fetching products: {str(e)}")
            return {"error": str(e)}
    
    def search_cities(self, query: str) -> Dict[str, Any]:
        """Search cities by query"""
        try:
            db = self._get_db_session()
            try:
                results = data_api.search_cities(db, query)
                return {"success": True, "data": results}
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error searching cities: {str(e)}")
            return {"error": str(e)}
    
    def check_city_availability(self, city_name: str, item_type: str, item_name: str) -> Dict[str, Any]:
        """Check availability of brand/product in city"""
        try:
            db = self._get_db_session()
            try:
                # Get city first
                city_result = self.get_city_id_by_name(city_name)
                if not city_result.get("success"):
                    return city_result
                
                city_id = city_result["city_id"]
                
                if item_type == "brand":
                    brands = data_api.get_brands_by_city(db, city_id)
                    available = any(item_name.lower() in brand.get("title", "").lower() for brand in brands)
                    return {"success": True, "available": available, "type": "brand"}
                else:
                    # For products, we'd need to check across all brands in the city
                    brands = data_api.get_brands_by_city(db, city_id)
                    for brand in brands:
                        products = data_api.get_products_by_brand(db, brand["id"])
                        if any(item_name.lower() in product.get("name", "").lower() for product in products):
                            return {"success": True, "available": True, "type": "product"}
                    return {"success": True, "available": False, "type": "product"}
                    
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error checking availability: {str(e)}")
            return {"error": str(e)}

# Singleton instance
query_agent = QueryAgent() 
