#!/usr/bin/env python3

import requests
import json
import logging
from typing import Dict, List, Any, Optional
from openai import AsyncOpenAI
import os
from dotenv import load_dotenv
from database.db_models import UserSession
from sqlalchemy.orm import Session
from utils.language_utils import language_handler

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
    
    def get_all_cities(self) -> Dict[str, Any]:
        """Get complete list of all cities we serve"""
        try:
            response = requests.get(f"{self.api_base_url}/cities", timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching cities: {str(e)}")
            return {"error": f"Failed to get cities: {str(e)}"}
    
    def get_city_id_by_name(self, city_name: str) -> Dict[str, Any]:
        """Get city ID by name (helper function)"""
        try:
            # First try to find exact city
            cities_response = requests.get(f"{self.api_base_url}/cities", timeout=10)
            cities_response.raise_for_status()
            cities_data = cities_response.json()
            
            if cities_data.get("success") and cities_data.get("data"):
                for city in cities_data["data"]:
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
                search_response = requests.get(f"{self.api_base_url}/cities/search", 
                                            params={"q": city_name}, timeout=10)
                search_response.raise_for_status()
                search_data = search_response.json()
                
                if search_data.get("success") and search_data.get("data"):
                    first_result = search_data["data"][0]
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
            
        except Exception as e:
            logger.error(f"Error finding city ID for {city_name}: {str(e)}")
            return {"error": f"Failed to find city: {str(e)}"}
    
    def get_brands_by_city(self, city_id: int) -> Dict[str, Any]:
        """Get brands available in a specific city"""
        try:
            response = requests.get(f"{self.api_base_url}/cities/{city_id}/brands", timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching brands for city {city_id}: {str(e)}")
            return {"error": f"Failed to get brands: {str(e)}"}
    
    def get_products_by_brand(self, brand_id: int) -> Dict[str, Any]:
        """Get products offered by a specific brand"""
        try:
            response = requests.get(f"{self.api_base_url}/brands/{brand_id}/products", timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching products for brand {brand_id}: {str(e)}")
            return {"error": f"Failed to get products: {str(e)}"}
    
    def search_cities(self, query: str) -> Dict[str, Any]:
        """Search cities by name"""
        try:
            response = requests.get(f"{self.api_base_url}/cities/search", 
                                  params={"q": query}, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error searching cities: {str(e)}")
            return {"error": f"Failed to search cities: {str(e)}"}
    
    def search_products(self, query: str) -> Dict[str, Any]:
        """Search products by name or keyword"""
        try:
            response = requests.get(f"{self.api_base_url}/products/search", 
                                  params={"q": query}, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error searching products: {str(e)}")
            return {"error": f"Failed to search products: {str(e)}"}
    
    async def process_query(self, user_message: str, conversation_history: List[Dict] = None) -> str:
        """
        Process user query using OpenAI with function calling capabilities
        """
        try:
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

أمثلة على الأسئلة:
- "ما هي المدن المتاحة؟" → استخدم get_all_cities
- "ما هي العلامات التجارية في الرياض؟" → استخدم get_city_id_by_name ثم get_brands_by_city  
- "ما هي منتجات شركة معينة؟" → استخدم get_products_by_brand"""
            }
            messages.append(system_message)
            
            # Add conversation history if provided (fix datetime serialization)
            if conversation_history:
                for msg in conversation_history[-5:]:  # Last 5 messages for context
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
            
            # Make request to OpenAI with function calling
            response = await self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=messages,
                functions=self.function_definitions,
                function_call="auto",
                temperature=0.3,
                max_tokens=1500
            )
            
            message = response.choices[0].message
            
            # Check if model wants to call a function
            if message.function_call:
                function_name = message.function_call.name
                function_args = json.loads(message.function_call.arguments)
                
                logger.info(f"Calling function: {function_name} with args: {function_args}")
                
                # Call the requested function
                if function_name in self.available_functions:
                    function_result = self.available_functions[function_name](**function_args)
                    
                    # Add function result to conversation
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
                    
                    # Get final response with function result
                    final_response = await self.openai_client.chat.completions.create(
                        model="gpt-4",
                        messages=messages,
                        temperature=0.3,
                        max_tokens=1500
                    )
                    
                    return final_response.choices[0].message.content
                else:
                    return f"خطأ: الوظيفة '{function_name}' غير متاحة."
            else:
                # No function call, return direct response
                return message.content

        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            return f"عذراً، حدث خطأ في معالجة استفسارك. الرجاء المحاولة مرة أخرى.\nالخطأ: {str(e)}"

# Singleton instance
query_agent = QueryAgent() 