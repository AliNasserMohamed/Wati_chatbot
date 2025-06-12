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
    
    async def process_query(self, user_message: str, conversation_history: List[Dict] = None, user_language: str = 'ar') -> str:
        """
        Process user query using OpenAI with function calling capabilities
        Limited to maximum 3 function calls per query to prevent excessive API usage
        Enhanced with language detection and proper conversation history handling
        ALL messages now go through the LLM - no fast replies or fallbacks
        """
        print(f"Processing query: {user_message} (Language: {user_language})")
        max_function_calls = 3
        function_call_count = 0
        
        try:
            # Prepare conversation history
            messages = []
            
            # System message with instructions based on user language
            if user_language == 'en':
                system_message = {
                    "role": "system",
                    "content": """You are a smart assistant for water delivery service in Saudi Arabia.

Your tasks:
1. Help customers find available cities for service
2. Show water brands available in each city
3. Display water products and their prices from each brand
4. Answer inquiries in a helpful manner
5. Ask friendly questions when you need specific information

Typo and Spelling Handling:
- Users often make typos in city names (e.g., "رياص" instead of "رياض", "جده" instead of "جدة")
- When a city name doesn't match exactly, use search_cities function to find similar cities
- Be understanding and helpful with spelling mistakes
- If you find a similar city, confirm with the user: "Did you mean [correct city name]?"

Friendly Communication Guidelines:
- When asking about city: "Which city are you in?" or "What city would you like delivery to?"
- When asking about brands: "Which brand interests you in [city]?"
- When asking about products: "Which products would you like to see from [brand]?"
- Be warm and helpful, not robotic
- If they mention a city that doesn't exist, gently suggest: "I couldn't find that city, but we serve [similar cities]. Which one is closest to you?"

Important rules:
- Always use available functions to get updated information
- For city queries: try get_city_id_by_name first, if fails use search_cities
- Be patient with typos and spelling variations
- Respond in English since the user is communicating in English
- Keep responses helpful and conversational

Examples of friendly responses:
- "What brands are available?" → "Which city are you in? I'll show you all the brands we deliver there!"
- "Do you deliver to my area?" → "Which city are you located in? I'll check our delivery coverage for you!"
- User writes "رياص" → "Did you mean Riyadh (الرياض)? We have great water delivery options there!"

Be helpful, understanding, and always ready to assist with typos or unclear requests."""
                }
            else:
                system_message = {
                    "role": "system",
                    "content": """أنت مساعد ذكي لخدمة توصيل المياه في المملكة العربية السعودية. 

مهامك:
1. مساعدة العملاء في العثور على المدن المتاحة للخدمة
2. عرض العلامات التجارية للمياه المتاحة في كل مدينة  
3. عرض منتجات المياه وأسعارها من كل علامة تجارية
4. الإجابة على الاستفسارات بطريقة مفيدة ودودة
5. طرح أسئلة ودودة عندما تحتاج معلومات محددة

التعامل مع الأخطاء الإملائية:
- العملاء غالباً يكتبون أسماء المدن بأخطاء إملائية (مثل "رياص" بدلاً من "رياض"، "جده" بدلاً من "جدة")
- عندما لا يتطابق اسم المدينة تماماً، استخدم وظيفة search_cities للبحث عن مدن مشابهة
- كن متفهماً ومساعداً مع الأخطاء الإملائية
- إذا وجدت مدينة مشابهة، تأكد من العميل: "هل تقصد [اسم المدينة الصحيح]؟"

إرشادات التواصل الودود:
- عند السؤال عن المدينة: "في أي مدينة أنت؟" أو "أي مدينة تريد التوصيل لها؟"
- عند السؤال عن العلامات التجارية: "أي علامة تجارية تهمك في [المدينة]؟"
- عند السؤال عن المنتجات: "أي منتجات تريد تشوف من [العلامة التجارية]؟"
- كن ودود ومساعد، مش آلي
- إذا ذكر مدينة غير موجودة، اقترح بلطف: "ما لقيت هذي المدينة، بس نوصل لـ [مدن مشابهة]. أي وحدة أقرب لك؟"

قواعد مهمة:
- استخدم دائماً الوظائف المتاحة للحصول على معلومات حديثة
- للاستفسارات عن المدن: جرب get_city_id_by_name أولاً، إذا فشل استخدم search_cities
- كن صبور مع الأخطاء الإملائية والتنويعات
- أجب باللغة العربية لأن المستخدم يتواصل بالعربية
- خلي ردودك مفيدة وودودة

أمثلة على الردود الودودة:
- "ما هي العلامات التجارية المتاحة؟" → "في أي مدينة أنت؟ راح أعرض لك كل العلامات التجارية اللي نوصلها هناك!"
- "هل توصلون لمنطقتي؟" → "في أي مدينة أنت؟ راح أتأكد لك من التغطية!"
- المستخدم يكتب "رياص" → "تقصد الرياض؟ عندنا خيارات ممتازة لتوصيل المياه هناك!"

كن مساعد ومتفهم ودائماً مستعد تساعد مع الأخطاء الإملائية أو الطلبات غير الواضحة."""
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
                    response = await self.openai_client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=messages,
                        functions=self.function_definitions,
                        function_call="auto",
                        temperature=0.3,
                        max_tokens=800
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