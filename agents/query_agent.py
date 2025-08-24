#!/usr/bin/env python3

import requests
import json
import logging
import asyncio
import time
from typing import Dict, List, Any, Optional
from openai import AsyncOpenAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
import os
from dotenv import load_dotenv
from database.db_models import UserSession
from sqlalchemy.orm import Session
from utils.language_utils import language_handler
from services.data_api import data_api
from database.db_utils import get_db
from database.district_utils import district_lookup
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
        
        # Initialize LangChain OpenAI client for tracing
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        
        # Keep AsyncOpenAI for fallback compatibility
        self.openai_client = AsyncOpenAI(api_key=openai_api_key)
        
        # Initialize LangChain client for better tracing
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.3,
            api_key=openai_api_key,
            tags=["query-agent", "abar-chatbot"]
        )
        
        # Rate limiting settings (configurable via environment variables)
        self.last_request_time = 0
        self.min_request_interval = float(os.getenv("OPENAI_MIN_REQUEST_INTERVAL", "0.5"))  # Default 500ms between requests
        self.max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "3"))  # Default 3 retries
        self.base_delay = float(os.getenv("OPENAI_BASE_DELAY", "1"))  # Default 1 second base delay
        
        # Define available functions for the LLM
        self.available_functions = {
            "get_all_cities": lambda user_language='ar': self.get_all_cities(user_language),
            "get_brands_by_city_name": lambda city_name, user_language='ar': self.get_brands_by_city_name(city_name, user_language),
            "get_products_by_brand_and_city_name": lambda brand_name, city_name, user_language='ar': self.get_products_by_brand_and_city_name(brand_name, city_name, user_language),
            "search_cities": self.search_cities,
            "search_brands_in_city": self.search_brands_in_city,
            "get_cheapest_products_by_city_name": self.get_cheapest_products_by_city_name
        }
        
        # Classification prompts for message relevance
        self.classification_prompt_ar = """أنت مصنف رسائل ذكي لشركة توصيل المياه. مهمتك تحديد ما إذا كانت الرسالة متعلقة بخدمات الشركة أم لا.

        سيتم تقديم:
        1. تاريخ المحادثة الحديث (إذا كان متوفراً)
        2. الرسالة الحالية التي تحتاج للتصنيف

        راجع تاريخ المحادثة لفهم السياق بشكل كامل قبل تصنيف الرسالة الحالية.

        الرسائل المتعلقة بالخدمة تشمل فقط:
        ✅ أسئلة عن المدن المتاحة للتوصيل
        ✅ أسئلة عن العلامات التجارية للمياه
        ✅ أسئلة عن المنتجات والأسعار
        ✅ طلبات معرفة التوفر في مدينة معينة أو حي معين
        ✅ أسئلة عن توفر التوصيل للمدن مثل  ("فيه توصيل جدة"، "هل يوجد توصيل الرياض"، "متوفر توصيل الدمام")
        ✅ أسئلة عن أحجام المياه والعبوات
        ✅ أسئلة عن الدبات والقوارير والجوالين (عبوات المياه الكبيرة)
        ✅ ذكر أسماء العلامات التجارية مثل (نستله، أكوافينا، العين، القصيم، المراعي، حلوه، وغيرها)
        ✅ أي ذكر لـ "مياه" مع أحجام أو أوصاف المنتجات (مثل "مياه حلوه 200 مل", "مياه الشكل الجديد", "مياه صغيرة")
        ✅ أسئلة التوفر مع ذكر "مياه" ("عندكم مياه", "يوجد مياه", "متوفر مياه")
        ✅ وصف منتجات المياه ("الشكل الجديد", "الحجم الجديد", "النوع الجديد", أي وصف مع كلمة "مياه")
        ✅ الرد بـ "نعم" أو "أي" عندما نسأل عن منتج معين في سياق المحادثة
        ✅ أسئلة عن الأسعار الإجمالية أو قوائم الأسعار
        ✅ طلبات الطلب أو الشراء ("أريد أطلب"، "كيف أطلب"، "أريد أشتري"، "أبي أطلب")
        ✅ طلبات توصيل المياه مع ذكر العلامة التجارية ("أريد توصيل مياه نستله"، "ارغب بتوصيل مياه راين")
        ✅ الردود على أسئلة متعلقة بالمياه والعلامات التجارية في تاريخ المحادثة

        🚨 تمييز مهم جداً - أسئلة التوصيل قبل وبعد الطلب:
        ✅ أسئلة التوصيل قبل الطلب (متعلقة بالخدمة):
        - "فيه توصيل لمدينتي؟"، "تصلون الرياض؟"، "هل يوجد توصيل جدة؟"
        - "تقدرون توصلون لحي كذا؟"، "التوصيل متوفر في منطقتنا؟"
        - أي سؤال عن إمكانية أو توفر التوصيل لمكان معين قبل تقديم الطلب

        ❌ أسئلة التوصيل بعد الطلب (غير متعلقة بالخدمة):
        - "متى يوصل الطلب؟"، "وين المندوب؟"، "الطلب اتأخر"
        - "متى يجي المندوب؟"، "كم باقي على وصول الطلب؟"
        - أي سؤال عن حالة أو توقيت طلب تم تقديمه بالفعل

        الرسائل غير المتعلقة بالخدمة تشمل:
        ❌ التحيات العامة ("أهلاً", "مرحبا", "السلام عليكم", "صباح الخير", "مساء الخير")  
        ❌ رسائل الشكر والامتنان ("شكراً", "جزاك الله خير", "مشكور", "الله يعطيك العافية")
        ❌ المواضيع العامة غير المتعلقة بالمياه
        ❌ الأسئلة الشخصية
        ❌ طلبات المساعدة في مواضيع أخرى
        ❌ الرسائل التي تحتوي على روابط
        ❌ مشاكل متعلقة بالمندوب أو المندوبين
        ❌ شكاوي من المندوب أو طاقم التوصيل
        ❌ مشاكل التوصيل (تأخير، عدم وصول الطلب، مشاكل التوصيل)
        ❌ شكاوي خدمة العملاء أو مشاكل الخدمة
        ❌ طلبات إلغاء أو تعديل طلبات موجودة
        ❌ استفسارات عن حالة الطلب أو تتبع الطلب لة حالة التوصيل او موعد التوصيل 
        ❌ أسئلة عن مواعيد التوصيل أو وقت الوصول ("متى يوصل"، "كم يستغرق التوصيل"، "متى يجي المندوب")
        ❌ أسئلة عن وقت وصول المندوب أو مدة التوصيل
        ❌ طلبات تعديل موقع التوصيل أو العنوان ("أبغى أعدل الموقع"، "أريد أغير العنوان"، "تعديل المكان")

        تعليمات خاصة وصارمة:
        - كن صارم جداً في التصنيف - فقط الأسئلة عن المدن والعلامات التجارية والمنتجات والأسعار تعتبر متعلقة
        - 🚨 أي رسالة تحتوي على كلمة "مياه" مع وصف منتج أو حجم أو سؤال توفر تعتبر متعلقة بالخدمة
        - 🚨 مثال: "عندكم مياه حلوه الشكل الجديد 200 مل" = متعلقة بالخدمة (حتى لو كانت "حلوه" غير معروفة كعلامة تجارية)
        - 🚨 أي اسم مذكور مع "مياه" يجب اعتباره علامة تجارية محتملة = متعلق بالخدمة
        - أي رسالة تذكر "المندوب" أو "الطلب لم يصل" أو "تأخر" أو "متى يوصل" أو "متى يجي" تعتبر غير متعلقة
        - لكن طلبات "توصيل المياه" مع ذكر العلامة التجارية أو المدينة تعتبر متعلقة بالخدمة
        - 🚨 الفرق الحاسم: أسئلة "فيه توصيل؟" أو "تصلون لمدينتي؟" = متعلقة (قبل الطلب)
        - 🚨 لكن "متى يوصل؟" أو "وين المندوب؟" = غير متعلقة (بعد الطلب)
        - إذا ذكر "الطلب" أو "المندوب" أو "الطلبية" فهو يسأل عن طلب موجود (غير متعلق)
        - أي رسالة تطلب "تعديل الموقع" أو "تغيير العنوان" أو "أعدل المكان" تعتبر غير متعلقة
        - أي شكوى أو مشكلة في الخدمة تعتبر غير متعلقة
        - لا تعتبر التحيات والشكر متعلقة بالخدمة حتى لو كانت في سياق محادثة عن المياه
        - اعتبر ذكر أسماء العلامات التجارية للمياه متعلق بالخدمة فقط
        - اعتبر الرد بـ "نعم" أو "أي" متعلق بالخدمة إذا كان في سياق محادثة عن المنتجات فقط
        - انتبه لتاريخ المحادثة: إذا كانت المحادثة عن المياه والعلامات التجارية، فحتى الردود البسيطة قد تكون متعلقة

        أجب بـ "relevant" إذا كانت الرسالة متعلقة بالمنتجات والأسعار والعلامات التجارية والمدن فقط، أو "not_relevant" لأي شيء آخر."""

        self.classification_prompt_en = """You are a smart message classifier for a water delivery company. Your task is to determine if a message is related to the company's services or not.

            Service-related messages include ONLY:
            ✅ Questions about available cities for delivery
            ✅ Questions about water brands
            ✅ Questions about products and prices
            ✅ Requests to check availability in specific cities
            ✅ Questions about delivery availability to cities BEFORE placing order ("is there delivery to Jeddah", "delivery available in Riyadh", "do you deliver to Dammam", "can you deliver to our area?")
            ✅ Questions about water sizes and packaging
            ✅ Questions about water gallons, jugs, and large water containers
            ✅ Mentioning brand names like (Nestle, Aquafina, Alain, Qassim, Almarai, Helwa, etc.)
            ✅ Any mention of "water" with product sizes or descriptions ("Helwa water 200ml", "water new design", "small water")
            ✅ Availability questions with "water" ("do you have water", "water available", "any water")
            ✅ Water product descriptions ("new design", "new size", "new type", any description with "water")
            ✅ Replying with "yes" when we ask about a specific product
            ✅ Questions about total prices or price lists
            ✅ Order requests or purchase inquiries ("I want to order", "how to order", "I want to buy")
            ✅ Water delivery requests with brand mentions ("I want Nestle water delivery", "I need Rain water delivery")

            🚨 CRITICAL DISTINCTION - Pre-Order vs Post-Order Delivery Questions:
            ✅ Pre-Order Delivery Questions (SERVICE-RELATED):
            - "Do you deliver to my city?", "Is delivery available in Riyadh?", "Can you deliver to Jeddah?"
            - "Do you deliver to our neighborhood?", "Is delivery available in our area?"
            - Any question about delivery possibility or availability BEFORE placing an order

            ❌ Post-Order Delivery Questions (NOT SERVICE-RELATED):
            - "When will my order arrive?", "Where is the driver?", "My order is late"
            - "When is the driver coming?", "How long until delivery arrives?"
            - Any question about status or timing of an order that was ALREADY placed

            Non-service-related messages include:
            ❌ General greetings ("hello", "hi", "good morning", "good evening", "how are you")
            ❌ Thank you messages ("thanks", "thank you", "appreciate it", "much obliged")
            ❌ General topics not related to water
            ❌ Personal questions
            ❌ Requests for help with other topics
            ❌ Messages containing links or URLs
            ❌ General delivery service inquiries (without mentioning specific brand or city)
            ❌ Problems related to delivery person/driver
            ❌ Complaints about delivery person or delivery staff
            ❌ Delivery problems (delays, order not arrived, delivery issues)
            ❌ Customer service complaints or service problems
            ❌ Requests to cancel or modify existing orders
            ❌ Inquiries about order status or order tracking
            ❌ Questions about delivery times or arrival times ("when will it arrive", "how long does delivery take", "when will the driver come")
            ❌ Questions about driver arrival time or delivery duration
            ❌ Requests to edit delivery location or address ("I want to change the address", "edit location", "modify delivery address")

            Special strict instructions:
            - Be very strict in classification - only questions about cities, brands, products, and prices count as relevant
            - 🚨 Any message containing "water" with product description or size or availability question counts as service-related
            - 🚨 Example: "do you have Helwa water new design 200ml" = service-related (even if "Helwa" is unknown brand)
            - 🚨 Any name mentioned with "water" should be considered potential brand = service-related
            - Any message mentioning "delivery person", "driver", "order not arrived", "delayed", "when will it arrive", or "how long" is not relevant
            - But water delivery requests with brand or city mentions are service-related
            - 🚨 CRITICAL DIFFERENCE: Questions like "do you deliver?" or "delivery available in my city?" = relevant (before order)
            - 🚨 But "when will it arrive?" or "where is the driver?" = not relevant (after order)
            - Check conversation context: If customer hasn't mentioned placing an order, they're asking about availability (relevant)
            - If they mention "my order", "the driver", or "delivery person" they're asking about existing order (not relevant)
            - Any message requesting to "edit location", "change address", or "modify delivery location" is not relevant
            - Any complaint or service problem is not relevant
            - Do not consider greetings and thanks as service-related even if they appear in water-related conversations
            - Consider mentioning water brand names as service-related only
            - Consider "yes" replies as service-related only if in context of product discussions

            Reply with "relevant" if the message is related to products, prices, brands, and cities only, or "not_relevant" for anything else."""
                    
        # Function definitions for OpenAI function calling
        self.function_definitions = [
            {
                "name": "get_all_cities",
                "description": "Get complete list of all cities we serve with water delivery. Use this when user asks about available cities, locations we serve, or wants to see all cities. Returns language-appropriate city names only (Arabic cities for Arabic conversations, English cities for English conversations).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_language": {
                            "type": "string",
                            "description": "Language of the conversation ('ar' for Arabic, 'en' for English). Determines which city names to return.",
                            "enum": ["ar", "en"],
                            "default": "ar"
                        }
                    },
                    "required": []
                }
            },
            {
                "name": "get_brands_by_city_name",
                "description": "STEP 1 in workflow: Get all water brands available in a specific city using city name. This handles fuzzy matching for incomplete or misspelled city names. Use this when customer mentions a city and you want to show available brands. Returns language-appropriate brand names only (Arabic brands for Arabic requests, English brands for English requests).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city_name": {
                            "type": "string",
                            "description": "Name of the city in Arabic or English (e.g., 'الرياض', 'Riyadh', 'جدة', 'Jeddah'). Supports partial matches and fuzzy matching."
                        },
                        "user_language": {
                            "type": "string",
                            "description": "Language of the conversation ('ar' for Arabic, 'en' for English). Determines which brand names to return.",
                            "enum": ["ar", "en"],
                            "default": "ar"
                        }
                    },
                    "required": ["city_name"]
                }
            },
            {
                "name": "get_products_by_brand_and_city_name",
                "description": "STEP 2 in workflow: Get all water products for a specific brand in a specific city using names. This handles fuzzy matching for incomplete or misspelled brand/city names. Use this when customer has specified both a brand and city. Returns language-appropriate product strings with prices and contextual message.",
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
                        },
                        "user_language": {
                            "type": "string",
                            "description": "Language of the conversation ('ar' for Arabic, 'en' for English). Determines which product names and format to return.",
                            "enum": ["ar", "en"],
                            "default": "ar"
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
                "description": "Search for brands by name within a specific city only. Use this when customer mentions a brand name that might be incomplete or misspelled and you know their city. This function can also be used to check if a specific brand is available in a city or not - if the brand exists in the city, it will be returned in the results; if not, you'll get an empty result indicating the brand is not available in that city.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "brand_name": {
                            "type": "string",
                            "description": "Brand name to search for (Arabic or English). Supports partial matches and can be used for availability checking."
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
                "name": "get_cheapest_products_by_city_name",
                "description": "Get the cheapest products in each size/packing for a specific city. Use this when user asks about cheapest prices, cheapest brands, or cheapest water in their city. Shows cheapest product from each brand in different sizes.",
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
    
    async def _call_langchain_llm(self, messages: List, max_tokens: int = 1500, temperature: float = 0.3):
        """Make LangChain LLM call for better tracing in LangSmith"""
        try:
            # Apply rate limiting (same as before)
            await self._rate_limit_delay()
            
            # Convert dict messages to LangChain message objects if needed
            langchain_messages = []
            for msg in messages:
                if isinstance(msg, dict):
                    if msg["role"] == "system":
                        langchain_messages.append(SystemMessage(content=msg["content"]))
                    elif msg["role"] == "user":
                        langchain_messages.append(HumanMessage(content=msg["content"]))
                    elif msg["role"] == "assistant":
                        langchain_messages.append(AIMessage(content=msg["content"]))
                else:
                    # Already a LangChain message object
                    langchain_messages.append(msg)
            
            # Create a temporary LLM with specific parameters for this call
            temp_llm = self.llm.bind(max_tokens=max_tokens, temperature=temperature)
            
            # Make the call (this will be traced in LangSmith)
            response = await temp_llm.ainvoke(langchain_messages)
            
            # Return in format similar to OpenAI response for compatibility
            return {"content": response.content}
            
        except Exception as e:
            logger.error(f"Error in LangChain LLM call: {str(e)}")
            raise e
    
    def _get_db_session(self):
        """Get database session"""
        from database.db_utils import SessionLocal
        return SessionLocal()
    
    def _clean_brand_name(self, brand_text: str) -> str:
        """Remove water-related prefixes from brand names and apply normalization
        Removes: مياه, موية, مياة before brand names
        Applies Arabic text normalization for better matching
        Example: 'مياه وي' -> 'وي', 'موية نقي' -> 'نقي'
        """
        from database.district_utils import DistrictLookup
        
        # Water prefixes to remove (case insensitive)
        water_prefixes = ["مياه", "موية", "مياة", "ميه", "water"]
        
        # Clean the brand text
        cleaned_text = brand_text.strip()
        
        # Remove water prefixes from the beginning
        for prefix in water_prefixes:
            # Check if text starts with the prefix followed by space
            if cleaned_text.lower().startswith(prefix.lower() + " "):
                cleaned_text = cleaned_text[len(prefix):].strip()
                break
            # Check if text starts with the prefix without space (for concatenated cases)
            elif cleaned_text.lower().startswith(prefix.lower()) and len(cleaned_text) > len(prefix):
                cleaned_text = cleaned_text[len(prefix):].strip()
                break
        
        # Apply normalization for better brand matching
        normalized_text = DistrictLookup.normalize_city_name(cleaned_text)
        
        return normalized_text
    
    async def _verify_city_extraction(self, user_message: str, conversation_history: List[Dict] = None, extracted_city: str = None, extraction_source: str = "message") -> bool:
        """Use ChatGPT to verify if the extracted city/district is correct based on the user's message and FULL conversation history"""
        try:
            print(f"🔍 [CITY VERIFICATION] Starting verification for '{extracted_city}' from {extraction_source}")
            
            # Prepare FULL context from conversation history (both user and assistant messages)
            context = ""
            if conversation_history:
                recent_messages = conversation_history[-5:]  # Last 8 messages for better context
                print(f"🔍 [CITY VERIFICATION] Using {len(recent_messages)} recent messages for context")
                
                context_lines = []
                for msg in recent_messages:
                    role = msg.get('role', 'unknown')
                    content = msg.get('content', '')
                    if role == 'user':
                        context_lines.append(f"العميل: {content}")
                    elif role == 'assistant':
                        context_lines.append(f"المساعد: {content}")
                    else:
                        context_lines.append(f"{role}: {content}")
                
                context = "\n".join(context_lines)
                context = f"تاريخ المحادثة الحديث:\n{context}\n"
                print(f"🔍 [CITY VERIFICATION] Context prepared: {len(context)} characters")
            
            # Enhanced verification prompt
            verification_prompt = f"""أنت خبير في فهم النصوص العربية واستخراج أسماء المدن والأحياء. مهمتك التحقق من صحة استخراج المدينة أو الحي.

{context}
الرسالة الحالية للعميل: "{user_message}"

استخرجنا "{extracted_city}" من {extraction_source}.

🚨 قواعد مهمة للتحقق:
1. يجب أن يكون العميل ذكر المدينة أو الحي بوضوح في رسالته أو أكد عليها
2. إذا كان المساعد قد ذكر عدة مدن وقال العميل "نعم" أو "موافق" بدون تحديد مدينة معينة - هذا خطأ
3. إذا كان المساعد يسأل "أي مدينة تريد؟" وأجاب العميل بشيء غامض - هذا خطأ
4. فقط إذا ذكر العميل اسم المدينة بوضوح أو أكد على مدينة معينة - هذا صحيح

هل استخراج "{extracted_city}" صحيح ومبرر من رسائل العميل فقط؟

أجب بـ "صحيح" إذا كان العميل ذكر المدينة بوضوح، أو "خطأ" إذا لم يذكرها أو كان غامض."""

            print(f"🔍 [CITY VERIFICATION] Sending prompt to LLM for verification")
            
            # Call LangChain for verification
            response = await self._call_langchain_llm(
                messages=[
                    {"role": "system", "content": "أنت خبير في فهم النصوص واستخراج المعلومات الجغرافية. كن دقيقاً جداً في التحقق."},
                    {"role": "user", "content": verification_prompt}
                ],
                temperature=0.1,
                max_tokens=20
            )
            
            verification_result = response["content"].strip().lower()
            is_correct = "صحيح" in verification_result
            
            print(f"🔍 [CITY VERIFICATION] Raw LLM response: '{response['content']}'")
            print(f"🔍 [CITY VERIFICATION] Verification result for '{extracted_city}': {verification_result} -> {'✅ APPROVED' if is_correct else '❌ REJECTED'}")
            
            if not is_correct:
                print(f"🚨 [CITY VERIFICATION] City '{extracted_city}' was REJECTED - user did not explicitly mention this city")
            else:
                print(f"✅ [CITY VERIFICATION] City '{extracted_city}' was APPROVED - user explicitly mentioned this city")
            
            return is_correct
            
        except Exception as e:
            print(f"🔍 [CITY VERIFICATION] ERROR in verification: {str(e)}")
            logger.error(f"Error in city extraction verification: {str(e)}")
            # On error, default to rejecting the extraction for safety
            print(f"🚨 [CITY VERIFICATION] Defaulting to REJECT due to error for safety")
            return False

    async def _extract_city_from_context(self, user_message: str, conversation_history: List[Dict] = None) -> Optional[Dict[str, Any]]:
        """Extract city information from current message and conversation history with AI verification
        Priority: 1) City in last message, 2) District in last message, 3) City in history (last 5 messages), 4) District in history (last 5 messages)"""
        try:
            
            db = self._get_db_session()
            try:
                all_cities = data_api.get_all_cities(db)
                
                # PRIORITY 1: Check for city in last message (current user message)
                if user_message:
                    # Normalize user message for better matching
                    normalized_user_message = district_lookup.normalize_city_name(user_message)
                    current_content = normalized_user_message.lower()
                    
                    for city in all_cities:
                        # Normalize both Arabic and English city names
                        city_name_ar = district_lookup.normalize_city_name(city.get("name", "")).lower()
                        city_name_en = city.get("name_en", "").lower().strip()
                        
                        # Check normalized Arabic city name
                        if city_name_ar and city_name_ar in current_content:
                            print(f"🏙️ QueryAgent: Found normalized city '{city['name']}' in last message")
                            print(f"   Original: '{city.get('name', '')}' -> Normalized: '{city_name_ar}'")
                            print(f"   User message normalized: '{normalized_user_message}'")
                            
                            # Verify extraction with ChatGPT
                            is_verified = await self._verify_city_extraction(
                                user_message, conversation_history, 
                                city['name'], "الرسالة الحالية"
                            )
                            
                            if is_verified:
                                return {
                                    "city_id": city["id"],
                                    "city_name": city["name"],
                                    "city_name_en": city["name_en"],
                                    "found_in": "current_message_city"
                                }
                        # Check English city name (no normalization needed for English)
                        elif city_name_en and city_name_en in user_message.lower():
                            print(f"🏙️ QueryAgent: Found direct city '{city['name']}' (English) in last message")
                            
                            # Verify extraction with ChatGPT
                            is_verified = await self._verify_city_extraction(
                                user_message, conversation_history, 
                                city['name'], "الرسالة الحالية"
                            )
                            
                            if is_verified:
                                return {
                                    "city_id": city["id"],
                                    "city_name": city["name"],
                                    "city_name_en": city["name_en"],
                                    "found_in": "current_message_city"
                                }
                
                # PRIORITY 2: Check for district in last message (current user message) - COMMENTED OUT
                # if user_message:
                #     district_match = district_lookup.find_district_in_message(user_message, db)
                #     print(f"🏘️ QueryAgent: District match: {district_match}")
                #     if district_match:
                #         district_name = district_match['district']
                #         city_name = district_match['city']
                #         
                #         print(f"🏘️ QueryAgent: Found district '{district_name}' -> city '{city_name}' in last message")
                #         
                #         # Verify district extraction with ChatGPT
                #         is_verified = await self._verify_city_extraction(
                #             user_message, conversation_history, 
                #             district_name, "الرسالة الحالية (حي)"
                #         )
                #         
                #         if is_verified:
                #             # Find the city details in our cities list (normalize for comparison)
                #             normalized_district_city = district_lookup.normalize_city_name(city_name)
                #             for city in all_cities:
                #                 system_city_name = city.get("name", "").strip()
                #                 normalized_system_city = district_lookup.normalize_city_name(system_city_name)
                #                 
                #                 if normalized_system_city == normalized_district_city:
                #                     print(f"🎯 QueryAgent: District-to-City mapping from last message:")
                #                     print(f"   📍 District: '{district_name}' (user is from this district)")
                #                     print(f"   🏙️ Business City: '{city['name']}' (ID: {city['id']}) - THIS will be used for brands/products")
                #                     return {
                #                         "city_id": city["id"],
                #                         "city_name": city["name"],  # ← CITY name (e.g., "الأحساء") - used for business logic
                #                         "city_name_en": city["name_en"],
                #                         "found_in": "current_message_district",
                #                         "district_name": district_name  # ← DISTRICT name (e.g., "الحمراء الأول") - context only
                #                     }
                
                # PRIORITY 3: Check for city in conversation history
                if conversation_history:
                    for message in reversed(conversation_history[-5:]):  # Check last 5 messages
                        content = message.get("content", "")
                        # Normalize conversation history content for better matching
                        normalized_content = district_lookup.normalize_city_name(content)
                        content_lower = normalized_content.lower()
                        
                        # Check if any city name appears in the message
                        for city in all_cities:
                            # Normalize city names from database
                            city_name_ar = district_lookup.normalize_city_name(city.get("name", "")).lower()
                            city_name_en = city.get("name_en", "").lower().strip()
                            
                            if city_name_ar and city_name_ar in content_lower:
                                print(f"🏙️ QueryAgent: Found normalized city in history '{city['name']}'")
                                print(f"   Original: '{city.get('name', '')}' -> Normalized: '{city_name_ar}'")
                                print(f"   History content normalized: '{normalized_content}'")
                                
                                # Verify extraction with ChatGPT
                                is_verified = await self._verify_city_extraction(
                                    user_message, conversation_history, 
                                    city['name'], "تاريخ المحادثة"
                                )
                                
                                if is_verified:
                                    return {
                                        "city_id": city["id"],
                                        "city_name": city["name"],
                                        "city_name_en": city["name_en"],
                                        "found_in": "conversation_history_city"
                                    }
                            elif city_name_en and city_name_en in content.lower():
                                print(f"🏙️ QueryAgent: Found city in history '{city['name']}' (English)")
                                
                                # Verify extraction with ChatGPT
                                is_verified = await self._verify_city_extraction(
                                    user_message, conversation_history, 
                                    city['name'], "تاريخ المحادثة"
                                )
                                
                                if is_verified:
                                    return {
                                        "city_id": city["id"],
                                        "city_name": city["name"],
                                        "city_name_en": city["name_en"],
                                        "found_in": "conversation_history_city"
                                    }
                
                # PRIORITY 4: Check for district in conversation history - COMMENTED OUT
                # if conversation_history:
                #     for message in reversed(conversation_history[-5:]):  # Check last 5 messages
                #         content = message.get("content", "")
                #         
                #         district_match = district_lookup.find_district_in_message(content, db)
                #         if district_match:
                #             district_name = district_match['district']
                #             city_name = district_match['city']
                #             
                #             print(f"🏘️ QueryAgent: Found district in history '{district_name}' -> city '{city_name}'")
                #             
                #             # Verify district extraction with ChatGPT
                #             is_verified = await self._verify_city_extraction(
                #                 user_message, conversation_history, 
                #                 district_name, "تاريخ المحادثة (حي)"
                #             )
                #             
                #             if is_verified:
                #                 # Find the city details in our cities list (normalize for comparison)
                #                 normalized_district_city = district_lookup.normalize_city_name(city_name)
                #                 for city in all_cities:
                #                     system_city_name = city.get("name", "").strip()
                #                     normalized_system_city = district_lookup.normalize_city_name(system_city_name)
                #                     
                #                     if normalized_system_city == normalized_district_city:
                #                         print(f"🎯 QueryAgent: District-to-City mapping from history:")
                #                         print(f"   📍 District: '{district_name}' (user is from this district)")
                #                         print(f"   🏙️ Business City: '{city['name']}' (ID: {city['id']}) - THIS will be used for brands/products")
                #                         return {
                #                             "city_id": city["id"],
                #                             "city_name": city["name"],  # ← CITY name - used for business logic
                #                             "city_name_en": city["name_en"],
                #                             "found_in": "conversation_history_district",
                #                             "district_name": district_name  # ← DISTRICT name - context only
                #                         }

                return None
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error extracting city from context: {str(e)}")
            return None

    async def _verify_brand_extraction(self, user_message: str, conversation_history: List[Dict] = None, extracted_brand: str = None, extraction_source: str = "message") -> bool:
        """Use ChatGPT to verify if the extracted brand is correct based on the user's message and FULL conversation history"""
        try:
            print(f"🔍 [BRAND VERIFICATION] Starting verification for '{extracted_brand}' from {extraction_source}")
            
            # Prepare FULL context from conversation history (both user and assistant messages)
            context = ""
            if conversation_history:
                recent_messages = conversation_history[-5:]  # Last 8 messages for better context
                print(f"🔍 [BRAND VERIFICATION] Using {len(recent_messages)} recent messages for context")
                
                context_lines = []
                for msg in recent_messages:
                    role = msg.get('role', 'unknown')
                    content = msg.get('content', '')
                    if role == 'user':
                        context_lines.append(f"العميل: {content}")
                    elif role == 'assistant':
                        context_lines.append(f"المساعد: {content}")
                    else:
                        context_lines.append(f"{role}: {content}")
                
                context = "\n".join(context_lines)
                context = f"تاريخ المحادثة الحديث:\n{context}\n"
                print(f"🔍 [BRAND VERIFICATION] Context prepared: {len(context)} characters")
            
            # Enhanced verification prompt
            verification_prompt = f"""أنت خبير في فهم النصوص العربية واستخراج أسماء العلامات التجارية للمياه. مهمتك التحقق من صحة استخراج العلامة التجارية.

{context}
الرسالة الحالية للعميل: "{user_message}"

استخرجنا علامة تجارية "{extracted_brand}" من {extraction_source}.

🚨 قواعد مهمة للتحقق:
1. يجب أن يكون العميل ذكر العلامة التجارية بوضوح في رسالته أو أكد عليها تحديداً
2. إذا كان المساعد قد ذكر عدة علامات تجارية وقال العميل "نعم" أو "موافق" بدون تحديد علامة معينة - هذا خطأ
3. إذا كان المساعد يسأل "أي علامة تريد؟" وأجاب العميل بشيء غامض - هذا خطأ  
4. فقط إذا ذكر العميل اسم العلامة التجارية بوضوح أو أكد على علامة معينة - هذا صحيح
5. لا تقبل العلامات التجارية التي ذكرها المساعد فقط في قائمة الخيارات

هل استخراج "{extracted_brand}" صحيح ومبرر من رسائل العميل فقط؟

أجب بـ "صحيح" إذا كان العميل ذكر العلامة التجارية بوضوح، أو "خطأ" إذا لم يذكرها أو كان غامض."""

            print(f"🔍 [BRAND VERIFICATION] Sending prompt to LLM for verification")
            
            # Call LangChain for verification
            response = await self._call_langchain_llm(
                messages=[
                    {"role": "system", "content": "أنت خبير في فهم النصوص واستخراج أسماء العلامات التجارية. كن دقيقاً جداً في التحقق."},
                    {"role": "user", "content": verification_prompt}
                ],
                temperature=0.1,
                max_tokens=20
            )
            
            verification_result = response["content"].strip().lower()
            is_correct = "صحيح" in verification_result
            
            print(f"🔍 [BRAND VERIFICATION] Raw LLM response: '{response['content']}'")
            print(f"🔍 [BRAND VERIFICATION] Verification result for '{extracted_brand}': {verification_result} -> {'✅ APPROVED' if is_correct else '❌ REJECTED'}")
            
            if not is_correct:
                print(f"🚨 [BRAND VERIFICATION] Brand '{extracted_brand}' was REJECTED - user did not explicitly mention this brand")
            else:
                print(f"✅ [BRAND VERIFICATION] Brand '{extracted_brand}' was APPROVED - user explicitly mentioned this brand")
            
            return is_correct
            
        except Exception as e:
            print(f"🔍 [BRAND VERIFICATION] ERROR in verification: {str(e)}")
            logger.error(f"Error in brand extraction verification: {str(e)}")
            # On error, default to rejecting the extraction for safety
            print(f"🚨 [BRAND VERIFICATION] Defaulting to REJECT due to error for safety")
            return False

    async def _extract_brand_from_context(self, user_message: str, conversation_history: List[Dict] = None, city_name: str = None) -> Optional[Dict[str, Any]]:
        """Extract brand information from current message and conversation history with AI verification and improved matching
        IMPORTANT: Only returns brands if city_name is provided (city must be known first)
        IMPORTANT: Ignores size terms like ابو ربع, ابو نص, ابو ريال as they are NOT brand names
        IMPORTANT: Removes water prefixes like مياه, موية, مياة before brand names
        ENHANCED: Searches for identical brand after normalizing, then partial matching
        Priority: 1) Brand in current message (exact → partial), 2) Brand in conversation history (last 5 messages)
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
                
                # PRIORITY 1: Check current user message first - EXACT MATCH
                if user_message:
                    # Clean the user message by removing water prefixes
                    cleaned_message = self._clean_brand_name(user_message)
                    current_content = cleaned_message.lower()
                    
                    # First try exact matching after normalization
                    for brand in brands:
                        # Normalize brand title for better matching
                        brand_title_normalized = self._clean_brand_name(brand.get("title", "")).lower().strip()
                        
                        if brand_title_normalized and brand_title_normalized == current_content:
                            print(f"🎯 Brand exact match found:")
                            print(f"   Original brand: '{brand.get('title', '')}'")
                            print(f"   Normalized brand: '{brand_title_normalized}'")
                            print(f"   User message cleaned: '{current_content}'")
                            
                            # Verify extraction with ChatGPT
                            is_verified = await self._verify_brand_extraction(
                                user_message, conversation_history,
                                brand["title"], "الرسالة الحالية (مطابقة تامة)"
                            )
                            
                            if is_verified:
                                return {
                                    "brand_title": brand["title"],
                                    "found_in": "current_message"
                                }
                    
                    # If no exact match, try partial matching
                    for brand in brands:
                        # Normalize brand title for better matching
                        brand_title_normalized = self._clean_brand_name(brand.get("title", "")).lower()
                        
                        if brand_title_normalized and (brand_title_normalized in current_content or current_content in brand_title_normalized):
                            print(f"🔍 Brand partial match found:")
                            print(f"   Original brand: '{brand.get('title', '')}'")
                            print(f"   Normalized brand: '{brand_title_normalized}'")
                            print(f"   User message cleaned: '{current_content}'")
                            
                            # Verify extraction with ChatGPT
                            is_verified = await self._verify_brand_extraction(
                                user_message, conversation_history,
                                brand["title"], "الرسالة الحالية (مطابقة جزئية)"
                            )
                            
                            if is_verified:
                                return {
                                    "brand_title": brand["title"],
                                    "found_in": "current_message"
                                }
                
                # PRIORITY 2: Check conversation history if no brand in current message
                if conversation_history:
                    for message in reversed(conversation_history[-5:]):  # Check last 5 messages
                        content = message.get("content", "")
                        # Normalize conversation history content for better brand matching
                        normalized_content = self._clean_brand_name(content).lower()
                        
                        # First try exact matching with normalized content
                        for brand in brands:
                            # Normalize brand title for better matching
                            brand_title_normalized = self._clean_brand_name(brand.get("title", "")).lower().strip()
                            
                            if brand_title_normalized and brand_title_normalized in normalized_content:
                                print(f"🔍 Brand found in conversation history:")
                                print(f"   Original brand: '{brand.get('title', '')}'")
                                print(f"   Normalized brand: '{brand_title_normalized}'")
                                print(f"   History content normalized: '{normalized_content}'")
                                
                                # Verify extraction with ChatGPT
                                is_verified = await self._verify_brand_extraction(
                                    user_message, conversation_history,
                                    brand["title"], "تاريخ المحادثة"
                                )
                                
                                if is_verified:
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
    
    def get_all_cities(self, user_language: str = 'ar') -> Dict[str, Any]:
        """Get complete list of all cities we serve
        Returns language-specific city names with contextual message
        """
        try:
            db = self._get_db_session()
            try:
                cities = data_api.get_all_cities(db)
                
                # Filter cities to include only language-appropriate names
                filtered_cities = []
                for city in cities:
                    if user_language == 'ar':
                        # Arabic conversation - return Arabic city names
                        if city.get("name"):  # Only include cities with Arabic names
                            filtered_cities.append(city["name"])
                    else:
                        # English conversation - return English city names, fallback to Arabic
                        city_name = city.get("name_en", "") or city.get("name", "")
                        if city_name:  # Only include cities with names
                            filtered_cities.append(city_name)
                
                # Remove duplicates and sort
                filtered_cities = sorted(list(set(filtered_cities)))
                
                # Create response message
                if user_language == 'ar':
                    response_message = " هذه هي المدن التي نخدمها ونوصل لها : "
                else:
                    response_message = "These are the cities we serve:"
                
                return {
                    "success": True, 
                    "data": filtered_cities,  # Simple list of city names in appropriate language
                    "language": user_language,
                    "response_message": response_message,
                    "total_cities": len(filtered_cities)
                }
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error fetching cities: {str(e)}")
            return {"error": f"Failed to get cities: {str(e)}"}
    
    def get_brands_by_city_name(self, city_name: str, user_language: str = 'ar') -> Dict[str, Any]:
        """Get brands available in a specific city using city name with fuzzy matching
        Returns language-specific brand names and city information in response message
        """
        from utils.language_utils import language_handler
        
        try:
            # Use the conversation language instead of detecting from city name
            detected_language = user_language
            print(f"🌐 Using conversation language '{detected_language}' for city '{city_name}'")
            
            db = self._get_db_session()
            try:
                brands = data_api.get_brands_by_city_name(db, city_name)
                if not brands:
                    return {
                        "success": False,
                        "error": f"عذراً، لا نقدم خدمة التوصيل لمدينة {city_name} حالياً",
                        "original_input": city_name,
                        "show_app_links": False
                    }
                
                # Extract city information (same for all brands)
                city_ar = brands[0]["city_name"] if brands else city_name
                city_en = brands[0].get("city_name_en", "") if brands else ""
                
                # Filter brands to include only language-appropriate titles
                filtered_brands = []
                for brand in brands:
                    if detected_language == 'ar':
                        # Arabic request - return only Arabic brand names
                        if brand.get("title"):  # Only include brands with Arabic titles
                            filtered_brands.append(brand["title"])
                    else:
                        # English request - return only English brand names, fallback to Arabic
                        brand_name = brand.get("title_en", "") or brand.get("title", "")
                        if brand_name:  # Only include brands with names
                            filtered_brands.append(brand_name)
                
                # Remove duplicates and sort
                filtered_brands = sorted(list(set(filtered_brands)))
                
                # Create response message
                if detected_language == 'ar':
                    response_message = f"هذه هي العلامات التجارية المتاحة في {city_ar}:"
                    city_info = city_ar
                else:
                    city_display = city_en if city_en else city_ar
                    response_message = f"These are the brands available in {city_display}:"
                    city_info = city_display
                
                return {
                    "success": True, 
                    "data": filtered_brands,  # Simple list of brand names in detected language
                    "city_found": city_info,
                    "language": detected_language,
                    "response_message": response_message,
                    "total_brands": len(filtered_brands)
                }
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error fetching brands for city {city_name}: {str(e)}")
            return {"error": f"Failed to get brands: {str(e)}"}
    
    def get_products_by_brand_and_city_name(self, brand_name: str, city_name: str, user_language: str = 'ar') -> Dict[str, Any]:
        """Get products for a specific brand in a specific city using names with fuzzy matching
        Returns language-specific product strings with prices and contextual message
        """
        from utils.language_utils import language_handler
        
        try:
            # Use the conversation language instead of detecting from brand/city names
            detected_language = user_language
            print(f"🌐 Using conversation language '{detected_language}' for brand '{brand_name}' in city '{city_name}'")
            
            # Clean the brand name by removing water prefixes
            cleaned_brand_name = self._clean_brand_name(brand_name)
            
            db = self._get_db_session()
            try:
                # Try with cleaned brand name first
                products = data_api.get_products_by_brand_and_city_name(db, cleaned_brand_name, city_name)
                
                # If no results with cleaned name, try original name
                if not products:
                    products = data_api.get_products_by_brand_and_city_name(db, brand_name, city_name)
                if not products:
                    return {
                        "success": False,
                        "error": f"عذراً، العلامة التجارية {brand_name} غير متوفرة في مدينة {city_name} حالياً",
                        "original_brand": brand_name,
                        "original_city": city_name
                    }
                
                # Extract brand and city information
                brand_ar = products[0]["brand_title"] if products else brand_name
                brand_en = products[0].get("brand_title_en", "") if products else ""
                city_ar = products[0]["city_name"] if products else city_name
                city_en = products[0].get("city_name_en", "") if products else ""
                
                # Create simple product strings with prices
                filtered_products = []
                for product in products:
                    price = product["product_contract_price"]
                    title = product["product_title"]
                    
                    if detected_language == 'ar':
                        # Arabic format: "Product Title - XX.XX ريال"
                        product_string = f"{title} - {price} ريال"
                    else:
                        # English format: "Product Title - XX.XX SAR"
                        product_string = f"{title} - {price} SAR"
                    
                    filtered_products.append(product_string)
                
                # Create response message
                if detected_language == 'ar':
                    response_message = f"منتجات {brand_ar} المتاحة في {city_ar}:"
                    brand_found = brand_ar
                    city_found = city_ar
                else:
                    brand_display = brand_en if brand_en else brand_ar
                    city_display = city_en if city_en else city_ar
                    response_message = f"{brand_display} products available in {city_display}:"
                    brand_found = brand_display
                    city_found = city_display
                
                return {
                    "success": True, 
                    "data": filtered_products,  # Simple list of product strings with prices
                    "language": detected_language,
                    "response_message": response_message,
                    "brand_found": brand_found,
                    "city_found": city_found,
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
            # Clean the brand name by removing water prefixes
            cleaned_brand_name = self._clean_brand_name(brand_name)
            
            db = self._get_db_session()
            try:
                # Search with both cleaned and original brand names
                brands = data_api.search_brands_in_city(db, cleaned_brand_name, city_name)
                
                # If no results with cleaned name, try original name
                if not brands:
                    brands = data_api.search_brands_in_city(db, brand_name, city_name)
                
                if not brands:
                    return {
                        "success": False,
                        "error": f"عذراً، العلامة التجارية {brand_name} غير متوفرة في مدينة {city_name} حالياً",
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
                        "error": f"عذراً، لا نقدم خدمة التوصيل لمدينة {query} حالياً",
                        "query": query,
                        "show_app_links": False
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
    


    def get_cheapest_products_by_city_name(self, city_name: str) -> Dict[str, Any]:
        """Get cheapest products in each size for a specific city using city name with fuzzy matching"""
        try:
            db = self._get_db_session()
            try:
                result = data_api.get_cheapest_products_by_city_name(db, city_name)
                return result
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error fetching cheapest products for city {city_name}: {str(e)}")
            return {"error": f"Failed to get cheapest products: {str(e)}"}
    
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
            
            # Classification will be performed fresh each time for accuracy
            
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
            
            # Call LangChain for classification (will be traced in LangSmith)
            response = await self._call_langchain_llm(
                messages=[
                    {"role": "system", "content": classification_prompt},
                    {"role": "user", "content": f"{context}\nCurrent message: {user_message}"}
                ],
                temperature=0.1,  # Low temperature for consistent classification
                max_tokens=10  # Short response expected
            )
            
            classification_result = response["content"].strip().lower()
            
            # Log the classification
            logger.info(f"Message classification for '{user_message[:50]}...': {classification_result}")
            
            # Determine relevance
            # Fix: Check for exact match to avoid "not_relevant" being treated as relevant
            is_relevant = classification_result == "relevant"
            
            # Return True if relevant, False if not relevant
            return is_relevant
            
        except Exception as e:
            logger.error(f"Error classifying message relevance: {str(e)}")
            # On error, default to relevant to avoid blocking legitimate queries
            return True
    
    async def _validate_response_appropriateness(self, user_message: str, generated_response: str, conversation_history: List[Dict] = None, user_language: str = 'ar') -> Dict[str, Any]:
        """
        Validate if the generated response is appropriate for the user's message.
        
        Args:
            user_message: The original user message
            generated_response: The response generated by the system
            conversation_history: Previous conversation context
            user_language: Language of the conversation
            
        Returns:
            Dict with 'is_appropriate' (bool), 'reason' (str), and 'confidence' (float)
        """
        try:
            # Build conversation context
            conversation_context = ""
            if conversation_history:
                recent_history = conversation_history[-3:]  # Last 3 messages for context
                for i, msg in enumerate(recent_history):
                    role = msg.get('role', 'unknown')
                    content = msg.get('content', '')
                    conversation_context += f"{i+1}. {role}: {content}\n"
            
            if user_language == 'ar':
                validation_prompt = f"""أنت مقيم صارم جداً لجودة الردود في خدمة العملاء لشركة أبار لتوصيل المياه.

مهمتك: تحديد ما إذا كان الرد المُولد مناسب ومتعلق برسالة العميل أم لا.

رسالة العميل: "{user_message}"
الرد المُولد: "{generated_response}"

السياق السابق للمحادثة (آخر 3 رسائل):
{conversation_context}

📋 نطاق عمل وكيل الاستعلامات - مهم جداً لفهم الردود المناسبة:

🎯 ما يستطيع وكيل الاستعلامات فعله:
1. ✅ عرض المدن المتاحة للتوصيل
2. ✅ عرض العلامات التجارية المتاحة في كل مدينة
3. ✅ عرض منتجات المياه وأسعارها لكل علامة تجارية
4. ✅ البحث عن علامات تجارية في مدن محددة
5. ✅ عرض أرخص المنتجات في مدينة معينة
6. ✅ الإجابة على أسئلة المنتجات والأسعار والتوفر
7. ✅ طرح أسئلة ودودة لجمع معلومات (مدينة، علامة، منتج)
8. ✅ توجيه العميل للتطبيق/الموقع للطلب
9. ✅ التعامل مع الاستفسارات العامة عن المياه وأنواعها

❌ ما لا يستطيع وكيل الاستعلامات فعله:
1. ❌ أخذ طلبات فعلية أو معالجة الدفع
2. ❌ تحديد مواعيد التوصيل أو التوصيل الفعلي
3. ❌ التعامل مع مشاكل المندوبين أو التوصيل
4. ❌ تعديل الطلبات الموجودة أو إلغاؤها
5. ❌ التعامل مع الشكاوي أو مشاكل الخدمة
6. ❌ تقديم معلومات التواصل أو العناوين
7. ❌ التعامل مع طلبات تغيير المواقع أو العناوين

🔧 وظائف النظام المتاحة لوكيل الاستعلامات:
- get_all_cities(): عرض جميع المدن
- get_brands_by_city_name(): عرض العلامات في مدينة
- get_products_by_brand_and_city_name(): عرض منتجات علامة في مدينة
- search_brands_in_city(): البحث عن علامات تجارية
- get_cheapest_products_by_city_name(): أرخص المنتجات في مدينة

🚨 فهم منطق العمل الحاسم:
- النظام يتطلب معلومات المدينة والعلامة التجارية معاً لعرض المنتجات والأسعار
- إذا ذكر العميل العلامة التجارية لكن لم يذكر المدينة → السؤال عن المدينة ضروري ومناسب ✅
- إذا سأل العميل عن الأسعار لكن لم يحدد العلامة/المدينة → السؤال عن الاثنين ضروري ومناسب ✅
- إذا أراد العميل معلومات عامة لكن لم يحدد المدينة → السؤال عن المدينة ضروري ومناسب ✅
- هذه الأسئلة ليست عامة - هي ضرورية لتقديم خدمة دقيقة

🔄 فهم تدفق المحادثات لتوصيل المياه - مهم جداً:
راجع الرسائل الثلاث الأخيرة لفهم السياق:

1️⃣ عندما يحتاج العميل توصيل مياه أو يسأل عن الأسعار/العلامات:
   - إذا لم نعرف المدينة → السؤال "أي مدينة تريد؟" مناسب ✅
   - إذا عرفنا المدينة → عرض العلامات المتاحة في المدينة مناسب ✅
   
2️⃣ إذا عرفنا المدينة والعميل يريد علامة معينة أو يسأل عن الأسعار:
   - عرض المنتجات المتاحة للعلامة المحددة مناسب ✅
   - أو السؤال "أي ماركة تحتاج؟" إذا لم يحدد العميل
   
3️⃣ عندما يذكر العميل علامة تجارية معينة:
   - إذا لم نعرف المدينة → السؤال "أي مدينة أنت فيها؟" مناسب ✅
   - هذا يتبع التدفق المنطقي: علامة تجارية مذكورة → نحتاج المدينة → نعرض المنتجات
   - مثال: العميل يسأل عن "مياه راين" → السؤال عن المدينة صحيح ✅
   
4️⃣ خدمة العملاء المفيدة:
   - عرض الخيارات المتاحة أفضل من مجرد السؤال
   - مثال: إذا عرفنا المدينة → اعرض العلامات المتاحة
   - مثال: إذا عرفنا العلامة → اعرض المنتجات والأسعار

قواعد التقييم الصارمة:

🔴 الرد غير مناسب إذا:
- يجيب على سؤال مختلف تماماً عن سؤال العميل
- يخلط بين طلبات التواصل وأسئلة الفروع 
- يخلط بين أسئلة التوصيل العامة وأسئلة التوصيل للباب
- يقدم معلومات غير متعلقة بسؤال العميل
- يحتوي على روابط مكررة في نفس الرسالة
- عام جداً ولا يجيب على السؤال المحدد
- يسأل أسئلة غير مفيدة لا تساعد في تحقيق طلب العميل
- يتجاهل المعلومات التي قدمها العميل بالفعل

⚠️ تنبيه: لا ترفض الردود التي تجيب بصدق على توفر المنتجات!
⚠️ حاسم: لا ترفض الردود التي تسأل عن المعلومات الضرورية (المدينة/العلامة) المطلوبة لتقديم خدمة دقيقة!
🔧 منطق الخدمة: النظام يجب أن يسأل عن المدينة/العلامة التجارية عند الحاجة لعرض المنتجات والأسعار - هذا سلوك مناسب!

🟢 الرد مناسب إذا:
- يجيب بدقة على سؤال العميل المحدد
- يستخدم المعلومات الصحيحة حسب نوع السؤال
- يتماشى مع سياق المحادثة
- يقدم معلومات متعلقة بخدمات المياه عند الحاجة
- يتبع التدفق المنطقي: مدينة → علامات متاحة أو منتجات أو علامة مذكورة → يسأل عن المدينة → يعرض المنتجات
- يعرض الخيارات المتاحة بدلاً من مجرد السؤال عنها
- يقدم معلومات مفيدة حسب ما نعرفه من السياق
- يجيب بصدق عن توفر أو عدم توفر منتج معين (مقبول حتى لو لم يقدم بدائل)
- يسأل عن المعلومات الناقصة الضرورية لتحقيق طلب العميل:
  • يسأل عن المدينة عندما يذكر العميل علامة تجارية لكن المدينة غير معروفة ✅
  • يسأل عن العلامة التجارية عندما يسأل العميل عن المنتجات/الأسعار لكن العلامة غير معروفة ✅
  • يسأل أسئلة متابعة مفيدة لتقديم خدمة أفضل ✅

أمثلة على أخطاء شائعة:
- العميل يسأل عن رقم التواصل → الرد يتكلم عن الفروع ❌
- العميل يسأل عن التوصيل عامة → الرد عن التوصيل للباب فقط ❌ 
- العميل يسأل عن ماركة معينة → رد عام عن جميع الماركات ❌

أمثلة على ردود صحيحة ومقبولة:
- العميل يسأل عن "مياه المنهل" → "للأسف، مياه المنهل غير متوفرة حالياً" ✅ (مقبول)
- العميل يسأل عن علامة معينة → "هذه العلامة غير متاحة في الرياض" ✅ (مقبول)
- العميل يذكر "مياه راين" → "أي مدينة أنت فيها؟ راح أعرض لك منتجات راين هناك!" ✅ (مناسب)
- العميل يسأل "أي علامات عندكم؟" → "أي مدينة أنت فيها؟ راح أعرض لك العلامات المتاحة هناك!" ✅ (مناسب)
- العميل يسأل "كم سعر المياه؟" → "أي علامة ومدينة تريد؟ راح أعرض لك الأسعار!" ✅ (مناسب)  
- العميل يقول "أبي توصيل مياه" → "أي مدينة وأي علامة تريد؟" ✅ (مناسب)
- العميل يسأل عن علامة معينة بشكل عام → السؤال عن المدينة لعرض منتجات هذه العلامة ✅ (مناسب)
- إخبار العميل بالحقيقة عن التوفر أفضل من معلومات خاطئة ✅

🚨 قاعدة مهمة: السؤال عن معلومات العلامة التجارية أو المدينة دائماً مناسب عندما تكون هذه المعلومات مطلوبة لتقديم خدمة دقيقة ✅

قيّم الرد وأخرج:
- is_appropriate: true أو false
- reason: سبب واضح ومحدد للقرار
- confidence: درجة ثقة من 0.0 إلى 1.0

أخرج الناتج بصيغة JSON فقط:
{{"is_appropriate": true/false, "reason": "السبب المفصل", "confidence": 0.0-1.0}}"""

            else:
                validation_prompt = f"""You are a strict quality evaluator for Abar Water Delivery Company customer service responses.

Your task: Determine if the generated response is appropriate and relevant to the customer's message.

Customer Message: "{user_message}"
Generated Response: "{generated_response}"

Previous Conversation Context (Last 3 messages):
{conversation_context}

📋 Query Agent Scope - Critical for Understanding Appropriate Responses:

🎯 What the Query Agent CAN do:
1. ✅ Show available cities for delivery
2. ✅ Show available water brands in each city
3. ✅ Show water products and prices for each brand
4. ✅ Search for brands in specific cities
5. ✅ Show cheapest products in a specific city
6. ✅ Answer questions about products, prices, and availability
7. ✅ Ask friendly questions to gather information (city, brand, product)
8. ✅ Direct customers to app/website for ordering
9. ✅ Handle general inquiries about water and water types

❌ What the Query Agent CANNOT do:
1. ❌ Take actual orders or process payments
2. ❌ Schedule deliveries or handle actual delivery
3. ❌ Handle delivery driver or delivery problems
4. ❌ Modify or cancel existing orders
5. ❌ Handle complaints or service issues
6. ❌ Provide contact information or addresses
7. ❌ Handle requests to change locations or addresses

🔧 Available System Functions for Query Agent:
- get_all_cities(): Show all cities
- get_brands_by_city_name(): Show brands in city
- get_products_by_brand_and_city_name(): Show brand products in city
- search_brands_in_city(): Search for brands
- get_cheapest_products_by_city_name(): Cheapest products in city

🔄 Understanding Water Delivery Conversation Flow - Very Important:
Review the last 3 messages to understand context:

1️⃣ When customer needs water delivery or asks about prices/brands:
   - If we don't know the city → Asking "Which city are you in?" is appropriate ✅
   - If we know the city → Showing available brands in that city is appropriate ✅
   
2️⃣ If we know the city and customer wants specific brand or asks prices:
   - Showing available products for the specified brand is appropriate ✅
   - Or asking "Which brand do you need?" if customer hasn't specified
   
3️⃣ Helpful Customer Service:
   - Showing available options is better than just asking questions
   - Example: If we know city → show available brands
   - Example: If we know brand → show products and prices

Strict Evaluation Rules:

🔴 Response is INAPPROPRIATE if:
- Answers a completely different question than what customer asked
- Confuses contact requests with branches questions
- Confuses general delivery questions with door delivery questions  
- Provides information unrelated to customer's question
- Contains duplicate links in the same message
- Too generic and doesn't address the specific question
- Asks about brand without knowing the city first

⚠️ Warning: Don't reject responses that honestly answer about product availability!
🟢 Response is APPROPRIATE if:
- Accurately answers the customer's specific question
- Uses correct information based on question type
- Aligns with conversation context
- Provides relevant water service information when needed
- Follows logical flow: city → available brands or products
- Shows available options instead of just asking about them
- Provides helpful information based on what we know from context
- Honestly answers about availability or non-availability of specific products (acceptable even without alternatives)

Common Error Examples:
- Customer asks about contact number → Response talks about branches ❌
- Customer asks about general delivery → Response only about door delivery ❌
- Customer asks about specific brand → Generic response about all brands ❌

Examples of Correct and Acceptable Responses:
- Customer asks about "Al Manhal water" → "Sorry, Al Manhal water is currently not available" ✅ (Acceptable)
- Customer asks about specific brand → "This brand is not available in Riyadh" ✅ (Acceptable)
- Telling customer the truth about availability is better than wrong information ✅

Evaluate the response and output:
- is_appropriate: true or false
- reason: Clear, specific reason for decision
- confidence: Confidence score from 0.0 to 1.0

Output in JSON format only:
{{"is_appropriate": true/false, "reason": "detailed reason", "confidence": 0.0-1.0}}"""

            # Call language handler for evaluation
            evaluation_result = await language_handler.process_with_openai(
                validation_prompt,
                "أنت خبير تقييم جودة خدمة العملاء. قم بالتقييم بدقة وصرامة." if user_language == 'ar' else "You are a customer service quality evaluation expert. Evaluate strictly and accurately."
            )
            
            if not evaluation_result:
                print("❌ Response validation failed - no result from language handler")
                return {"is_appropriate": True, "reason": "Validation failed - defaulting to appropriate", "confidence": 0.5}
            
            # Try to parse JSON result
            try:
                import json
                result = json.loads(evaluation_result.strip())
                
                # Ensure required keys exist
                if not all(key in result for key in ['is_appropriate', 'reason', 'confidence']):
                    raise ValueError("Missing required keys in validation result")
                
                print(f"🔍 Response validation result: {result['is_appropriate']} (confidence: {result['confidence']}) - {result['reason']}")
                print(f"📝 Generated response being validated: '{generated_response}'")
                return result
                
            except (json.JSONDecodeError, ValueError) as e:
                print(f"❌ Failed to parse validation result: {str(e)}. Raw result: {evaluation_result}")
                # Default to appropriate if parsing fails
                return {"is_appropriate": True, "reason": "JSON parsing failed - defaulting to appropriate", "confidence": 0.5}
                
        except Exception as e:
            print(f"❌ Error in response validation: {str(e)}")
            # Default to appropriate on error to avoid blocking responses
            return {"is_appropriate": True, "reason": f"Validation error: {str(e)}", "confidence": 0.5}

    async def process_query(self, user_message: str, conversation_history: List[Dict] = None, user_language: str = 'ar', journey_id: str = None) -> str:
        """
        Process user query using OpenAI with function calling capabilities with response validation and retry logic
        Enhanced with 2-attempt response validation to ensure appropriate responses
        """
        print(f"Processing query: {user_message} (Language: {user_language})")
        
        # Maximum number of attempts
        max_attempts = 1
        
        for attempt in range(1, max_attempts + 1):
            print(f"🔄 Response generation attempt {attempt}/{max_attempts}")
            
            try:
                # Generate response using internal method
                response = await self._generate_response_internal(user_message, conversation_history, user_language, journey_id)
                
                # If empty response, skip validation and try again
                if not response or response.strip() == "":
                    print(f"⚠️ Attempt {attempt} generated empty response")
                    if attempt < max_attempts:
                        continue
                    else:
                        # Return empty string when all attempts fail instead of error message
                        # This ensures no response is sent to customer and human agent can handle
                        return ""
                
                # Validate response appropriateness
                print(f"🔍 Validating response appropriateness for attempt {attempt}")
                validation_result = await self._validate_response_appropriateness(
                    user_message=user_message,
                    generated_response=response,
                    conversation_history=conversation_history,
                    user_language=user_language
                )
                
                if validation_result['is_appropriate']:
                    print(f"✅ Response validated as appropriate (attempt {attempt})")
                    return response
                else:
                    print(f"❌ Response deemed inappropriate (attempt {attempt}): {validation_result['reason']}")
                    if attempt < max_attempts:
                        print(f"🔄 Retrying response generation...")
                        continue
                    else:
                        print(f"⚠️ Max attempts reached and validation failed, not sending response")
                        return ""
                        
            except Exception as e:
                print(f"❌ Error in attempt {attempt}: {str(e)}")
                if attempt < max_attempts:
                    continue
                else:
                    error_msg = "عذراً، حدث خطأ في معالجة الاستعلام. الرجاء المحاولة مرة أخرى." if user_language == 'ar' else "Sorry, there was an error processing the query. Please try again."
                    return error_msg

    async def _generate_response_internal(self, user_message: str, conversation_history: List[Dict] = None, user_language: str = 'ar', journey_id: str = None) -> str:
        """
        Internal method for generating response (separated for retry logic)
        """
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
            city_context = await self._extract_city_from_context(user_message, conversation_history)
            
            # Check if we have brand information
            brand_context = await self._extract_brand_from_context(
                user_message, 
                conversation_history, 
                city_context.get("city_name") if city_context else None  # ← Uses CITY name for brand search
            )
            
            # Prepare conversation history
            messages = []
            
            # System message with instructions based on user language
            city_info = ""
            brand_info = ""
            
            if city_context:
                if 'district' in city_context.get('found_in', ''):
                    found_where = "current message district" if 'current_message_district' in city_context['found_in'] else "conversation history district"
                    district_name = city_context.get('district_name', 'unknown district')
                    city_info = f"\n\nIMPORTANT CONTEXT: The customer mentioned {district_name} district which maps to {city_context['city_name_en']} ({city_context['city_name']}) - detected from {found_where}. Use the CITY name ({city_context['city_name']}) for all brand/product searches, but you can acknowledge their district for context. 🚨 MANDATORY: Since you know the city, immediately call get_brands_by_city_name('{city_context['city_name']}') to show available brands."
                else:
                    found_where = "current message" if city_context['found_in'] == "current_message" else "conversation history"
                    city_info = f"\n\nIMPORTANT CONTEXT: The customer is from {city_context['city_name_en']} ({city_context['city_name']}) - detected from {found_where}. You already know their city, so you can show products and brands for this city without asking again. 🚨 MANDATORY: Since you know the city, immediately call get_brands_by_city_name('{city_context['city_name']}') to show available brands."
            
            if brand_context:
                found_where = "current message" if brand_context['found_in'] == "current_message" else "conversation history"
                if city_context:
                    brand_info = f"\n\nBRAND CONTEXT: The customer mentioned '{brand_context['brand_title']}' - detected from {found_where}. 🚨 MANDATORY: Since you know both city ({city_context['city_name']}) and brand ({brand_context['brand_title']}), immediately call get_products_by_brand_and_city_name('{brand_context['brand_title']}', '{city_context['city_name']}') to show products."
                else:
                    brand_info = f"\n\nBRAND CONTEXT: The customer mentioned '{brand_context['brand_title']}' - detected from {found_where}. You know the brand but need to ask for the city first, then show products."
            
            if user_language == 'en':
                system_message = {
                    "role": "system",
                    "content": f"""You are a friendly customer service employee at Abar Water Delivery Company in Saudi Arabia.{city_info}{brand_info}

                    📋 Important terminology for understanding Arabic customers (for understanding only - don't mention to customers):
                    - "قوارير المياه" = "الجوالين" (same product - water gallons)
                    - "حبة مياه" = "زجاجة مياه" (common term - means water bottle)
                    - "مقاس" = size/volume (e.g., "مقاس 200 مل" means 200ml size)
                    - Example: "احتاج كرتونة 48 حبة مقاس 200 مل" = "I need a carton of 48 bottles, 200ml size"

                    Your job is to help customers with:
                    1. Finding available cities for water delivery service
                    2. Showing water brands available in each city
                    3. Displaying water products and their prices from each brand
                    4. Answering questions naturally and helpfully
                    5. Asking friendly questions when you need more information

                    🏙️ Smart City Name Extraction - Very Important:
                    - When you suspect a word in the current message or conversation history might be a city name
                    - ALWAYS use the get_all_cities() function to get the complete list of cities we serve
                    - Compare the suspected word with the available cities list
                    - Get the correct and complete city name from the list
                    - Use the correct name with other functions like get_brands_by_city_name and get_products_by_brand_and_city_name
                    - 🚨 CRITICAL: Never tell a customer we don't serve their city without first calling get_all_cities() to verify
                    
                    

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
                    - Search through the last 5 messages for any mention of city names or brand names
                    - Do not ask for information that already exists in conversation history
                    - Use extracted information from history even if it's from older messages

                    🚨 MANDATORY FUNCTION CALLING - CRITICAL:
                    - When you know the city but need to show brands: IMMEDIATELY call get_brands_by_city_name function
                    - When you know both city and brand but need products: IMMEDIATELY call get_products_by_brand_and_city_name function
                    - NEVER say "let me check" or "one moment" without actually calling the function
                    - If system provides city context, use the function calls immediately in the same response
                    - Do NOT provide generic responses - always use functions to get real data

                    🚨 DISTRICT-TO-CITY MAPPING SYSTEM - CRITICAL:
                    - The system automatically detects DISTRICT NAMES (neighborhoods) in user messages
                    - Districts are automatically mapped to their corresponding CITIES for all business operations
                    - When customer mentions districts like "حي الحمراء الأول", "منطقة المعلمين", "الحي الشمالي" etc.:
                    → System maps them to corresponding cities (e.g., "الحمراء الأول" → "الأحساء")
                    → ALL business operations (brands/products search) use the CITY name, NOT district name
                    → District names are kept for context and customer communication only
                    - 🚨 CRITICAL: If system context shows district mapping, NEVER ask for city - you already have it!
                    - When you see context like "Customer mentioned [district] district which maps to [city]":
                    → IMMEDIATELY proceed with the mapped city for all operations
                    → DO NOT ask "Which city are you in?" - you already know the city from district mapping
                    → Acknowledge the district but use the city: "I'll show you brands/products available in [city] for [district] district"
                    - You can acknowledge the district for customer context: "I found your request for الحمراء الأول district"
                    - NEVER search for brands/products using district names directly
                    - MIXED QUERIES: If customer mentions BOTH city and district (e.g., "جدة حي الحمراء الأول"), direct city name takes priority over district mapping

                    CITY DETECTION PRIORITY - WITH STRONG FOCUS ON HISTORY:
                    1. Check if city is mentioned in current user message (direct city names have priority)
                    2. Check if district is mentioned (system will map to city automatically - NEVER ask for city if district found!)
                    3. 🚨 Search thoroughly through conversation history (last 5 messages) for any city mentions
                    4. Search thoroughly through conversation history for any district mentions
                    5. Only if NO city/district found in current message OR history - ask for city

                    🚨 CRITICAL RULE: If system provides district-to-city mapping in context, you already have the city!
                    - NEVER ask "Which city are you in?" when district mapping context is provided
                    - District mapping = automatic city knowledge = proceed immediately with business logic
                    - Use this phrase to ask about city: "Which city are you in? I need to know your location." - ONLY when NO district/city found anywhere

                    BRAND DETECTION PRIORITY - WITH STRONG FOCUS ON HISTORY:
                    1. Check if brand is mentioned in current user message
                    2. 🚨 Search thoroughly through conversation history (last 5 messages) for any brand mentions
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

                    🚨 HANDLING WATER WORDS BEFORE BRAND NAMES - CRITICAL:
                    - Customers may mention words like "مياه" (water), "موية" (water), "مياة" (water), "water" before brand names
                    - Examples: "مياه وي" (We water) - "موية نقي" (Naqi water) - "water Nestle" - "مياه نستله"
                    - These water words are NOT part of the actual brand name
                    - The system automatically removes these prefixes when searching
                    - So "مياه وي" becomes just "وي" for database search
                    - Consider these words as descriptors, not part of the brand name

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

                    🚨 APP PROMOTION - ONLY IN SPECIFIC CASES:
                    - When showing specific products/prices for a brand, add at the end: "You can order through our app: https://onelink.to/abar_app"
                    - Don't repeat links if they already exist in the response
                    - If city is not available, just use the predefined simple response

                    🚨 CITY NOT AVAILABLE - CRITICAL INSTRUCTIONS:
                    - BEFORE saying we don't deliver to any city, you MUST first call get_all_cities() function
                    - Compare the user's city name with ALL cities we serve to ensure it's not a spelling mistake
                    - Only AFTER confirming the city is truly not in our service list, then use this exact response: "عذراً، لا نقدم خدمة التوصيل لهذه المدينة حالياً"
                    - This protects us from incorrectly rejecting customers due to spelling variations or typos
                    - DO NOT add explanations or additional text beyond this message
                    - Be direct and clear about unavailability only after verification

                    🚨 CRITICAL RULE - BE DIRECT ABOUT SERVICE AVAILABILITY:
                    - When a city is not serviced, clearly state: "عذراً، لا نقدم خدمة التوصيل لهذه المدينة حالياً"
                    - When a brand is not available in a city, clearly state: "عذراً، هذه العلامة التجارية غير متوفرة في هذه المدينة حالياً"
                    - Be direct and honest with customers about availability
                    - This applies to cities and brand availability questions

                    🚨 SPECIFIC BUSINESS RULES - CRITICAL:

                    1. APARTMENT DOOR DELIVERY:
                    - ONLY when customer uses specific phrases like "apartment door", "flat door", "door delivery", "deliver to my door", or mentions specific floors ("1st floor", "2nd floor", "3rd floor"), answer: "We deliver to apartment doors if there is an elevator, and if there is no elevator we deliver to the 1st, 2nd, and 3rd floors maximum with a request to add a note with your order through the app."
                    - Do NOT use this response for general delivery questions

                    2. JUG EXCHANGE SERVICE:
                    - Jug exchange is ONLY available in specified cities, not outside them
                    - Jug exchange is NOT available for Al-Manhal brand yet
                    - Always mention these limitations when discussing jug exchange

                    3. BRANCHES QUESTION:
                    - ONLY when customer specifically mentions "branches", "physical stores", "offices", "locations", "do you have branches", answer: "We don't have physical branches, but we deliver to many cities."
                    - Do NOT use this response for contact information, phone number requests, or other questions

                    4. CONTACT INFORMATION REQUESTS:
                    - ONLY when customer specifically asks about "phone number", "contact number", "how to contact", "get in touch", "call you", "reach you", answer: "You can contact us through our app or website for technical support and customer service: https://onelink.to/abar_app or https://abar.app/en/store/"
                    - Do NOT confuse contact requests with branches questions

                    5. PRICE DISPUTES:
                    - If customer asks about product price and claims it's available at a lower price elsewhere, DO NOT agree or confirm lower prices
                    - ONLY provide prices from our official data - never generate or estimate prices
                    - Always use the get_products_by_brand function for accurate pricing information

                    Important rules:
                    - Always use available functions to get updated information
                    - For city queries: use search_cities to handle typos and fuzzy matching, and get_all_cities to verify availability
                    - Before declaring a city unserviced, ALWAYS verify with get_all_cities first
                    - Be patient with typos and spelling variations
                    - Respond in English since the customer is communicating in English
                    - Keep responses helpful and conversational like a real person would
                    - Use context smartly - don't ask for information you already have
                    - Don't repeat links in the same message - each link should appear only once

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
                    if 'district' in city_context.get('found_in', ''):
                        found_where_ar = "الرسالة الحالية (حي)" if 'current_message_district' in city_context['found_in'] else "تاريخ المحادثة (حي)"
                        district_name = city_context.get('district_name', 'حي غير معروف')
                        city_info_ar = f"\n\nسياق مهم: العميل ذكر حي {district_name} والذي يربط بمدينة {city_context['city_name']} ({city_context['city_name_en']}) - تم اكتشافه من {found_where_ar}. استخدم اسم المدينة ({city_context['city_name']}) لجميع عمليات البحث عن العلامات التجارية/المنتجات، ولكن يمكنك الاعتراف بحيهم للسياق. 🚨 إجباري: بما أنك تعرف المدينة، استدعي فوراً get_brands_by_city_name('{city_context['city_name']}') لعرض العلامات التجارية المتاحة."
                    else:
                        found_where_ar = "الرسالة الحالية" if city_context['found_in'] == "current_message" else "تاريخ المحادثة"
                        city_info_ar = f"\n\nسياق مهم: العميل من {city_context['city_name']} ({city_context['city_name_en']}) - تم اكتشافها من {found_where_ar}. أنت تعرف مدينتهم بالفعل، لذا يمكنك عرض المنتجات والعلامات التجارية لهذه المدينة بدون السؤال مرة أخرى. 🚨 إجباري: بما أنك تعرف المدينة، استدعي فوراً get_brands_by_city_name('{city_context['city_name']}') لعرض العلامات التجارية المتاحة."
                
                if brand_context:
                    found_where_ar = "الرسالة الحالية" if brand_context['found_in'] == "current_message" else "تاريخ المحادثة"
                    if city_context:
                        brand_info_ar = f"\n\nسياق العلامة التجارية: العميل ذكر '{brand_context['brand_title']}' - تم اكتشافها من {found_where_ar}. 🚨 إجباري: بما أنك تعرف المدينة ({city_context['city_name']}) والعلامة التجارية ({brand_context['brand_title']})، استدعي فوراً get_products_by_brand_and_city_name('{brand_context['brand_title']}', '{city_context['city_name']}') لعرض المنتجات."
                    else:
                        brand_info_ar = f"\n\nسياق العلامة التجارية: العميل ذكر '{brand_context['brand_title']}' - تم اكتشافها من {found_where_ar}. أنت تعرف العلامة التجارية لكن تحتاج لسؤال عن المدينة أولاً، ثم عرض المنتجات."
                
                system_message = {
                    "role": "system",
                    "content": f"""أنت موظف خدمة عملاء ودود في شركة أبار لتوصيل المياه في السعودية.{city_info_ar}{brand_info_ar}

                    📋 معلومات مهمة لفهم المصطلحات (للفهم فقط - لا تذكرها للعميل):
                    - قوارير المياه = الجوالين (نفس المنتج)
                    - "حبة مياه" = "زجاجة مياه" (مصطلح شائع)
                    - "مقاس" = الحجم/السعة (مثل: "مقاس 200 مل" تعني حجم 200 مل)
                    - مثال: "احتاج كرتونة 48 حبة مقاس 200 مل" = "احتاج كرتونة 48 زجاجة حجم 200 مل"

                    وظيفتك مساعدة العملاء في:
                    1. إيجاد المدن المتاحة لخدمة توصيل المياه
                    2. عرض العلامات التجارية للمياه المتاحة في كل مدينة  
                    3. عرض منتجات المياه وأسعارها من كل علامة تجارية
                    4. الإجابة على الأسئلة بطريقة طبيعية ومفيدة
                    5. طرح أسئلة ودودة عندما تحتاج معلومات أكثر

                    🏙️ استخراج أسماء المدن الذكي - مهم جداً:
                    - عندما تشك أن كلمة في الرسالة الحالية أو تاريخ المحادثة قد تكون اسم مدينة
                    - استخدم دائماً الوظيفة get_all_cities() لتحصل على القائمة الكاملة للمدن التي نخدمها
                    - قارن الكلمة المشبوهة مع قائمة المدن المتاحة
                    - احصل على الاسم الصحيح والكامل للمدينة من القائمة
                    - استخدم الاسم الصحيح مع الوظائف الأخرى مثل get_brands_by_city_name and  get_products_by_brand_and_city_name
                    - 🚨 مهم جداً: لا تخبر العميل أبداً أننا لا نخدم مدينته بدون استدعاء get_all_cities() للتحقق أولاً
                    
                    🚨 تطبيع أسماء المدن المهم جداً:
                    - مدينة جيزان هي نفسها مدينة جازان (نفس المدينة لكن كتابة مختلفة)
                    - المستخدمون قد يكتبون "جيزان" لكن قاعدة البيانات تحفظها كـ "جازان"
                    - استخدم دائماً "جازان" عند البحث في قاعدة البيانات مهما كان طريقة كتابة المستخدم
                    - إذا ذكر المستخدم "جيزان"، طبعها لـ "جازان" لجميع عمليات قاعدة البيانات
                    
                    📍 أسماء المدن المختصرة - انتبه لهذا بشكل قوي جداً:
                    - المستخدمون أحياناً يقولون "المدينة" أو "المدينه" بدلاً من "المدينة المنورة"
                    - المستخدمون أحياناً يقولون "مكة" أو "مكه" بدلاً من "مكة المكرمة"
                    - المستخدمون أحياناً يقولون "الخميس" بدلاً من "خميس مشيط"
                    - 🚨 مهم جداً: عندما تسمع "المدينة" في الرسالة الحالية أو تاريخ المحادثة، تعامل معها فوراً كأنها "المدينة المنورة"
                    - 🚨 مهم جداً: عندما تسمع "الخميس" في الرسالة الحالية أو تاريخ المحادثة، تعامل معها فوراً كأنها "خميس مشيط"
                    - 🚨 خاصة عندما يقول العميل "الموقع المدينة" أو "في المدينة" - هذا يعني المدينة المنورة بلا شك
                    - 🚨 خاصة عندما يقول العميل "توصيل الخميس" أو "في الخميس" أو "متوفر في الخميس" - هذا يعني خميس مشيط بلا شك
                    - جميع هذه المدن يتم التوصيل لها
                    - لا تسأل عن المدينة إذا ذكر العميل "المدينة" أو "الخميس" في أي صيغة
                   

                    أسلوب التواصل:
                    - تكلم مثل موظف خدمة عملاء حقيقي
                    - كن طبيعي وودود ومحادثي
                    - لا تستخدم أبداً عبارات مثل "رد الذكاء الاصطناعي" أو "رد المساعد" أو "أنا ذكاء اصطناعي"
                    - رد كأنك شخص حقيقي يعمل في الشركة

                    🚨 الانتباه الفائق لتاريخ المحادثة - مهم جداً:
                    - راجع دائماً تاريخ المحادثة بعناية للعثور على المدن والعلامات التجارية المذكورة سابقاً
                    - ابحث في آخر 5 رسائل للعميل والمساعد عن أي ذكر لأسماء المدن أو العلامات التجارية
                    - 🚨 انتبه بشكل خاص لهذه العبارات في الرسالة الحالية: "الموقع المدينة"، "في المدينة"، "أنا في المدينة" = تعني المدينة المنورة
                    - 🚨 انتبه بشكل خاص لهذه العبارات في الرسالة الحالية: "توصيل الخميس"، "في الخميس"، "أنا في الخميس"، "متوفر في الخميس" = تعني خميس مشيط
                    - لا تسأل عن معلومات موجودة بالفعل في تاريخ المحادثة أو في الرسالة الحالية
                    - استخدم المعلومات المستخرجة من التاريخ حتى لو كانت من رسائل قديمة

                    🚨 استدعاء الوظائف الإجباري - مهم جداً:
                    - عندما تعرف المدينة لكن تحتاج لعرض العلامات التجارية: استدعي فوراً وظيفة get_brands_by_city_name
                    - عندما تعرف المدينة والعلامة التجارية لكن تحتاج للمنتجات: استدعي فوراً وظيفة get_products_by_brand_and_city_name
                    - لا تقل أبداً "دعني أتحقق" أو "لحظة واحدة" بدون استدعاء الوظيفة فعلاً
                    - إذا وفر النظام سياق المدينة، استخدم استدعاءات الوظائف فوراً في نفس الرد
                    - لا تقدم ردود عامة - استخدم دائماً الوظائف للحصول على بيانات حقيقية

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
                    1. تحقق إذا كانت المدينة مذكورة في رسالة العميل الحالية (أسماء المدن المباشرة لها أولوية)
                    2. 🚨 انتبه لمؤشرات الموقع مع أسماء المدن: "الموقع المدينة"، "في المدينة"، "موقعي المدينة" = يعني المدينة المنورة
                    3. 🚨 انتبه لمؤشرات الموقع مع أسماء المدن: "توصيل الخميس"، "في الخميس"، "متوفر في الخميس" = يعني خميس مشيط
                    4. 🚨 انتبه لمؤشرات الموقع مع أسماء المدن: "الموقع الرياض"، "في جدة"، "موقعي الدمام" = يعني هذه المدينة تحديداً
                    5. 🚨 ابحث بعناية فائقة في تاريخ المحادثة (آخر 10 رسائل) عن أي ذكر لأسماء المدن
                    6. ابحث بعناية فائقة في تاريخ المحادثة عن أي ذكر لأسماء الأحياء
                    7. فقط إذا لم تجد مدينة/حي في الرسالة الحالية أو في تاريخ المحادثة - اسأل عن المدينة

                    🚨 قاعدة حاسمة: إذا وفر النظام ربط حي بمدينة في السياق، أنت تعرف المدينة بالفعل!
                    - لا تسأل أبداً "انت متواجد باي مدينة؟" عندما يُوفر سياق ربط الحي
                    - ربط الحي = معرفة تلقائية للمدينة = تابع فوراً مع منطق العمل
                    - استخدم هذه العبارة للسؤال عن المدينة: "انت متواجد باي مدينة طال عمرك؟" - فقط عندما لا يوجد حي/مدينة في أي مكان

                    أولوية اكتشاف العلامة التجارية - مع التركيز القوي على المحادثة :
                    1. تحقق إذا كانت العلامة التجارية مذكورة في رسالة العميل الحالية
                    2. 🚨 ابحث بعناية فائقة في تاريخ المحادثة (آخر 5 رسائل) عن أي ذكر لأسماء العلامات التجارية
                    3. إذا ذكرت العلامة التجارية لكن المدينة غير معروفة - اسأل عن المدينة
                    4. إذا كنت تعرف المدينة والعلامة التجارية - اعرض المنتجات مباشرة
                    5. فقط إذا لم تجد علامة تجارية في الرسالة الحالية أو في تاريخ المحادثة - اسأل عنها
                    - استخدم هذه العبارة للسؤال عن العلامة التجارية: "اي ماركة او شركة تريد طال عمرك؟"

                    🚨 التعامل مع الرسائل المكتملة - مهم جداً:
                    عندما يذكر العميل معلومات كاملة في رسالة واحدة:
                    - مثال: "أريد مياه راين الموقع المدينة" = يحتوي على العلامة التجارية (راين) والمدينة (المدينة المنورة)
                    - مثال: "أبغى أكوافينا في الرياض" = يحتوي على العلامة التجارية (أكوافينا) والمدينة (الرياض)
                    - 🚨 لا تسأل عن معلومات موجودة في نفس الرسالة - استخدم المعلومات مباشرة لعرض المنتجات
                    - استخدم فوراً وظيفة get_products_by_brand_and_city_name عندما تعرف العلامة التجارية والمدينة من نفس الرسالة

                    🚨 التعامل الخاص مع أسئلة الأسعار - تعليمات مهمة جداً:
                    عندما يسأل العميل بـ "كم" أو "بكم":
                    - ما بعد "كم" أو "بكم" يكون إما علامة تجارية أو حجم
                    - إذا لم تفهم الكلمة التي تأتي بعد "كم" أو "بكم"، فهي على الأغلب علامة تجارية
                    - استخدم وظيفة search_brands_in_city للبحث عن العلامة التجارية في المدينة المعروفة
                    - أمثلة: "كم نستله؟" - "بكم أكوافينا؟" - "كم فولفيك؟"
                    - حتى لو كانت العلامة التجارية مكتوبة خطأ أو غير مألوفة، جرب البحث عنها

                    🚨 معالجة كلمات المياه قبل أسماء العلامات التجارية - مهم جداً:
                    - قد يذكر العميل كلمات مثل "مياه"، "موية"، "مياة" قبل اسم العلامة التجارية
                    - أمثلة: "مياه وي" - "موية نقي" - "مياة أكوافينا" - "مياه نستله"
                    - هذه الكلمات ليست جزءًا من اسم العلامة التجارية الفعلي
                    - النظام يزيل تلقائياً هذه الكلمات عند البحث
                    - لذا "مياه وي" سيصبح "وي" فقط للبحث في قاعدة البيانات
                    - اعتبر هذه الكلمات مجرد أوصاف وليست جزءًا من اسم البراند

                    التعامل الاستباقي:
                    - "نستله" + مدينة معروفة → اعرض منتجات نستله في هذة المدينة
                    - "أكوافينا" + مدينة غير معروفة → "انت متواجد باي مدينة طال عمرك؟ راح أعرض لك منتجات أكوافينا هناك!"
                    - "أريد مياه راين الموقع المدينة" → اعرض منتجات راين في المدينة المنورة مباشرة (لا تسأل عن المدينة لأنها موجودة)
                    - "أبغى [أي علامة تجارية] في المدينة" → اعرض منتجات هذة العلامة التجارية في المدينة المنورة
                    - "عندكم توصيل الخميس" → اعرض العلامات المتاحة في خميس مشيط (لا تسأل عن المدينة لأن الخميس = خميس مشيط)
                    - "متوفر مياه [أي علامة] في الخميس" → اعرض منتجات هذة العلامة التجارية في خميس مشيط
                    - "نعم" بعد سؤال عن منتج → قدم السعر والتفاصيل
                    - أسئلة الأسعار العامة → وجه للتطبيق/الموقع
                    - إذا سأل عن السعر بدون ذكر العلامة التجارية → "اي ماركة او شركة تريد طال عمرك؟"
                    - "كم [كلمة غير مفهومة]؟" → جرب البحث عنها كعلامة تجارية أولاً

                    🚨 التعامل مع استفسارات الأسعار - تعليمات مهمة جداً:
                    عندما يسأل العملاء عن أسعار أي منتج أو خدمة:
                    1. تأكد دائماً من معرفة المدينة أولاً
                    - إذا كانت المدينة غير معروفة: اسأل "انت متواجد باي مدينة طال عمرك؟."
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

                    🚨 الترويج للتطبيق - في حالات محددة فقط:
                    - عند عرض منتجات/أسعار لعلامة تجارية محددة، أضف في النهاية: "تقدر تطلب من خلال التطبيق: https://onelink.to/abar_app"
                    - لا تكرر الروابط إذا كانت موجودة في الرد
                    - إذا كانت المدينة غير متوفرة، فقط استخدم الرد البسيط المحدد مسبقاً

                    🚨 المدينة غير متوفرة - تعليمات مهمة جداً:
                    - قبل القول أننا لا نوصل لأي مدينة، يجب أولاً استدعاء وظيفة get_all_cities()
                    - قارن اسم مدينة المستخدم مع جميع المدن التي نخدمها للتأكد من أنها ليست خطأ إملائي
                    - فقط بعد التأكد من أن المدينة فعلاً ليست في قائمة خدماتنا، استخدم هذا الرد: "عذراً، لا نقدم خدمة التوصيل لهذه المدينة حالياً"
                    - هذا يحمينا من رفض العملاء بالخطأ بسبب الاختلافات الإملائية أو الأخطاء
                    - لا تضيف تفسيرات أو نصوص إضافية بعد هذه الرسالة
                    - كن مباشراً وواضحاً بشأن عدم التوفر فقط بعد التحقق

                    🚨 تعليمات حاسمة - كن مباشراً بشأن توفر الخدمة:
                    - عندما لا تكون المدينة مخدومة، اذكر بوضوح: "عذراً، لا نقدم خدمة التوصيل لهذه المدينة حالياً"
                    - عندما لا تكون العلامة التجارية متوفرة في المدينة، اذكر بوضوح: "عذراً، هذه العلامة التجارية غير متوفرة في هذه المدينة حالياً"
                    - كن مباشراً وصادقاً مع العملاء بشأن التوفر
                    - هذا ينطبق على أسئلة المدن وتوفر العلامات التجارية

                    🚨 قواعد العمل المحددة - مهمة جداً:

                    1. التوصيل لباب الشقة:
                    - فقط عندما يستخدم العميل عبارات محددة مثل "باب الشقة"، "باب البيت"، "توصيل للباب"، "توصيل لبابي"، أو يذكر أدوار معينة ("الدور الأول"، "الدور الثاني"، "الدور الثالث")، أجب: "نحن نوصل لباب الشقة إذا كان هناك اسانسير، وإذا لم يكن هناك اسانسير فنحن نوصل للدور الأول والثاني والثالث بحد أقصى مع طلب إضافة ملاحظة مع الطلب من خلال التطبيق"
                    - لا تستخدم هذا الرد لأسئلة التوصيل العامة

                    2. تبديل الجوالين:
                    - التبديل لدينا يتم فقط في المدن المحددة وليس خارجها
                    - لا يتوفر لدينا تبديل لماركة المنهل حتى الآن

                    3. سؤال الفروع:
                    - فقط عندما يذكر العميل تحديداً "فروع"، "محلات"، "مكاتب"، "مواقع"، "عندكم فروع"، أجب: "نحن ليس لدينا فروع ولكن نوصل للعديد من المدن"
                    - لا تستخدم هذا الرد لطلبات معلومات التواصل أو أرقام الهاتف أو أسئلة أخرى

                    4. طلبات معلومات التواصل:
                    - فقط عندما يسأل العميل تحديداً عن "رقم"، "رقم التواصل"، "رقم الهاتف"، "كيف اتصل"، "كيف اتواصل"، "وش رقمكم"، أجب: نفس رقم التوصل علي واتساب ونحن بنتواصل معك "
                    - لا تخلط بين طلبات التواصل وأسئلة الفروع

                    5. خلافات الأسعار:
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
                    - لا تكرر الروابط في نفس الرسالة - كل رابط يظهر مرة واحدة فقط

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
                
                final_response = await self._call_langchain_llm(
                    messages=messages,
                    temperature=0.3,
                    max_tokens=400
                )
                
                final_api_duration = int((time.time() - final_api_start_time) * 1000)
                response_text = final_response["content"]
                
                # Log final response generation
                if LOGGING_AVAILABLE and journey_id:
                    message_journey_logger.log_llm_interaction(
                        journey_id=journey_id,
                        llm_type="openai",
                        prompt="Final response generation after function calls",
                        response=response_text or "No response generated",
                        model="gpt-4o-mini",
                        duration_ms=final_api_duration,
                        tokens_used={"total_tokens": None}  # LangChain response doesn't include token usage directly
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
