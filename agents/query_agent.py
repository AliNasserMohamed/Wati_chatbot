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
        # Use local server API endpoints instead of external ones
        self.api_base_url = os.getenv("LOCAL_API_BASE_URL", "http://localhost:8000/api")
        self.external_api_key = os.getenv("EXTERNAL_API_KEY")  # For external APIs if needed
        self.openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    async def get_cities(self) -> List[Dict[str, Any]]:
        """Get list of all available cities from local database."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.api_base_url}/cities") as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("data", [])
                    else:
                        print(f"❌ Error fetching cities: HTTP {response.status}")
                        return []
        except Exception as e:
            print(f"❌ Error fetching cities: {str(e)}")
            return []

    async def get_brands_by_region(self, city_id: str) -> List[Dict[str, Any]]:
        """Get brands available in a specific region/city from local database."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.api_base_url}/cities/{city_id}/brands") as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("data", [])
                    else:
                        print(f"❌ Error fetching brands for city {city_id}: HTTP {response.status}")
                        return []
        except Exception as e:
            print(f"❌ Error fetching brands for city {city_id}: {str(e)}")
            return []

    async def get_products_by_brand(self, brand_id: str) -> List[Dict[str, Any]]:
        """Get products available for a specific brand from local database."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.api_base_url}/brands/{brand_id}/products") as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("data", [])
                    else:
                        print(f"❌ Error fetching products for brand {brand_id}: HTTP {response.status}")
                        return []
        except Exception as e:
            print(f"❌ Error fetching products for brand {brand_id}: {str(e)}")
            return []

    async def get_user_orders(self, phone_number: str) -> List[Dict[str, Any]]:
        """Get order history for a user by phone number."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.api_base_url}/orders",
                params={"phone_number": phone_number},
                headers={"Authorization": f"Bearer {self.external_api_key}"}
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

    async def handle_query(self, message: str, phone_number: str, db: Session) -> str:
        """Handle user queries about cities, brands, and products."""
        try:
            print(f"🔍 Processing query: {message}")
            
            # First check if we have data in the database
            cities = await self.get_cities()
            if not cities:
                return "آسف، البيانات غير متوفرة حالياً. فريقنا راح يحدث النظام قريباً."
            
            # Use OpenAI to understand the query and provide appropriate response
            system_prompt = """
            أنت مساعد ذكي لتطبيق آبار توصيل المياه في المملكة العربية السعودية.
            يمكنك مساعدة العملاء بالاستفسارات التالية:
            1. المدن المتوفرة للخدمة
            2. الماركات المتوفرة في كل مدينة
            3. المنتجات المتوفرة لكل ماركة
            4. معلومات عامة عن الخدمة
            
            استخدم اللهجة السعودية في الرد وكن مفيداً ومفهوماً.
            """
            
            # Get available cities for context
            cities_text = ", ".join([city.get("name", "") for city in cities[:10]])  # First 10 cities
            
            user_prompt = f"""
            الاستفسار من العميل: {message}
            
            المدن المتوفرة حالياً: {cities_text}
            
            أجب على استفسار العميل بشكل مفيد ومفصل.
            """
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )
            
            answer = response.choices[0].message.content
            print(f"✅ Generated response: {answer[:100]}...")
            
            return answer
            
        except Exception as e:
            print(f"❌ Error handling query: {str(e)}")
            return "معذرة، فيه خطأ صار وأنت تسوي طلبك. جرب تاني مرة."

query_agent = QueryAgent() 