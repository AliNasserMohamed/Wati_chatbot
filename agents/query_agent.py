import os
from typing import List, Dict, Any
import aiohttp
import json
import openai
from database.db_models import UserSession
from sqlalchemy.orm import Session
from utils.language_utils import language_handler

class QueryAgent:
    def __init__(self):
        self.api_base_url = os.getenv("API_BASE_URL")
        self.api_key = os.getenv("API_KEY")
        self.openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    async def get_cities(self) -> List[Dict[str, Any]]:
        """Get list of all available cities."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.api_base_url}/cities",
                headers={"Authorization": f"Bearer {self.api_key}"}
            ) as response:
                return await response.json()

    async def get_brands_by_region(self, city_id: str) -> List[Dict[str, Any]]:
        """Get brands available in a specific region/city."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.api_base_url}/brands",
                params={"city_id": city_id},
                headers={"Authorization": f"Bearer {self.api_key}"}
            ) as response:
                return await response.json()

    async def get_products_by_brand(self, brand_id: str) -> List[Dict[str, Any]]:
        """Get products available for a specific brand."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.api_base_url}/products",
                params={"brand_id": brand_id},
                headers={"Authorization": f"Bearer {self.api_key}"}
            ) as response:
                return await response.json()

    async def get_user_orders(self, phone_number: str) -> List[Dict[str, Any]]:
        """Get order history for a user by phone number."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.api_base_url}/orders",
                params={"phone_number": phone_number},
                headers={"Authorization": f"Bearer {self.api_key}"}
            ) as response:
                return await response.json()

    async def format_response_in_arabic(self, intent: str, data: List[Dict[str, Any]]) -> str:
        """Format the response data in Saudi Arabic."""
        if intent == "list_cities":
            cities_list = "\n".join([f"- {city['name']}" for city in data])
            return f"""
            المدن المتوفرة عندنا:
            {cities_list}
            
            اي مدينة تبي تختار؟
            """
        
        elif intent == "list_brands":
            brands_list = "\n".join([f"- {brand['name']}" for brand in data])
            return f"""
            الماركات المتوفرة:
            {brands_list}
            
            اي ماركة تفضل؟
            """
        
        elif intent == "list_products":
            products_list = "\n".join([f"- {product['name']}: {product['price']} ريال" for product in data])
            return f"""
            المنتجات المتوفرة:
            {products_list}
            
            اي منتج تبي تطلب؟
            """
        
        elif intent == "check_orders":
            if not data:
                return language_handler.get_default_responses('ar')['NO_ORDERS']
            
            orders_list = "\n".join([
                f"- طلب رقم {order['id']}: {order['status']} ({order['date']})"
                for order in data
            ])
            return f"""
            طلباتك:
            {orders_list}
            """

    async def handle_query(self, text: str, phone_number: str, db: Session) -> str:
        """Process user queries and return appropriate responses."""
        # Get or create user session
        session = db.query(UserSession).filter_by(user_id=phone_number).first()
        context = json.loads(session.context) if session and session.context else {}

        # Detect language
        language = language_handler.detect_language(text)

        # If message is in English, translate to Arabic first
        if language == 'en':
            text = await language_handler.translate_to_arabic(text)

        # Use OpenAI to understand the query intent
        system_prompt = """
        أنت مساعد متخصص في فهم استفسارات العملاء.
        حدد نوع الاستفسار من الخيارات التالية:
        - list_cities: إذا كان العميل يسأل عن المدن المتوفرة
        - list_brands: إذا كان العميل يسأل عن الماركات المتوفرة
        - list_products: إذا كان العميل يسأل عن المنتجات
        - check_orders: إذا كان العميل يسأل عن طلباته

        اكتب فقط نوع الاستفسار بدون أي إضافات.
        """

        intent = await language_handler.process_with_openai(text, system_prompt)

        try:
            if intent == "list_cities":
                cities = await self.get_cities()
                return await self.format_response_in_arabic("list_cities", cities)

            elif intent == "list_brands":
                if "city_id" not in context:
                    return language_handler.get_default_responses('ar')['CITY_FIRST']
                brands = await self.get_brands_by_region(context["city_id"])
                return await self.format_response_in_arabic("list_brands", brands)

            elif intent == "list_products":
                if "brand_id" not in context:
                    return language_handler.get_default_responses('ar')['BRAND_FIRST']
                products = await self.get_products_by_brand(context["brand_id"])
                return await self.format_response_in_arabic("list_products", products)

            elif intent == "check_orders":
                orders = await self.get_user_orders(phone_number)
                return await self.format_response_in_arabic("check_orders", orders)

            else:
                return language_handler.get_default_responses('ar')['UNKNOWN']

        except Exception as e:
            print(f"Error handling query: {str(e)}")
            return language_handler.get_default_responses('ar')['ORDER_ERROR']

query_agent = QueryAgent() 