#!/usr/bin/env python3

import requests
import json
import logging
import asyncio
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
            "search_cities": self.search_cities,
            "search_products": self.search_products
        }
        
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
                "description": "Get the internal city ID from a city name (Arabic or English). Use this as a helper function when you need to find a city ID before calling other functions that require city_id parameter. Essential for getting brands or products for a specific city.",
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
                "description": "Get all water brands available in a specific city. Use this when user asks about brands in a particular city, what brands are available in their location, or water companies serving a city. You must call get_city_id_by_name first to get the city_id.",
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
                "description": "Get all water products offered by a specific brand. Use this when user asks about products from a specific brand, product prices, product sizes/packing, or available water products. Returns product_id, product_title, product_packing, and product_contract_price.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "brand_id": {
                            "type": "integer",
                            "description": "Brand ID (get this from get_brands_by_city response)"
                        }
                    },
                    "required": ["brand_id"]
                }
            },
            {
                "name": "search_cities",
                "description": "Search for cities by name. Use this when user mentions a city name and you want to verify it exists or find similar city names.",
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
                "name": "search_products",
                "description": "Search for products by name or keyword. Use this when user asks about specific product types, sizes, or product names across all brands.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search term for product name or keyword"
                        }
                    },
                    "required": ["query"]
                }
            }
        ]
    
    def _get_db_session(self):
        """Get database session"""
        from database.db_utils import SessionLocal
        return SessionLocal()
    
    def get_all_cities(self) -> Dict[str, Any]:
        """Get complete list of all cities we serve"""
        try:
            db = self._get_db_session()
            try:
                cities = data_api.get_all_cities(db)
                return {"success": True, "data": cities}
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error fetching cities: {str(e)}")
            return {"error": f"Failed to get cities: {str(e)}"}
    
    def get_city_id_by_name(self, city_name: str) -> Dict[str, Any]:
        """Get city ID by name (helper function)"""
        try:
            db = self._get_db_session()
            try:
                # Get all cities and find matching one
                cities = data_api.get_all_cities(db)
                
                for city in cities:
                    # Check if city name matches (case insensitive)
                    if (city_name.lower() in city.get("name", "").lower() or 
                        city_name.lower() in city.get("name_en", "").lower()):
                        return {
                            "success": True,
                            "city_id": city["id"],
                            "city_name": city["name"],
                            "city_name_en": city["name_en"]
                        }
                
                # If no exact match, try search
                search_results = data_api.search_cities(db, city_name)
                if search_results:
                    first_result = search_results[0]
                    return {
                        "success": True,
                        "city_id": first_result["id"],
                        "city_name": first_result["name"],
                        "city_name_en": first_result["name_en"]
                    }
                
                return {
                    "success": False,
                    "error": f"City '{city_name}' not found. Please check the city name."
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
                return {"success": True, "data": brands}
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
                return {"success": True, "data": products}
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
                return {"success": True, "data": cities}
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error searching cities: {str(e)}")
            return {"error": f"Failed to search cities: {str(e)}"}
    
    def search_products(self, query: str) -> Dict[str, Any]:
        """Search products by name or keyword"""
        try:
            db = self._get_db_session()
            try:
                products = data_api.search_products(db, query)
                return {"success": True, "data": products}
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error searching products: {str(e)}")
            return {"error": f"Failed to search products: {str(e)}"}
    
    async def process_query(self, user_message: str, conversation_history: List[Dict] = None) -> str:
        """
        Process user query using OpenAI with function calling capabilities
        Limited to maximum 3 function calls per query to prevent excessive API usage
        """
        max_function_calls = 3
        function_call_count = 0
        
        try:
            # Simple fallback for common queries if OpenAI is rate limited
            if self._should_use_fallback(user_message):
                return await self._handle_simple_query(user_message)
            
            # Prepare conversation history
            messages = []
            
            # System message with instructions
            system_message = {
                "role": "system",
                "content": """أنت مساعد ذكي لخدمة توصيل المياه في المملكة العربية السعودية. 

مهامك:
1. مساعدة العملاء في العثور على المدن المتاحة للخدمة
2. عرض العلامات التجارية للمياه المتاحة في كل مدينة  
3. عرض منتجات المياه وأسعارها من كل علامة تجارية
4. الإجابة على الاستفسارات بطريقة ودودة ومفيدة

قواعد مهمة:
- استخدم الوظائف المتاحة للحصول على معلومات حديثة ودقيقة
- إذا سأل المستخدم عن مدينة معينة، استخدم get_city_id_by_name أولاً ثم get_brands_by_city
- إذا سأل عن منتجات علامة تجارية، استخدم get_products_by_brand
- إذا كانت المعلومات غير واضحة، اطلب توضيح من المستخدم
- أجب باللغة العربية بشكل أساسي إلا إذا سأل المستخدم بالإنجليزية
- اجعل إجاباتك مختصرة ومفيدة

أمثلة على الأسئلة:
- "ما هي المدن المتاحة؟" → استخدم get_all_cities
- "ما هي العلامات التجارية في الرياض؟" → استخدم get_city_id_by_name ثم get_brands_by_city  
- "ما هي منتجات شركة معينة؟" → استخدم get_products_by_brand"""
            }
            messages.append(system_message)
            
            # Add conversation history if provided (fix datetime serialization)
            if conversation_history:
                for msg in conversation_history[-3:]:  # Reduced to 3 messages for fewer tokens
                    # Create a clean message without datetime objects
                    clean_msg = {
                        "role": msg.get("role", "user"),
                        "content": msg.get("content", "")
                    }
                    # Skip empty messages
                    if clean_msg["content"]:
                        messages.append(clean_msg)
            
            # Add current user message
            messages.append({"role": "user", "content": user_message})
            
            # Main function calling loop with retry logic
            while function_call_count < max_function_calls:
                try:
                    # Make request to OpenAI with function calling (using GPT-3.5-turbo)
                    response = await self.openai_client.chat.completions.create(
                        model="gpt-3.5-turbo",  # Changed from gpt-4 to avoid rate limits
                        messages=messages,
                        functions=self.function_definitions,
                        function_call="auto",
                        temperature=0.3,
                        max_tokens=800  # Reduced tokens to stay within limits
                    )
                    
                    message = response.choices[0].message
                    
                    # Check if model wants to call a function
                    if message.function_call:
                        function_call_count += 1
                        function_name = message.function_call.name
                        
                        try:
                            function_args = json.loads(message.function_call.arguments)
                        except json.JSONDecodeError:
                            logger.error(f"Invalid function arguments: {message.function_call.arguments}")
                            return "عذراً، حدث خطأ في معالجة طلبك. الرجاء إعادة صياغة السؤال."
                        
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
                            return f"خطأ: الوظيفة '{function_name}' غير متاحة."
                    else:
                        # No function call, return the response
                        final_response = message.content
                        if final_response:
                            logger.info(f"Query completed after {function_call_count} function calls")
                            return final_response
                        else:
                            return "عذراً، لم أتمكن من معالجة طلبك. الرجاء المحاولة مرة أخرى."
                
                except Exception as api_error:
                    if "rate_limit" in str(api_error).lower():
                        logger.warning(f"Rate limit hit, trying fallback method...")
                        return await self._handle_simple_query(user_message)
                    else:
                        logger.error(f"OpenAI API error: {str(api_error)}")
                        return await self._handle_simple_query(user_message)
            
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
                    return "تم الوصول للحد الأقصى من العمليات. الرجاء إعادة صياغة السؤال."
                    
            except Exception as e:
                logger.error(f"Final response generation failed: {str(e)}")
                return await self._handle_simple_query(user_message)

        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            return await self._handle_simple_query(user_message)
    
    def _should_use_fallback(self, message: str) -> bool:
        """Check if we should use simple fallback instead of OpenAI"""
        # For now, always try OpenAI first
        return False
    
    async def _handle_simple_query(self, message: str) -> str:
        """Simple fallback handler for common queries without OpenAI"""
        try:
            message_lower = message.lower()
            
            # Handle city/brand queries
            if any(word in message_lower for word in ['مدن', 'مدينة', 'cities', 'city']):
                if any(word in message for word in ['متاحة', 'متوفرة', 'available']):
                    # List all cities
                    cities_result = self.get_all_cities()
                    if cities_result.get('success') and cities_result.get('data'):
                        cities = cities_result['data'][:10]  # First 10 cities
                        city_list = '\n'.join([f"• {city['name']} ({city.get('name_en', '')})" for city in cities])
                        return f"المدن المتاحة لخدمة توصيل المياه:\n\n{city_list}\n\nوالمزيد من المدن الأخرى متاحة أيضاً."
            
            # Handle brand queries for specific cities
            city_names = ['جازان', 'jazan', 'الرياض', 'riyadh', 'جدة', 'jeddah', 'الدمام', 'dammam']
            for city_name in city_names:
                if city_name in message_lower:
                    if any(word in message_lower for word in ['مارك', 'علامة', 'شرك', 'brand']):
                        # Get brands for this city
                        city_result = self.get_city_id_by_name(city_name)
                        if city_result.get('success'):
                            city_id = city_result['city_id']
                            brands_result = self.get_brands_by_city(city_id)
                            if brands_result.get('success') and brands_result.get('data'):
                                brands = brands_result['data']
                                if brands:
                                    brand_list = '\n'.join([f"• {brand['title']}" for brand in brands])
                                    return f"العلامات التجارية للمياه المتوفرة في {city_result['city_name']}:\n\n{brand_list}"
                                else:
                                    return f"عذراً، لا توجد علامات تجارية مسجلة حالياً في {city_result['city_name']}. الرجاء التواصل معنا لمزيد من المعلومات."
            
            # Handle product queries
            if any(word in message_lower for word in ['منتج', 'product', 'مياه']):
                if any(word in message_lower for word in ['بحث', 'search', 'أبحث']):
                    products_result = self.search_products("مياه")
                    if products_result.get('success') and products_result.get('data'):
                        products = products_result['data'][:5]  # First 5 products
                        product_list = '\n'.join([
                            f"• {product['product_title']} - {product.get('product_contract_price', 'غير محدد')} ريال"
                            for product in products
                        ])
                        return f"منتجات المياه المتاحة:\n\n{product_list}\n\nلمزيد من المنتجات، الرجاء تحديد العلامة التجارية."
            
            # Default response
            return "أهلاً وسهلاً! أنا هنا لمساعدتك في:\n\n• معرفة المدن المتاحة للخدمة\n• العلامات التجارية في كل مدينة\n• منتجات المياه والأسعار\n\nما الذي تود الاستفسار عنه؟"
            
        except Exception as e:
            logger.error(f"Fallback handler error: {str(e)}")
            return "أهلاً بك في خدمة آبار لتوصيل المياه. الرجاء المحاولة مرة أخرى أو التواصل مع فريق الدعم."

# Singleton instance
query_agent = QueryAgent() 