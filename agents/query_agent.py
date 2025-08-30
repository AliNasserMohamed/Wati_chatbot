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
        ✅ أسئلة عن تبديل الجوالين أو استبدال الجوالين أو تغيير الجوالين او دبات المياه
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
        - 🚨 أسئلة تبديل الجوالين متعلقة بالخدمة: "فيه تبديل جوالين؟"، "تبديل الجوالين"، "استبدال الجوالين"، "تبديل جالون"، "بدل الجالون"، "تغيير الجوالين" = متعلق بالخدمة
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
            ✅ Questions about gallon exchange, jug exchange, or bottle exchange service
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
            - 🚨 Example: "do you have Helwa water new design 200ml" = service-related (even if "Helva" is unknown brand)
            - 🚨 Any name mentioned with "water" should be considered potential brand = service-related
            - 🚨 Gallon exchange questions are service-related: "gallon exchange?", "jug exchange", "bottle exchange", "replace gallon", "swap gallon", "change gallon" = service-related
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
        
        # Apply brand-specific replacements
        cleaned_text = cleaned_text.replace("ايڤال", "ايفال")
        
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
                recent_messages = conversation_history[-7:]  # Last 7 messages for better context
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

    def _create_city_result(self, city: Dict[str, Any], found_in: str, user_language: str = 'ar') -> Dict[str, Any]:
        """Helper function to create language-appropriate city result"""
        if user_language == 'en':
            city_name_result = city["name_en"] or city["name"]
        else:
            city_name_result = city["name"]
        
        return {
            "city_id": city["id"],
            "city_name": city_name_result,        # Language-appropriate name
            "city_name_en": city["name_en"],      # Keep original English for reference
            "found_in": found_in
        }

    async def _extract_city_from_context(self, user_message: str, conversation_history: List[Dict] = None, user_language: str = 'ar') -> Optional[Dict[str, Any]]:
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
                        
                        # LANGUAGE-AWARE PRIORITY: Check language-appropriate city name first
                        if user_language == 'en':
                            # For English conversations, prioritize English city names
                            if city_name_en and city_name_en in user_message.lower():
                                print(f"🏙️ QueryAgent: Found English city '{city.get('name_en', city['name'])}' in last message")
                                
                                # Verify extraction with ChatGPT
                                is_verified = await self._verify_city_extraction(
                                    user_message, conversation_history, 
                                    city.get('name_en', city['name']), "current message"
                                )
                                
                                if is_verified:
                                    return self._create_city_result(city, "current_message_city", user_language)
                            # Fallback: Check normalized Arabic city name for English conversations (e.g., "Kharj" -> "الخرج")
                            elif city_name_ar and city_name_ar in current_content:
                                print(f"🏙️ QueryAgent: Found normalized Arabic city '{city['name']}' matching English input")
                                print(f"   Original: '{city.get('name', '')}' -> Normalized: '{city_name_ar}'")
                                print(f"   User message normalized: '{normalized_user_message}'")
                                
                                # Verify extraction with ChatGPT
                                is_verified = await self._verify_city_extraction(
                                    user_message, conversation_history, 
                                    city['name'], "current message"
                                )
                                
                                if is_verified:
                                    return self._create_city_result(city, "current_message_city", user_language)
                        else:
                            # For Arabic conversations, prioritize Arabic city names
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
                                    return self._create_city_result(city, "current_message_city", user_language)
                            # Fallback: Check English city name for Arabic conversations
                            elif city_name_en and city_name_en in user_message.lower():
                                print(f"🏙️ QueryAgent: Found direct city '{city['name']}' (English) in last message")
                                
                                # Verify extraction with ChatGPT
                                is_verified = await self._verify_city_extraction(
                                    user_message, conversation_history, 
                                    city['name'], "الرسالة الحالية"
                                )
                                
                                if is_verified:
                                    return self._create_city_result(city, "current_message_city", user_language)
                
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
                    for message in reversed(conversation_history[-7:]):  # Check last 7 messages
                        content = message.get("content", "")
                        # Normalize conversation history content for better matching
                        normalized_content = district_lookup.normalize_city_name(content)
                        content_lower = normalized_content.lower()
                        
                        # Check if any city name appears in the message (language-aware priority)
                        for city in all_cities:
                            # Normalize city names from database
                            city_name_ar = district_lookup.normalize_city_name(city.get("name", "")).lower()
                            city_name_en = city.get("name_en", "").lower().strip()
                            
                            # LANGUAGE-AWARE PRIORITY for conversation history
                            if user_language == 'en':
                                # For English conversations, prioritize English city names
                                if city_name_en and city_name_en in content.lower():
                                    print(f"🏙️ QueryAgent: Found English city in history '{city.get('name_en', city['name'])}'")
                                    
                                    # Verify extraction with ChatGPT
                                    is_verified = await self._verify_city_extraction(
                                        user_message, conversation_history, 
                                        city.get('name_en', city['name']), "conversation history"
                                    )
                                    
                                    if is_verified:
                                        return self._create_city_result(city, "conversation_history_city", user_language)
                                # Fallback: Check normalized Arabic city name
                                elif city_name_ar and city_name_ar in content_lower:
                                    print(f"🏙️ QueryAgent: Found normalized Arabic city in history matching English context '{city['name']}'")
                                    print(f"   Original: '{city.get('name', '')}' -> Normalized: '{city_name_ar}'")
                                    print(f"   History content normalized: '{normalized_content}'")
                                    
                                    # Verify extraction with ChatGPT
                                    is_verified = await self._verify_city_extraction(
                                        user_message, conversation_history, 
                                        city['name'], "conversation history"
                                    )
                                    
                                    if is_verified:
                                        return self._create_city_result(city, "conversation_history_city", user_language)
                            else:
                                # For Arabic conversations, prioritize Arabic city names
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
                                        return self._create_city_result(city, "conversation_history_city", user_language)
                                # Fallback: Check English city name
                                elif city_name_en and city_name_en in content.lower():
                                    print(f"🏙️ QueryAgent: Found English city in history '{city['name']}'")
                                    
                                    # Verify extraction with ChatGPT
                                    is_verified = await self._verify_city_extraction(
                                        user_message, conversation_history, 
                                        city['name'], "تاريخ المحادثة"
                                    )
                                    
                                    if is_verified:
                                        return self._create_city_result(city, "conversation_history_city", user_language)
                
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
                recent_messages = conversation_history[-7:]  # Last 7 messages for better context
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

    def _create_brand_result(self, brand: Dict[str, Any], found_in: str, user_language: str = 'ar') -> Dict[str, Any]:
        """Helper function to create language-appropriate brand result"""
        if user_language == 'en':
            brand_title_result = brand.get("title_en") or brand["title"]
        else:
            brand_title_result = brand["title"]
        
        return {
            "brand_title": brand_title_result,    # Language-appropriate name
            "brand_title_en": brand.get("title_en"),  # Keep original English for reference
            "found_in": found_in
        }

    async def _extract_brand_from_context(self, user_message: str, conversation_history: List[Dict] = None, user_language: str = 'ar') -> Optional[Dict[str, Any]]:
        """Extract brand information from current message and conversation history with AI verification and improved matching
        
        🔍 GENERAL EXTRACTION: Always extracts brands from ALL brands database (not city-specific)
        ⚠️ ALWAYS REQUIRES VERIFICATION: All returned brands need city availability check by LLM
        
        IMPORTANT: Ignores size terms like ابو ربع, ابو نص, ابو ريال as they are NOT brand names
        IMPORTANT: Removes water prefixes like مياه, موية, مياة before brand names
        ENHANCED: Searches for identical brand after normalizing, then partial matching
        Priority: 1) Brand in current message (exact → partial), 2) Brand in conversation history (last 5 messages)
        
        Returns: Brand info with needs_city_check=True (LLM must always verify city availability)
        """
        
        # Size terms that should NEVER be treated as brand names
        size_terms = ["ابو ربع", "ابو نص", "ابو ريال", "ابو ريالين"]
        
        # Check if the message only contains size terms - if so, don't extract any brand
        message_lower = user_message.lower()
        if any(size_term in message_lower for size_term in size_terms) and not any(brand_indicator in message_lower for brand_indicator in ["نستله", "أكوافينا", "العين", "القصيم", "المراعي"]):
            return None
            
        try:
            db = self._get_db_session()
            try:
                # Always get all brands - let LLM verify city availability later
                brands = data_api.get_all_brands(db)
                needs_city_check = True   # LLM must always verify brand availability in target city
                
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
                            print(f"   City verification needed: YES (always required)")
                            
                            # Verify extraction with ChatGPT
                            is_verified = await self._verify_brand_extraction(
                                user_message, conversation_history,
                                brand["title"], "الرسالة الحالية (مطابقة تامة)"
                            )
                            
                            if is_verified:
                                result = self._create_brand_result(brand, "current_message", user_language)
                                result["needs_city_check"] = needs_city_check
                                return result
                    
                    # If no exact match, try partial matching
                    for brand in brands:
                        # Normalize brand title for better matching
                        brand_title_normalized = self._clean_brand_name(brand.get("title", "")).lower()
                        
                        if brand_title_normalized and (brand_title_normalized in current_content or current_content in brand_title_normalized):
                            print(f"🔍 Brand partial match found:")
                            print(f"   Original brand: '{brand.get('title', '')}'")
                            print(f"   Normalized brand: '{brand_title_normalized}'")
                            print(f"   User message cleaned: '{current_content}'")
                            print(f"   City verification needed: YES (always required)")
                            
                            # Verify extraction with ChatGPT
                            is_verified = await self._verify_brand_extraction(
                                user_message, conversation_history,
                                brand["title"], "الرسالة الحالية (مطابقة جزئية)"
                            )
                            
                            if is_verified:
                                result = self._create_brand_result(brand, "current_message", user_language)
                                result["needs_city_check"] = needs_city_check
                                return result
                
                # PRIORITY 2: Check conversation history if no brand in current message
                if conversation_history:
                    for message in reversed(conversation_history[-7:]):  # Check last 7 messages
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
                                print(f"   City verification needed: YES (always required)")
                                
                                # Verify extraction with ChatGPT
                                is_verified = await self._verify_brand_extraction(
                                    user_message, conversation_history,
                                    brand["title"], "تاريخ المحادثة"
                                )
                                
                                if is_verified:
                                    result = self._create_brand_result(brand, "conversation_history", user_language)
                                    result["needs_city_check"] = needs_city_check
                                    return result
                
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
            for message in reversed(conversation_history[-7:]):  # Check last 7 messages
                if message.get("role") == "assistant":
                    content = message.get("content", "").lower()
                    # Check if the bot asked about needing a product or mentioned a price
                    if any(phrase in content for phrase in ["تحتاج", "تريد", "هل تريد", "هل تحتاج", "السعر", "الثمن", "do you need", "would you like", "price", "cost"]):
                        return True
            return True  # If user says yes in context of water conversation, it's likely relevant
        
        return False

    
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
            user_language = user_language
            print(f"🌐 Using conversation language '{user_language}' for city '{city_name}'")
            
            db = self._get_db_session()
            try:
                brands = data_api.get_brands_by_city_name(db, city_name, user_language)
                if not brands:
                    if user_language == 'ar':
                        error_msg = f"عذراً، لا نقدم خدمة التوصيل لمدينة {city_name} حالياً"
                    else:
                        error_msg = f"Sorry, we currently do not provide delivery service to {city_name}"
                    
                    return {
                        "success": False,
                        "error": error_msg,
                        "original_input": city_name,
                        "show_app_links": False
                    }
                
                # Extract language-appropriate city information
                # The data_api now returns language-appropriate city names in main field
                city_name_display = brands[0]["city_name"] if brands else city_name
                
                # Extract language-appropriate brand titles
                # The data_api now returns language-appropriate brand names in main field
                filtered_brands = []
                for brand in brands:
                    brand_name = brand.get("title", "")
                    if brand_name:  # Only include brands with names
                        filtered_brands.append(brand_name)
                
                # Remove duplicates and sort
                filtered_brands = sorted(list(set(filtered_brands)))
                
                # Create response message using language-appropriate city name
                if user_language == 'ar':
                    response_message = f"هذه هي العلامات التجارية المتاحة في {city_name_display}:"
                else:
                    response_message = f"These are the brands available in {city_name_display}:"
                
                city_info = city_name_display
                
                return {
                    "success": True, 
                    "data": filtered_brands,  # Simple list of brand names in detected language
                    "city_found": city_info,
                    "language": user_language,
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
            user_language = user_language
            print(f"🌐 Using conversation language '{user_language}' for brand '{brand_name}' in city '{city_name}'")
            
            # Clean the brand name by removing water prefixes
            cleaned_brand_name = self._clean_brand_name(brand_name)
            
            db = self._get_db_session()
            try:
                # Try with cleaned brand name first
                products = data_api.get_products_by_brand_and_city_name(db, cleaned_brand_name, city_name, user_language)
                
                # If no results with cleaned name, try original name
                if not products:
                    products = data_api.get_products_by_brand_and_city_name(db, brand_name, city_name, user_language)
                if not products:
                    if user_language == 'ar':
                        error_msg = f"عذراً، العلامة التجارية {brand_name} غير متوفرة في مدينة {city_name} حالياً"
                    else:
                        error_msg = f"Sorry, the {brand_name} brand is currently not available in {city_name}"
                    
                    return {
                        "success": False,
                        "error": error_msg,
                        "original_brand": brand_name,
                        "original_city": city_name
                    }
                
                # Extract language-appropriate brand and city information
                # The data_api now returns language-appropriate names in main fields
                brand_name_display = products[0]["brand_title"] if products else brand_name
                city_name_display = products[0]["city_name"] if products else city_name
                
                # Create simple product strings with prices
                filtered_products = []
                for product in products:
                    price = product["product_contract_price"]
                    # The data_api now returns language-appropriate product titles in main field
                    title = product["product_title"]
                    
                    # Check if product is a gallon/jug (don't show carton price for individual units)
                    is_gallon = any(keyword in title.lower() for keyword in ['جالون', 'gallon', '19 لتر', '20 لتر', 'جوالين', 'تبديل', 'exchange'])
                    
                    if user_language == 'ar':
                        if is_gallon:
                            # Arabic format for gallons: "Product Title - XX.XX ريال"
                            product_string = f"{title} - {price} ريال"
                        else:
                            # Arabic format for cartons: "Product Title - XX.XX ريال (سعر الكرتونة)"
                            product_string = f"{title} - {price} ريال (سعر الكرتونة)"
                    else:
                        if is_gallon:
                            # English format for gallons: "Product Title - XX.XX SAR"
                            product_string = f"{title} - {price} SAR"
                        else:
                            # English format for cartons: "Product Title - XX.XX SAR (carton price)"
                            product_string = f"{title} - {price} SAR (carton price)"
                    
                    filtered_products.append(product_string)
                
                # Create response message using language-appropriate names
                if user_language == 'ar':
                    response_message = f"منتجات {brand_name_display} المتاحة في {city_name_display}:"
                else:
                    response_message = f"{brand_name_display} products available in {city_name_display}:"
                
                brand_found = brand_name_display
                city_found = city_name_display
                
                return {
                    "success": True, 
                    "data": filtered_products,  # Simple list of product strings with prices
                    "language": user_language,
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
    
    def search_brands_in_city(self, brand_name: str, city_name: str, user_language: str = 'ar') -> Dict[str, Any]:
        """Search for brands by name within a specific city only with language support"""
        try:
            # Clean the brand name by removing water prefixes
            cleaned_brand_name = self._clean_brand_name(brand_name)
            
            db = self._get_db_session()
            try:
                # Search with both cleaned and original brand names
                brands = data_api.search_brands_in_city(db, cleaned_brand_name, city_name, user_language)
                
                # If no results with cleaned name, try original name
                if not brands:
                    brands = data_api.search_brands_in_city(db, brand_name, city_name, user_language)
                
                if not brands:
                    if user_language == 'ar':
                        error_msg = f"عذراً، العلامة التجارية {brand_name} غير متوفرة في مدينة {city_name} حالياً"
                    else:
                        error_msg = f"Sorry, the {brand_name} brand is currently not available in {city_name}"
                    
                    return {
                        "success": False,
                        "error": error_msg,
                        "original_brand": brand_name,
                        "original_city": city_name
                    }
                
                # Return found brands
                filtered_brands = [
                    {
                        "title": brand["title"],                    # Language-appropriate brand name
                        "title_en": brand.get("title_en", ""),     # Original English brand name
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
    
    def search_cities(self, query: str, user_language: str = 'ar') -> Dict[str, Any]:
        """Search cities by name with language support"""
        try:
            user_language = user_language
            db = self._get_db_session()
            try:
                cities = data_api.search_cities(db, query, user_language)
                
                if not cities:
                    if user_language == 'ar':
                        error_msg = f"عذراً، لا نقدم خدمة التوصيل لمدينة {query} حالياً"
                    else:
                        error_msg = f"Sorry, we currently do not provide delivery service to {query}"
                    
                    return {
                        "success": False,
                        "error": error_msg,
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
    


    def get_cheapest_products_by_city_name(self, city_name: str, user_language: str = 'ar') -> Dict[str, Any]:
        """Get cheapest products in each size for a specific city using city name with fuzzy matching"""
        try:
            user_language = user_language
            db = self._get_db_session()
            try:
                result = data_api.get_cheapest_products_by_city_name(db, city_name, user_language)
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
                recent_messages = conversation_history[-7:]  # Last 7 messages for context
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
            print(f"🔍 Classification: '{user_message[:50]}...' → {classification_result.upper()}")
            
            # Determine relevance
            # Fix: Check for exact match to avoid "not_relevant" being treated as relevant
            is_relevant = classification_result == "relevant"
            
            # Return True if relevant, False if not relevant
            return is_relevant
            
        except Exception as e:
            logger.error(f"Error classifying message relevance: {str(e)}")
            # On error, default to relevant to avoid blocking legitimate queries
            return True
    
    async def _validate_response_appropriateness(self, user_message: str, generated_response: str, conversation_history: List[Dict] = None, user_language: str = 'ar', city_context: Dict = None, brand_context: Dict = None) -> Dict[str, Any]:
        """
        Validate if the generated response is appropriate for the user's message.
        
        Args:
            user_message: The original user message
            generated_response: The response generated by the system
            conversation_history: Previous conversation context
            user_language: Language of the conversation
            city_context: Extracted city context information
            brand_context: Extracted brand context information
            
        Returns:
            Dict with 'is_appropriate' (bool), 'reason' (str), and 'confidence' (float)
        """
        try:
            # Build conversation context
            conversation_context = ""
            if conversation_history:
                recent_history = conversation_history[-7:]  # Last 7 messages for context
                for i, msg in enumerate(recent_history):
                    role = msg.get('role', 'unknown')
                    content = msg.get('content', '')
                    conversation_context += f"{i+1}. {role}: {content}\n"
            
            if user_language == 'ar':
                #                 validation_prompt = f"""أنت مقيم صارم جداً لجودة الردود في خدمة العملاء لشركة أبار لتوصيل المياه.

                # مهمتك: تحديد ما إذا كان الرد المُولد مناسب ومتعلق برسالة العميل أم لا.

                # رسالة العميل: "{user_message}"
                # الرد المُولد: "{generated_response}"

                # السياق السابق للمحادثة (آخر 3 رسائل):
                # {conversation_context}

                # 📋 نطاق عمل وكيل الاستعلامات - مهم جداً لفهم الردود المناسبة:

                # 🎯 ما يستطيع وكيل الاستعلامات فعله:
                # 1. ✅ عرض المدن المتاحة للتوصيل
                # 2. ✅ عرض العلامات التجارية المتاحة في كل مدينة
                # 3. ✅ عرض منتجات المياه وأسعارها لكل علامة تجارية
                # 4. ✅ البحث عن علامات تجارية في مدن محددة
                # 5. ✅ عرض أرخص المنتجات في مدينة معينة
                # 6. ✅ الإجابة على أسئلة المنتجات والأسعار والتوفر
                # 7. ✅ طرح أسئلة ودودة لجمع معلومات (مدينة، علامة، منتج)
                # 8. ✅ توجيه العميل للتطبيق/الموقع للطلب
                # 9. ✅ توجيه طلبات حساب الإجمالي أو تكلفة الطلبات للتطبيق (مثل "10 كرتون نوڤا كم السعر الإجمالي؟")
                # 10. ✅ معالجة طلبات تبديل الجوالين بنفس طريقة استعلامات المنتجات العادية مع فلترة المنتجات حسب كلمة "تبديل"
                # 11. ✅ التعامل مع الاستفسارات العامة عن المياه وأنواعها
                # 12. ✅ عرض اسعار علامة تجارية في مدينة محددة عندما يسال العميل عن الاسعار او يذكر اسم البراند
                # 13. ✅ عرض سعر الكرتونة الواحدة عندما يسأل العميل عن عدة كراتين (مثل "10 كراتين كم السعر؟") - مقبول لأن العميل يستطيع الحساب

                # ❌ ما لا يستطيع وكيل الاستعلامات فعله:
                # 1. ❌ أخذ طلبات فعلية أو معالجة الدفع
                # 2. ❌ تحديد مواعيد التوصيل أو التوصيل الفعلي
                # 3. ❌ التعامل مع مشاكل المندوبين أو التوصيل
                # 4. ❌ تعديل الطلبات الموجودة أو إلغاؤها
                # 5. ❌ التعامل مع الشكاوي أو مشاكل الخدمة
                # 6. ❌ تقديم معلومات التواصل أو العناوين
                # 7. ❌ التعامل مع طلبات تغيير المواقع أو العناوين

                # 🔧 وظائف النظام المتاحة لوكيل الاستعلامات:
                # - get_all_cities(): عرض جميع المدن
                # - get_brands_by_city_name(): عرض العلامات في مدينة
                # - get_products_by_brand_and_city_name(): عرض منتجات علامة في مدينة
                # - search_brands_in_city(): البحث عن علامات تجارية
                # - get_cheapest_products_by_city_name(): أرخص المنتجات في مدينة

                # 🚨 فهم منطق العمل الحاسم:
                # - النظام يتطلب معلومات المدينة والعلامة التجارية معاً لعرض المنتجات والأسعار
                # - إذا ذكر العميل العلامة التجارية لكن لم يذكر المدينة → السؤال عن المدينة ضروري ومناسب ✅
                # - إذا سأل العميل عن الأسعار لكن لم يحدد العلامة/المدينة → السؤال عن الاثنين ضروري ومناسب ✅
                # - إذا أراد العميل معلومات عامة لكن لم يحدد المدينة → السؤال عن المدينة ضروري ومناسب ✅
                # - هذه الأسئلة ليست عامة - هي ضرورية لتقديم خدمة دقيقة

                # 🔄 فهم تدفق المحادثات لتوصيل المياه - مهم جداً:
                # راجع الرسائل الثلاث الأخيرة لفهم السياق:

                # 1️⃣ عندما يحتاج العميل توصيل مياه أو يسأل عن الأسعار/العلامات:
                #    - إذا لم نعرف المدينة → السؤال "أي مدينة تريد؟" مناسب ✅
                #    - إذا عرفنا المدينة → عرض العلامات المتاحة في المدينة مناسب ✅
                
                # 2️⃣ إذا عرفنا المدينة والعميل يريد علامة معينة أو يسأل عن الأسعار:
                #    - عرض المنتجات المتاحة للعلامة المحددة مناسب ✅
                #    - أو السؤال "أي ماركة تحتاج؟" إذا لم يحدد العميل
                
                # 3️⃣ عندما يذكر العميل علامة تجارية معينة:
                #    - إذا لم نعرف المدينة → السؤال "أي مدينة أنت فيها؟" مناسب ✅
                #    - هذا يتبع التدفق المنطقي: علامة تجارية مذكورة → نحتاج المدينة → نعرض المنتجات
                #    - مثال: العميل يسأل عن "مياه راين" → السؤال عن المدينة صحيح ✅
                
                # 4️⃣ خدمة العملاء المفيدة:
                #    - عرض الخيارات المتاحة أفضل من مجرد السؤال
                #    - مثال: إذا عرفنا المدينة → اعرض العلامات المتاحة
                #    - مثال: إذا عرفنا العلامة → اعرض المنتجات والأسعار

                # 5️⃣ معالجة تبديل الجوالين:
                #    -  طلبات تبديل الجوالين يتم فيها سوال العميل عن المدينة ثم سواله عن العلامة التجارية بدون ذكر كل العلامات في مدينته بعد معرفة المدينة
                #    - اسأل عن المدينة والعلامة التجارية، ثم استخدم get_products_by_brand_and_city_name
                #    - قم بفلترة النتائج لعرض المنتجات التي تحتوي على "تبديل" أو "Exchange" في العنوان فقط
                #    - إذا لم توجد منتجات تبديل، أخبر العميل أن التبديل غير متوفر لهذه العلامة/المدينة
                #    - سير العمل الخاص: مدينة ← اسأل عن العلامة التجارية (بدون عرض كل العلامات) ← عرض منتجات التبديل

                # قواعد التقييم الصارمة:

                # 🔴 الرد غير مناسب إذا:
                # - يجيب على سؤال مختلف تماماً عن سؤال العميل
                # - يخلط بين طلبات التواصل وأسئلة الفروع 
                # - يخلط بين أسئلة التوصيل العامة وأسئلة التوصيل للباب
                # - يقدم معلومات غير متعلقة بسؤال العميل
                # - يحتوي على روابط مكررة في نفس الرسالة
                # - عام جداً ولا يجيب على السؤال المحدد
                # - يسأل أسئلة غير مفيدة لا تساعد في تحقيق طلب العميل
                # - يتجاهل المعلومات التي قدمها العميل بالفعل

                # ⚠️ تنبيه: لا ترفض الردود التي تجيب بصدق على توفر المنتجات!
                # ⚠️ حاسم: لا ترفض الردود التي تسأل عن المعلومات الضرورية (المدينة/العلامة) المطلوبة لتقديم خدمة دقيقة!
                # ⚠️ مهم جداً: لا ترفض الردود التي تذكر العلامة التجارية والمدينة بوضوح حتى لو كانت تخبر عن عدم التوفر!
                # 🔧 منطق الخدمة: النظام يجب أن يسأل عن المدينة/العلامة التجارية عند الحاجة لعرض المنتجات والأسعار - هذا سلوك مناسب!
                # 🔧 منطق التبديل: إذا ذكر الرد العلامة التجارية والمدينة بوضوح لطلب تبديل الجوالين، فهو مناسب بغض النظر عن التوفر!

                # 🟢 الرد مناسب إذا:
                # - يجيب بدقة على سؤال العميل المحدد
                # - يستخدم المعلومات الصحيحة حسب نوع السؤال
                # - يتماشى مع سياق المحادثة
                # - يقدم معلومات متعلقة بخدمات المياه عند الحاجة
                # - يتبع التدفق المنطقي: مدينة → علامات متاحة أو منتجات أو علامة مذكورة → يسأل عن المدينة → يعرض المنتجات
                # - يعرض الخيارات المتاحة بدلاً من مجرد السؤال عنها
                # - يقدم معلومات مفيدة حسب ما نعرفه من السياق
                # - يجيب بصدق عن توفر أو عدم توفر منتج معين (مقبول حتى لو لم يقدم بدائل)
                # - يسأل عن المعلومات الناقصة الضرورية لتحقيق طلب العميل:
                #   • يسأل عن المدينة عندما يذكر العميل علامة تجارية لكن المدينة غير معروفة ✅
                #   • يسأل عن العلامة التجارية عندما يسأل العميل عن المنتجات/الأسعار لكن العلامة غير معروفة ✅
                #   • يسأل أسئلة متابعة مفيدة لتقديم خدمة أفضل ✅

                # أمثلة على أخطاء شائعة:
                # - العميل يسأل عن رقم التواصل → الرد يتكلم عن الفروع ❌
                # - العميل يسأل عن التوصيل عامة → الرد عن التوصيل للباب فقط ❌ 
                # - العميل يسأل عن ماركة معينة → رد عام عن جميع الماركات ❌

                # أمثلة على ردود صحيحة ومقبولة:
                # - العميل يسأل عن علامة معينة → "هذه العلامة غير متاحة في الرياض أو اي مدينة اخري" ✅ (مقبول)
                # - العميل يذكر "مياه راين" → "أي مدينة أنت فيها؟ راح أعرض لك منتجات راين هناك!" ✅ (مناسب)
                # - العميل يسأل "أي علامات عندكم؟" → "أي مدينة أنت فيها؟ راح أعرض لك العلامات المتاحة هناك!" ✅ (مناسب)
                # - العميل يسأل "كم سعر المياه؟" → "أي علامة ومدينة تريد؟ راح أعرض لك الأسعار!" ✅ (مناسب)  
                # - العميل يقول "أبي توصيل مياه" → "أي مدينة وأي علامة تريد؟" ✅ (مناسب)
                # - العميل يسأل عن علامة معينة بشكل عام → السؤال عن المدينة لعرض منتجات هذه العلامة ✅ (مناسب)
                # - إخبار العميل بالحقيقة عن التوفر أفضل من معلومات خاطئة ✅
                # - العميل يسأل عن "10 كراتين نوڤا كم السعر؟" → عرض سعر الكرتونة الواحدة مناسب ✅ (العميل يستطيع حساب المجموع بنفسه)
                # - العميل يسأل عن تبديل الجوالين بدون ذكر العلامة والمدينة → اسأل عن المعلومات المفقودة ✅ (مناسب)
                # - العميل يسأل عن تبديل الجوالين وذكر المدينة والعلامة معاً → عرض منتجات التبديل فقط (التي تحتوي على "تبديل") مباشرة ✅ (مناسب)
                # - العميل يطلب تبديل جوالين وذكر العلامة (مثل "المنهل") والمدينة متاحة من التاريخ او من الرسالة الحالية  → عرض منتجات تبديل "المنهل" مباشرة ✅ (مناسب)
                # - العميل يطلب تبديل جوالين وذكر المدينة والعلامة متاحة من التاريخ → عرض منتجات التبديل مباشرة ✅ (مناسب)
                # - رد يحتوي على "منتجات المنهل المتاحة في الرياض أو اي مدينة  لتبديل الجوالين" → مناسب إذا كانت المعلومات متاحة ✅ (مناسب)
                # - العميل يطلب تبديل جوالين لعلامة تجارية في مدينة محددة → رد يوضح عدم التوفر مع ذكر العلامة والمدينة بوضوح ✅ (مناسب ومقبول)

                # 🚨 قاعدة مهمة: السؤال عن معلومات العلامة التجارية أو المدينة دائماً مناسب عندما تكون هذه المعلومات مطلوبة لتقديم خدمة دقيقة ✅

                # 🔍 استخراج المعلومات من الرسائل - قاعدة حاسمة:
                # - إذا كانت المدينة أو العلامة التجارية مذكورة في الرسالة الحالية أو تاريخ المحادثة → لا تسأل عنها مرة أخرى ✅
                # - استخدم المعلومات المتاحة من الرسالة الحالية أو المحادثة السابقة مباشرة ✅
                # - مثال: إذا ذكر المستخدم "الرياض" في رسالة سابقة، لا تسأل "أي مدينة؟" مرة أخرى ✅
                # - مثال: إذا ذكر المستخدم "مياه المنهل" في الرسالة الحالية، لا تسأل "أي علامة تجارية؟" ✅
                # - 🚨 مثال هام: إذا كان الرد "منتجات المنهل أو اي علامة المتاحة في الرياض أو الدمام او اي مدينة  لتبديل الجوالين" ويحتوي على معلومات صحيحة → مناسب ✅
                # - 🚨 لا تعتبر الرد غير مناسب إذا كان يعرض منتجات تبديل مع ذكر العلامة والمدينة الصحيحتين ✅

                # 🚨 قاعدة خاصة جداً لتبديل الجوالين - مهمة جداً:
                # - ✅ إذا كان الرد يحتوي على عبارات مثل: "يوجد تبديل جوالين للمنهل في الرياض" أو "تبديل جوالين [علامة تجارية] في [مدينة]" → هذا مناسب جداً ✅
                # - ✅ إذا كان الرد يعرض منتجات تبديل مع ذكر المدينة والعلامة التجارية صراحة → هذا مناسب وصحيح ✅
                # - ✅ إذا كان الرد يقول "تبديل جوالين للعلامة التجارية X في المدينة Y" ثم يعرض المنتجات → هذا ممتاز ✅
                # - ✅ إذا كان الرد يقول "خدمة تبديل الجوالين للعلامة التجارية [العلامة] غير متوفرة في مدينة [المدينة]" مع ذكر العلامة والمدينة بوضوح → هذا مناسب جداً ومقبول ✅
                # - ✅ ردود عدم التوفر التي تذكر العلامة التجارية والمدينة بوضوح للتبديل مناسبة ومقبولة تماماً ✅
                # - ✅ مثال مقبول: "عذراً، خدمة تبديل الجوالين للعلامة التجارية 'المنهل' غير متوفرة في مدينة رفحاء حالياً" → مناسب جداً ✅
                # - ❌ لا ترفض الردود التي تعرض منتجات تبديل مع ذكر المدينة والعلامة التجارية واضحة في الرد ❌
                # - ❌ لا ترفض الردود التي تخبر بصدق عن عدم توفر خدمة التبديل مع ذكر العلامة والمدينة بوضوح ❌

                # قيّم الرد وأخرج:
                # - is_appropriate: true أو false
                # - reason: سبب واضح ومحدد للقرار
                # - confidence: درجة ثقة من 0.0 إلى 1.0

                # أخرج الناتج بصيغة JSON فقط:
                # {{"is_appropriate": true/false, "reason": "السبب المفصل", "confidence": 0.0-1.0}}"""

                # Build context information
                city_context_info = ""
                if city_context:
                    city_context_info = f"""
🏙️ سياق المدينة المستخرج:
- اسم المدينة: {city_context.get('city_name', 'غير محدد')} ({city_context.get('city_name_en', 'غير محدد')})
- مصدر الاستخراج: {city_context.get('found_in', 'غير محدد')}
"""
                
                brand_context_info = ""
                if brand_context:
                    brand_context_info = f"""
🏷️ سياق العلامة التجارية المستخرج:
- اسم العلامة التجارية: {brand_context.get('brand_title', 'غير محدد')}
- مصدر الاستخراج: {brand_context.get('found_in', 'غير محدد')}
"""
                
                validation_prompt = f"""أنت مقيم صارم جداً لجودة الردود في خدمة العملاء لشركة أبار لتوصيل المياه.

مهمتك: تحديد ما إذا كان الرد المُولد مناسب ومتعلق برسالة العميل أم لا.

رسالة العميل: "{user_message}"
الرد المُولد: "{generated_response}"

السياق السابق للمحادثة (آخر 7 رسائل):
{conversation_context}

{city_context_info}
{brand_context_info}

🔍 تحليل السياق المستخرج:
- مدينة + علامة تجارية (مؤكدة التوفر) → عرض المنتجات لهذه العلامة في هذه المدينة مباشرة
- مدينة + علامة تجارية (تحتاج تأكيد) → التحقق أولاً من توفر العلامة في المدينة، ثم عرض المنتجات
- مدينة فقط → عرض العلامات المتاحة أو السؤال عن العلامة المرغوبة
- علامة تجارية فقط → السؤال عن المدينة
- بدون سياق → السؤال عن المعلومات الناقصة

🚨 التمييز بين تبديل الجوالين والمنتجات الجديدة:
- إذا ذكر العميل كلمات "تبديل"، "استبدال"، "بدل"، "exchange" → الرد المناسب هو عرض منتجات التبديل فقط.
- إذا كان الطلب عن منتجات عادية → عرض المنتجات العادية فقط (بدون "تبديل").
- إخبار العميل بعدم التوفر بوضوح مع ذكر المدينة والعلامة = رد مناسب ✅.

📋 نطاق عمل وكيل الاستعلامات:
- عرض المدن المتاحة
- عرض العلامات التجارية المتاحة في كل مدينة
- عرض منتجات المياه وأسعارها لكل علامة
- السؤال عن المعلومات الناقصة (مدينة/علامة/منتج)
- عرض أرخص المنتجات
- الرد بعدم التوفر
- توجيه العميل للتطبيق أو الموقع

❌ ما لا يستطيع فعله:
- أخذ الطلبات الفعلية أو مواعيد التوصيل
- الشكاوي / مشاكل المندوبين
- الدفع أو الإلغاء
- أي رد خارج موضوع المياه أو المنتجات

⚠️ قواعد ذهبية (Always Appropriate):
1- ❇️ إذا لم تُذكر المدينة → السؤال عنها رد مناسب دائماً  
2- ❇️ إذا لم تُذكر العلامة → السؤال عنها رد مناسب دائماً  
3- ❇️ إذا لم تُذكر المدينة ولا العلامة → السؤال عنهما رد مناسب دائماً  
4- ❇️ إذا ذكر العميل مدينة فقط → عرض العلامات في المدينة أو سؤال عن العلامة رد مناسب دائماً  
5- ❇️ إذا عُرفت المدينة والعلامة → عرض المنتجات رد مناسب دائماً  
6- ❇️ إذا المنتج/العلامة غير متوفر → الرد بعدم التوفر (مع أو بدون بدائل) رد مناسب دائماً  
7- ❇️ عرض قائمة المنتجات أو قائمة المدن أو قائمة العلامات = رد مناسب دائماً طالما ضمن نطاق المياه  

🔴 الرد غير مناسب إذا فقط:
- تجاهل المدينة أو العلامة المذكورة
- عرض منتجات جديدة بدلاً من التبديل أو العكس
- أجاب عن موضوع آخر غير متعلق بالمياه
- عام جداً بدون إفادة (مثال: "نعم متوفر" بدون تفاصيل أو سؤال تكميلي)
- كرر سؤال عن معلومة تم ذكرها بالفعل في المحادثة

🟢 الرد مناسب إذا:
- يلتزم بالسياق (مدينة/علامة/نوع المنتج)
- يسأل فقط عن المعلومات الناقصة
- يعرض منتجات أو علامات أو مدن بشكل صحيح
- يوضح عدم التوفر عند الحاجة

أخرج النتيجة النهائية فقط:
{{
  "is_appropriate": true/false,
  "reason": "سبب التقييم",
  "confidence": 0.0-1.0
}}
"""


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
9. ✅ Redirect total order calculation requests to the app (like "10 cartons of Nove, what's the total cost?")
10. ✅ Handle gallon exchange requests using the same workflow as regular product queries, filtering products by "تبديل" or "Exchange" in title
11. ✅ Handle general inquiries about water and water types
12. ✅ Show single carton price when customer asks about multiple cartons (like "10 cartons, what's the price?") - acceptable as customer can calculate total

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

4️⃣ Gallon Exchange Handling:
   - Gallon exchange requests have SPECIAL workflow: ask for city, then ask for brand WITHOUT showing all brands in that city
   - Ask for city and brand separately, then use get_products_by_brand_and_city_name
   - Filter results to show only products with "تبديل" or "Exchange" in title
   - If no exchange products found, inform customer exchange is not available for that brand/city
   - Special workflow: city ← ask for brand (without showing all brands) ← show exchange products

Strict Evaluation Rules:

🔴 Response is INAPPROPRIATE if:
- Answers a completely different question than what customer asked
- Confuses contact requests with branches questions
- Confuses general delivery questions with door delivery questions  
- Provides information unrelated to customer's question
- Contains duplicate links in the same message
- Too generic and doesn't address the specific question

🟢 Response is ALWAYS APPROPRIATE if:
1. Asking about the city when not known from context
2. Asking about the brand when not known from context  
3. Asking about both city and brand when not known from context
4. Showing brands available in a city (when not discussing gallon exchange)
5. Showing products after knowing both city and brand
6. Answering about brand unavailability in a specific city (with or without alternatives)

⚠️ Important Evaluation Warning:
- ❌ DO NOT reject responses that mention a specific brand for a specific city (e.g., "In Al-Qurayyat, we have 'Hana' brand")
- ✅ This type of response means the system has verified availability and is very appropriate
- ✅ If response mentions a brand name with a city name, it means the system knows this brand is available in that city
- ✅ Appropriate examples: "In Riyadh, we have Nestle brand" or "In Jeddah, we offer Al-Qassim brand"
- ❌ DO NOT reject responses that display products of a brand in a city after knowing both city and brand from context
- ❌ DO NOT reject responses that list available brands in a city after knowing the city from user message or history
- ✅ Displaying products after knowing city and brand = desired goal
- ✅ Listing brands after knowing city = appropriate workflow step

⚠️ Warning: Don't reject responses that honestly answer about product availability!
⚠️ Critical: Don't reject responses that clearly mention both brand and city even if they state non-availability!
⚠️ Exchange Logic: If response clearly mentions brand and city for gallon exchange request, it's appropriate regardless of availability!
🟢 Response is APPROPRIATE if:
- Accurately answers the customer's specific question
- Uses correct information based on question type
- Aligns with conversation context
- Provides relevant water service information when needed
- Follows logical flow: city → available brands or products
- Shows available options instead of just asking about them
- Provides helpful information based on what we know from context
- Honestly answers about availability or non-availability of specific products (acceptable even without alternatives)
- ✅ If response mentions a specific brand for a specific city (e.g., "In Riyadh, we have Nestle brand") → This means the system has verified availability and is very appropriate ✅
- ✅ If response says "We have [brand name]" or "We offer [brand name]" for a specific city → Appropriate as it's verified information ✅
- ✅ Showing one or several specific brands for a specific city is an appropriate and helpful response ✅
- ✅ If the system knows the city and shows available brand(s) → Completely appropriate ✅
- ✅ Displaying products of a specific brand in a specific city after we know both city and brand from conversation → Very appropriate ✅
- ✅ Listing available brands in a specific city after user sends their city or we know it from history → Appropriate and helpful ✅
- ✅ If we have both city and brand context and response shows products and prices → This is the desired goal and completely appropriate ✅
- ✅ If we have city context only and response shows available brands in that city → Appropriate and helpful for customer ✅

Common Error Examples:
- Customer asks about contact number → Response talks about branches ❌
- Customer asks about general delivery → Response only about door delivery ❌
- Customer asks about specific brand → Generic response about all brands ❌

Examples of Correct and Acceptable Responses:
- Customer asks about "Al Manhal water" → "Sorry, Al Manhal water is currently not available" ✅ (Acceptable)
- Customer asks about specific brand → "This brand is not available in Riyadh" ✅ (Acceptable)
- Telling customer the truth about availability is better than wrong information ✅
- Customer asks "10 cartons of Nove, what's the price?" → Showing price per carton is appropriate ✅ (Customer can calculate total themselves)
- Customer asks about gallon exchange without mentioning brand and city → Ask for missing information ✅ (Appropriate)
- Customer asks about gallon exchange with both city and brand mentioned → Show exchange products only (containing "تبديل" or "Exchange") directly ✅ (Appropriate)
- Customer requests gallon exchange and mentions brand (like "Al Manhal") with city available from history → Show "Al Manhal" exchange products directly ✅ (Appropriate)
- Customer requests gallon exchange and mentions city with brand available from history → Show exchange products directly ✅ (Appropriate)
- Response containing "Al Manhal products available in Riyadh for gallon exchange" → Appropriate if information is available ✅ (Appropriate)
- Customer requests gallon exchange for specific brand in specific city → Response explaining non-availability with clear brand and city mentioned ✅ (Appropriate and acceptable)

🚨 Important rule: Asking for brand or city information is always appropriate when this information is needed to provide accurate service ✅

🔍 Information Extraction from Messages - Critical Rule:
- If city or brand is mentioned in current message or conversation history → DO NOT ask for it again ✅
- Use available information from current message or previous conversation directly ✅
- Example: If user mentioned "Riyadh" in previous message, don't ask "Which city?" again ✅
- Example: If user mentioned "Al Manhal water" in current message, don't ask "Which brand?" ✅
- 🚨 Important example: If response is "Al Manhal products available in Riyadh for gallon exchange" with correct information → Appropriate ✅
- 🚨 Don't consider response inappropriate if it shows exchange products with correct brand and city mentioned ✅

🚨 SPECIAL RULE FOR GALLON EXCHANGE - VERY IMPORTANT:
- ✅ If response contains phrases like: "Yes, gallon exchange for Al Manhal in Riyadh" or "gallon exchange [brand] in [city]" → This is very appropriate ✅
- ✅ If response shows exchange products while explicitly mentioning both city and brand → This is appropriate and correct ✅
- ✅ If response says "gallon exchange for brand X in city Y" then shows products → This is excellent ✅
- ✅ If response says "gallon exchange service for brand [brand] is not available in city [city]" with clear brand and city mentioned → This is very appropriate and acceptable ✅
- ✅ Non-availability responses that clearly mention both brand and city for exchange are appropriate and acceptable ✅
- ✅ Example acceptable: "Sorry, gallon exchange service for brand 'Al Manhal' is not available in Rafha city currently" → Very appropriate ✅
- ❌ DO NOT reject responses that show exchange products with clear city and brand mentioned in the response ❌
- ❌ DO NOT reject responses that honestly state non-availability of exchange service with clear brand and city mentioned ❌

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

            
            try:
                # Generate response using internal method
                response_result = await self._generate_response_internal(user_message, conversation_history, user_language, journey_id)
                if isinstance(response_result, tuple):
                    response, city_context, brand_context = response_result
                else:
                    # Fallback for backward compatibility
                    response, city_context, brand_context = response_result, None, None
                
                # If empty response, skip validation and try again
                if not response or response.strip() == "":

                    if attempt < max_attempts:
                        continue
                    else:
                        # Return empty string when all attempts fail instead of error message
                        # This ensures no response is sent to customer and human agent can handle
                        return ""
                
                # Validate response appropriateness

                validation_result = await self._validate_response_appropriateness(
                    user_message=user_message,
                    generated_response=response,
                    conversation_history=conversation_history,
                    user_language=user_language,
                    city_context=city_context,
                    brand_context=brand_context
                )
                
                # Log validation result to message journey
                if LOGGING_AVAILABLE and journey_id:
                    message_journey_logger.add_step(
                        journey_id=journey_id,
                        step_type="response_validation",
                        description=f"Response validation completed (attempt {attempt})",
                        data={
                            "is_appropriate": validation_result['is_appropriate'],
                            "reason": validation_result['reason'],
                            "confidence": validation_result['confidence'],
                            "attempt_number": attempt,
                            "user_message_length": len(user_message),
                            "response_length": len(response),
                            "agent_reply": response,
                            "validation_output": validation_result,
                            "city_extraction": {
                                "city_name": city_context.get('city_name') if city_context else None,
                                "city_name_en": city_context.get('city_name_en') if city_context else None,
                                "found_in": city_context.get('found_in') if city_context else None,
                                "district_name": city_context.get('district_name') if city_context else None
                            },
                            "brand_extraction": {
                                "brand_title": brand_context.get('brand_title') if brand_context else None,
                                "found_in": brand_context.get('found_in') if brand_context else None
                            },
                            "refusal_reason": validation_result['reason'] if not validation_result['is_appropriate'] else None
                        }
                    )
                
                if validation_result['is_appropriate']:
                    print(f"✅ Validation: ACCEPT → {response[:100]}...")
                    return response
                else:
                    print(f"❌ Validation: REFUSE → {validation_result['reason']}")
                    if attempt < max_attempts:
                        continue
                    else:
                        return ""
                        
            except Exception as e:
                print(f"❌ Error in attempt {attempt}: {str(e)}")
                if attempt < max_attempts:
                    continue
                else:
                    error_msg = "عذراً، حدث خطأ في معالجة الاستعلام. الرجاء المحاولة مرة أخرى." if user_language == 'ar' else "Sorry, there was an error processing the query. Please try again."
                    return error_msg

    async def _generate_response_internal(self, user_message: str, conversation_history: List[Dict] = None, user_language: str = 'ar', journey_id: str = None) -> tuple:
        """
        Internal method for generating response (separated for retry logic)
        Returns tuple of (response, city_context, brand_context)
        """
        # STEP 1: Check if message is relevant to water delivery services
        print("🔍 Checking message relevance...")
        is_relevant = await self._classify_message_relevance(user_message, conversation_history, user_language)
        
        if not is_relevant:
            print(f"❌ Message not relevant to water delivery services: {user_message}...")
            # Return None or empty string to indicate the agent should not reply
            return ("", None, None)
        
        print("✅ Message is relevant to water delivery services")



        # STEP 2: Check if this is a "yes" response to a previous product question
        if self._check_for_yes_response(user_message, conversation_history):
            print("✅ Detected 'yes' response - handling product confirmation")
        
        max_function_calls = 5
        function_call_count = 0
        
        try:
            # Check if we already have city information from current message or conversation history
            city_context = await self._extract_city_from_context(user_message, conversation_history, user_language)
            
            # Check if we have brand information
            brand_context = await self._extract_brand_from_context(
                user_message, 
                conversation_history, 
                user_language  # ← Pass language parameter
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
                
                brand_info = f"\n\nBRAND CONTEXT: The customer mentioned '{brand_context['brand_title']}' - detected from {found_where}. 🔍 EXTRACTION TYPE: GENERAL (from ALL brands database - NOT city-specific). ⚠️ MANDATORY VERIFICATION: This brand may or may not be available in the target city. You MUST first call get_brands_by_city_name('city_name') to verify if '{brand_context['brand_title']}' exists in that city's brand list, then show products only if confirmed available."
            
            if user_language == 'en':
                system_message = {
                    "role": "system",
                    "content": f"""You are a friendly customer service employee at Abar Water Delivery Company in Saudi Arabia.{city_info}{brand_info}

                    📋 Important terminology for understanding Arabic customers (for understanding only - don't mention to customers):
                    - "قوارير المياه" = "الجوالين" (same product - water gallons)
                    - "حبة مياه" = "زجاجة مياه" (common term - means water bottle)
                    - "مقاس" = size/volume (e.g., "مقاس 200 مل" means 200ml size)
                    - Example: "احتاج كرتونة 48 حبة مقاس 200 مل" = "I need a carton of 48 bottles, 200ml size"

                    🔍 CRITICAL: Brand Extraction Understanding:
                    - When a brand is detected in the context, it's extracted from ALL brands database (GENERAL extraction)
                    - This means the brand may or may not be available in the customer's city
                    - ALWAYS verify brand availability by calling get_brands_by_city_name() first before showing products
                    - Only show products if the brand exists in that city's available brands list

                    Your job is to help customers with:
                    
                    🚨🔄 HIGHEST PRIORITY: Gallon Exchange Handling - Special and Strict Workflow:
                      
                      📝 Understanding Gallon Exchange Process:
                      Gallon exchange means the customer brings an empty gallon and receives a full one for the exchange price.
                      This is a different service from buying a new gallon.
                      
                      🧠 Step 1: Identify Request Type First - MOST IMPORTANT
                      - Read the customer's message and conversation history completely and determine: is this a gallon exchange request or new water purchase?
                      - Keywords for gallon exchange: "gallon exchange", "exchange gallon", "replace gallon", "gallon replacement"
                      
                      🚨 If request is related to gallon exchange - Special different workflow:
                      1. NEVER use get_brands_by_city_name ❌
                      2. If you don't know the city → ask about the city
                      3. If you don't know the brand → ask "Which brand do you want to exchange?" (without showing brand list)
                      4. Once you know both city and brand → use get_products_by_brand_and_city_name directly
                      
                      5. Use get_products_by_brand_and_city_name function normally
                      6. 🚨 CRITICALLY IMPORTANT: Filter returned products to show only products containing "Exchange" or "تبديل" in the title - don't show "New" or other products
                      7. If no exchange products exist for that brand/city, tell customer exchange service is not available for this brand in this city
                      8. Displayed prices are exchange prices not purchase prices
                      9. Examples of exchange product titles:
                       - "19L Gallon - Exchange" (English)
                      10. Handle text unification: "Exchange"/"تبديل" must all be recognized
                      
                    Other Basic Functions:
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

                    🚨 NEVER ASSUME CITIES - ABSOLUTELY CRITICAL:
                    - NEVER assume or guess a city for any brand name
                    - If customer mentions ONLY a brand name (like "مياه المنهل" or "Nestle water") without a city:
                      → ALWAYS ask "أي مدينة أنت فيها؟" (Which city are you in?)
                      → DO NOT call any search functions without explicit city mention
                      → DO NOT assume "المدينة المنورة" or any other city
                    - Only call search functions when you have EXPLICIT city information from:
                      → User's current message
                      → Conversation history
                      → System-provided city context
                    - Example: "مياه المنهل" → Ask for city, don't assume Medina
                    - Example: "مياه المنهل الرياض" → Use Riyadh as specified

                    🚨 MANDATORY FUNCTION CALLING - CRITICAL:
                    - When you know the city but need to show brands: IMMEDIATELY call get_brands_by_city_name function
                    - When you know both city and brand but need products: IMMEDIATELY call get_products_by_brand_and_city_name function
                    - NEVER say "let me check" or "one moment" without actually calling the function
                    - If system provides city context, use the function calls immediately in the same response
                    - Do NOT provide generic responses - always use functions to get real data
                    - 🚨 LANGUAGE CONSISTENCY: The functions will automatically return English brand/product names for English conversations - use them directly without translation

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
                    
                    🚨 IMPORTANT PRICE CLARIFICATION:
                    - For carton/bottle products: ALL PRICES ARE FOR CARTONS, NOT SINGLE BOTTLES. Add "(carton price)" in English or "(سعر الكرتونة)" in Arabic.
                    - For gallon/jug products: Prices are per individual gallon. DO NOT add "(carton price)" for gallons/jugs.


                    ORDER REQUESTS - REDIRECT TO APP:
                    When user wants to place an order, make a purchase, or asks how to order, ALWAYS redirect them to the app/website with this message:
                    "You can find all products, prices, and place orders through our app: https://onelink.to/abar_app or on our website: https://abar.app/en/store/"
                    - Never try to take orders through the chat
                    - Never ask for delivery details, payment info, or personal information
                    - Always direct them to the official app/website for ordering
                    
                    TOTAL PRICE AND ORDER CALCULATIONS - REDIRECT TO APP:
                    When user asks about:
                    - Total prices or price lists ("prices", "price list", "all prices", "total prices")
                    - Total order calculations ("10 cartons of Nove, what's the total?", "total", "total cost", "sum")
                    - General price inquiries for multiple items or quantities
                    ALWAYS redirect them to the app with this message:
                    "You can find all products and prices in our app: https://onelink.to/abar_app or on our website: https://abar.app/en/store/"

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
                    for msg in conversation_history[-7:]:  # Check last 7 messages
                        all_conversation_text += " " + msg.get("content", "")
                
                if "quarter" in all_conversation_text or "half" in all_conversation_text or "riyal" in all_conversation_text:
                    system_message["content"] += "\n\nAdditional info: Quarter size = 200ml or 250ml, Half size = 330ml or 300ml, Riyal size = 600ml or 550ml, Two Riyal size = 1.5L"
                if "groundwater" in all_conversation_text or "artesian" in all_conversation_text:
                    system_message["content"] += (
                        "\n\nAdditional info: Groundwater/artesian water brands include: "
                        "Nova, Naqi, Berrin, Mawared, B, Vio, Miles, Aquaya, Aqua 8, Mana, Tania, Abar Hail, Oska, Nestle, Ava, Hena, Saqya Al Madina, Deman, Hani, Sahtak, Halwa, Athb, Aus, Qataf, Rest, Eval, We."
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
                    
                    brand_info_ar = f"\n\nسياق العلامة التجارية: العميل ذكر '{brand_context['brand_title']}' - تم اكتشافها من {found_where_ar}. 🔍 نوع الاستخراج: عام (من قاعدة بيانات جميع العلامات التجارية - ليس خاص بمدينة). ⚠️ تحقق إجباري: هذه العلامة التجارية قد تكون متوفرة أو غير متوفرة في المدينة المستهدفة. يجب أولاً استدعاء get_brands_by_city_name('اسم_المدينة') للتحقق من وجود '{brand_context['brand_title']}' في قائمة علامات تلك المدينة، ثم عرض المنتجات فقط إذا تم تأكيد التوفر."
                
                system_message = {
                    "role": "system",
                    "content": f"""أنت موظف خدمة عملاء ودود في شركة أبار لتوصيل المياه في السعودية.{city_info_ar}{brand_info_ar}

                    📋 معلومات مهمة لفهم المصطلحات (للفهم فقط - لا تذكرها للعميل):
- قوارير المياه = الجوالين (نفس المنتج)
- قوارير هي الجوالين
- "حبة مياه" = "زجاجة مياه" (مصطلح شائع)
- "مقاس" = الحجم/السعة (مثل: "مقاس 200 مل" تعني حجم 200 مل)
- مثال: "احتاج كرتونة 48 حبة مقاس 200 مل" = "احتاج كرتونة 48 زجاجة حجم 200 مل"

                    🔍 مهم جداً: فهم استخراج العلامات التجارية:
                    - عندما يتم اكتشاف علامة تجارية في السياق، يتم استخراجها من قاعدة بيانات جميع العلامات التجارية (استخراج عام)
                    - هذا يعني أن العلامة التجارية قد تكون متوفرة أو غير متوفرة في مدينة العميل
                    - يجب دائماً التحقق من توفر العلامة التجارية عبر استدعاء get_brands_by_city_name() أولاً قبل عرض المنتجات
                    - عرض المنتجات فقط إذا كانت العلامة التجارية موجودة في قائمة العلامات المتاحة لتلك المدينة

                    وظيفتك مساعدة العملاء في:
                    
                    🚨🔄 أولوية عليا: معالجة تبديل الجوالين - سير عمل خاص وصارم جداً:
                      
                      📝 فهم عملية تبديل الجوالين:
                      تبديل الجوالين يعني أن العميل يحضر الجالون الفارغ ويستلم جالون مليء بالماء مقابل سعر التبديل.
                      هذه خدمة مختلفة عن شراء جالون جديد.
                      
                      🧠 خطوة 1: تحديد نوع الطلب أولاً وأهم شيء
                      - اقرأ رسالة العميل ومحادثته كاملة وحدد: هل هو طلب تبديل جوالين أم شراء مياه جديدة؟
                      - كلمات مفتاحية لتبديل الجوالين: "تبديل الجوالين"، "تبديل جالون"، "استبدال الجوالين"، "بدل الجالون"، "تغيير الجوالين"
                      
                      🚨 إذا كان الطلب متعلق بتبديل الجوالين - سير عمل خاص مختلف تماماً:
                      1. لا تستخدم get_brands_by_city_name أبداً ❌
                      2. إذا لم تكن تعرف المدينة → اسأل عن المدينة
                      3. إذا لم تكن تعرف العلامة التجارية → اسأل "أي علامة تجارية تريد تبديلها؟" (بدون عرض قائمة العلامات)
                      4. بمجرد معرفة المدينة والعلامة التجارية → استخدم get_products_by_brand_and_city_name مباشرة
                      
                      5. استخدم وظيفة get_products_by_brand_and_city_name بشكل طبيعي
                      6. 🚨 مهم جداً وصارم: قم بفلترة المنتجات المرجعة لعرض المنتجات التي تحتوي على كلمة "تبديل" في عنوانها فقط - لا تعرض منتجات "جديد" أو غيرها
                      7. إذا لم توجد منتجات تبديل لتلك العلامة التجارية/المدينة، أخبر العميل أن خدمة التبديل غير متوفرة لهذه العلامة في هذه المدينة
                      8. الأسعار المعروضة هي أسعار التبديل وليس أسعار الشراء
                      9. أمثلة على عناوين منتجات التبديل:
                       - "جالون 19 لتر - تبديل" (عربي)
                      10. تعامل مع توحيد النصوص: "تبديل"/"تبدیل"/ يجب التعرف عليها جميعاً
                      
                    الوظائف الأساسية الأخرى:
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
                    
                    🚨 قواعد مهمة للتمييز بين الأسئلة والمواقع:
                    - ❌ لا تفسر "المدينة" كـ "المدينة المنورة" إذا كانت في سياق سؤال مثل:
                      • "أي مدينة" أو "بأي مدينة" أو "في أي مدينة" = أسئلة، ليست مواقع
                      • "انت متواجد باي مدينة" = سؤال عن الموقع، ليس تحديد موقع
                      • "كم مدينة" أو "اي مدن" = أسئلة عامة
                    - ✅ فسر "المدينة" كـ "المدينة المنورة" فقط في هذه السياقات:
                      • "الموقع المدينة" أو "في المدينة" أو "أنا في المدينة" = تحديد موقع
                      • "من المدينة" أو "ساكن المدينة" = تحديد موقع
                      • "توصيل المدينة" أو "أريد مياه المدينة" = تحديد موقع
                    
                    🚨 مهم جداً: عندما تسمع "المدينة" في سياق تحديد الموقع (وليس السؤال)، تعامل معها كأنها "المدينة المنورة"
                    - 🚨 مهم جداً: عندما تسمع "الخميس" في سياق تحديد الموقع (وليس السؤال)، تعامل معها كأنها "خميس مشيط"
                    - 🚨 خاصة عندما يقول العميل "الموقع المدينة" أو "في المدينة" - هذا يعني المدينة المنورة بلا شك
                    - 🚨 خاصة عندما يقول العميل "توصيل الخميس" أو "في الخميس" أو "متوفر في الخميس" - هذا يعني خميس مشيط بلا شك
                    - جميع هذه المدن يتم التوصيل لها
                    - لا تسأل عن المدينة إذا ذكر العميل "المدينة" أو "الخميس" في سياق تحديد الموقع (وليس السؤال)
                    - اذا لم يتم ذكر المدينة في الرسالة الحالية أو تاريخ المحادثة، فقم بسوال العميل عن المدينة
                   

                    أسلوب التواصل:
                    - تكلم مثل موظف خدمة عملاء حقيقي
                    - كن طبيعي وودود ومحادثي
                    - لا تستخدم أبداً عبارات مثل "رد الذكاء الاصطناعي" أو "رد المساعد" أو "أنا ذكاء اصطناعي"
                    - رد كأنك شخص حقيقي يعمل في الشركة

                    🚨 الانتباه الفائق لتاريخ المحادثة - مهم جداً:
                    - راجع دائماً تاريخ المحادثة بعناية للعثور على المدن والعلامات التجارية المذكورة سابقاً
                    - ابحث في آخر 5 رسائل للعميل والمساعد عن أي ذكر لأسماء المدن أو العلامات التجارية
                    - 🚨 انتبه بشكل خاص لهذه العبارات في الرسالة الحالية (في سياق تحديد الموقع فقط): "الموقع المدينة"، "في المدينة"، "أنا في المدينة" = تعني المدينة المنورة
                    - 🚨 انتبه بشكل خاص لهذه العبارات في الرسالة الحالية (في سياق تحديد الموقع فقط): "توصيل الخميس"، "في الخميس"، "أنا في الخميس"، "متوفر في الخميس" = تعني خميس مشيط
                    - ❌ تجاهل "المدينة" إذا كانت في سياق سؤال: "أي مدينة"، "بأي مدينة"، "في أي مدينة"، "انت متواجد باي مدينة"
                    - لا تسأل عن معلومات موجودة بالفعل في تاريخ المحادثة أو في الرسالة الحالية
                    - استخدم المعلومات المستخرجة من التاريخ حتى لو كانت من رسائل قديمة

                    🚨 استدعاء الوظائف الإجباري - مهم جداً:
                    - عندما تعرف المدينة لكن تحتاج لعرض العلامات التجارية: استدعي فوراً وظيفة get_brands_by_city_name
                    - عندما تعرف المدينة والعلامة التجارية لكن تحتاج للمنتجات: استدعي فوراً وظيفة get_products_by_brand_and_city_name
                    - 🚨 اتساق اللغة: الوظائف ستعيد تلقائياً أسماء العلامات التجارية/المنتجات باللغة الانجليزية للمحادثات الانجليزية - استخدمها مباشرة بدون ترجمة
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
                    2. 🚨 تمييز السياق: تأكد أن "المدينة" ليست في سياق سؤال قبل تفسيرها كـ "المدينة المنورة"
                       • ❌ أسئلة: "أي مدينة"، "بأي مدينة"، "في أي مدينة"، "انت متواجد باي مدينة"
                       • ✅ تحديد موقع: "الموقع المدينة"، "في المدينة"، "موقعي المدينة" = المدينة المنورة
                    3. 🚨 انتبه لمؤشرات الموقع مع أسماء المدن: "توصيل الخميس"، "في الخميس"، "متوفر في الخميس" = يعني خميس مشيط
                    4. 🚨 انتبه لمؤشرات الموقع مع أسماء المدن: "الموقع الرياض"، "في جدة"، "موقعي الدمام" = يعني هذه المدينة تحديداً
                    5. 🚨 ابحث بعناية فائقة في تاريخ المحادثة (آخر 10 رسائل) عن أي ذكر لأسماء المدن (في سياق تحديد الموقع)
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
                    - مثال: "أريد مياه راين الموقع المدينة" = يحتوي على العلامة التجارية (راين) والمدينة (المدينة المنورة) - لأن "الموقع المدينة" يعني تحديد موقع
                    - مثال: "أبغى أكوافينا في الرياض" = يحتوي على العلامة التجارية (أكوافينا) والمدينة (الرياض)
                    - مثال خاطئ: "أريد مياه راين أي مدينة؟" = هذا سؤال عن المدينة، ليس تحديد موقع - لا تفسر "مدينة" هنا كـ "المدينة المنورة"
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
                    - "أريد مياه راين الموقع المدينة" → اعرض منتجات راين في المدينة المنورة مباشرة (لأن "الموقع المدينة" = تحديد موقع)
                    - "أبغى [أي علامة تجارية] في المدينة" → اعرض منتجات هذة العلامة التجارية في المدينة المنورة (لأن "في المدينة" = تحديد موقع)
                    - ❌ "أريد مياه راين أي مدينة؟" → اسأل عن المدينة (لأن "أي مدينة" = سؤال وليس تحديد موقع)
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
                    
                    🚨 منع افتراض المدن - مهم جداً:
                    - لا تفترض أبداً أي مدينة لأي علامة تجارية
                    - إذا ذكر العميل اسم علامة تجارية فقط (مثل "مياه المنهل" أو "نستله") بدون مدينة:
                      → اسأل دائماً "أي مدينة أنت فيها؟"
                      → لا تستدعي أي وظائف بحث بدون ذكر صريح للمدينة
                      → لا تفترض "المدينة المنورة" أو أي مدينة أخرى
                    - استدعي وظائف البحث فقط عندما تملك معلومات صريحة عن المدينة من:
                      → رسالة العميل الحالية
                      → تاريخ المحادثة
                      → السياق المقدم من النظام
                    - مثال: "مياه المنهل" → اسأل عن المدينة، لا تفترض المدينة المنورة
                    - مثال: "مياه المنهل الرياض" → استخدم الرياض كما هو محدد
                    
                    🚨 توضيح مهم للأسعار:
                    - لمنتجات الكراتين/الزجاجات: جميع الأسعار المعروضة هي أسعار الكراتين وليس الزجاجة الواحدة. وضح ذلك بإضافة "(سعر الكرتونة)" باللغة العربية أو "(carton price)" بالإنجليزية.
                    - لمنتجات الجوالين: الأسعار هي للجالون الواحد. لا تضيف "(سعر الكرتونة)" للجوالين.
                    
                   

                    طلبات الطلب - التوجيه للتطبيق:
                    عندما يريد العميل تقديم طلب، أو الشراء، أو يسأل كيف يطلب، وجهه دائماً للتطبيق/الموقع بهذه الرسالة:
                    "بتحصل الاصناف والاسعار في التطبيق وهذا هو الرابط https://onelink.to/abar_app https://abar.app/en/store/ وايضا عن طريق الموقع الالكتروني"
                    - لا تحاول أخذ طلبات من خلال المحادثة أبداً
                    - لا تسأل عن تفاصيل التوصيل أو معلومات الدفع أو المعلومات الشخصية
                    - وجههم دائماً للتطبيق/الموقع الرسمي للطلب
                    
                    الأسعار الإجمالية وحسابات الطلبات - التوجيه للتطبيق:
                    عندما يسأل العميل عن:
                    - الأسعار الإجمالية أو قوائم الأسعار ("الأسعار"، "قائمة الأسعار"، "جميع الأسعار"، "كل الأسعار")
                    - حساب إجمالي الطلبات ("10 كرتون نوڤا، كم المجموع؟"، "المجموع"، "الإجمالي"، "مجموع السعر")
                    - استفسارات أسعار عامة لعدة عناصر أو كميات
                    وجهه دائماً للتطبيق بهذه الرسالة:
                    "بتحصل الاصناف والاسعار في التطبيق وهذا هو الرابط https://onelink.to/abar_app https://abar.app/en/store/ وايضا عن طريق الموقع الالكتروني"

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

                    كن مساعد ومتفهم ورد تماماً مثل موظف ودود حقيقي.
                    
                    ⚠️ ملاحظات مهمة:
                    - "صفا مكة" أو "صفا مكه" هي اسم علامة تجارية للمياه وليست مدينة مكة المكرمة
                    - عند رؤية "صفا مكة" اعتبرها اسم علامة تجارية وليس إشارة إلى مدينة مكة
                    - لا تخلط بين علامة "صفا مكة" التجارية وطلبات عن مدينة مكة المكرمة
                    - "حلوة أو حلوه" و "هنا" هما علامات تجارية للمياه وليست كلمات عادية
                    - عند رؤية "حلوة" أو "هنا" اعتبرهما أسماء علامات تجارية
"""
                }
            # Check user message and conversation history for size-related keywords
            all_conversation_text = user_message
            if conversation_history:
                for msg in conversation_history[-7:]:  # Check last 7 messages
                    all_conversation_text += " " + msg.get("content", "")
            
            # if "ربع" in all_conversation_text or "نص" in all_conversation_text or "ريال" in all_conversation_text or "ريالين" in all_conversation_text:
            #     system_message["content"] = system_message["content"] + "\n\nمعلومات اضافية: ابو ربع هي المياه بحجم ٢٠٠ مل او ٢٥٠ مل ابو نص هي المياه بحجم  ٣٣٠ او ٣٠٠ مل ابو ريال  هي المياه بحجم  ٦٠٠ مل  او ٥٥٠ مل ابو ريالين هي المياه بحجم  ١.٥ لتر"
            
            if "ابار" in all_conversation_text or "جوفية" in all_conversation_text:
                system_message["content"] += (
                    "\n\nمعلومات إضافية: الآبار الجوفية هي المياه الجوفية المعدنية التي تُستخرج من الأرض وتحتوي على معادن ومواد طبيعية مختلفة."
                    "\n\nوهذه هي العلامات التجارية التي تُعد من منتجات الآبار الجوفية:\n"
                    "نوفا، نقي، بيرين، موارد، بي، فيو، مايلز، أكويا، أكوا 8، مانا، تانيا، آبار حائل، أوسكا، نستله، آفا، هنا، سقيا المدينة، ديمان، هني، صحتك، حلوة، عذب، أوس، قطاف، رست، إيفال، وي."
                )

            messages.append(system_message)
            
            # Add conversation history if provided (use last 7 messages to keep context manageable)
            if conversation_history:
                # Filter and add recent conversation history
                recent_history = conversation_history[-7:]  # Last 7 messages for better context
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
                            return (error_msg, city_context, brand_context)
                        
                        logger.info(f"Calling function #{function_call_count}: {function_name} with args: {function_args}")
                        print(f"⚙️ Function Call #{function_call_count}: {function_name}({function_args})")
                        
                        # Call the requested function
                        if function_name in self.available_functions:
                            try:
                                # Record function call start time for duration measurement
                                func_start_time = time.time()
                                
                                # Automatically add user_language parameter for language-aware functions
                                if function_name in ["get_brands_by_city_name", "get_products_by_brand_and_city_name", "get_all_cities"]:
                                    function_args["user_language"] = user_language
                                    logger.info(f"Added user_language='{user_language}' to {function_name}")
                                
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
                                print(f"✅ Function Response: {function_name} → {type(function_result).__name__} (success: {function_result.get('success', 'N/A') if isinstance(function_result, dict) else 'N/A'})")
                                
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
                            return (error_msg, city_context, brand_context)
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
                            
                            return (final_response, city_context, brand_context)
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
                            
                            return (error_msg, city_context, brand_context)
                
                except Exception as api_error:
                    logger.error(f"OpenAI API error: {str(api_error)}")
                    # Return error message instead of fallback
                    error_msg = "عذراً، حدث خطأ في الخدمة. الرجاء المحاولة مرة أخرى." if user_language == 'ar' else "Sorry, there was a service error. Please try again."
                    return (error_msg, city_context, brand_context)
            
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
                    
                    return (response_text, city_context, brand_context)
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
                    
                    return (max_calls_msg, city_context, brand_context)
                    
            except Exception as e:
                logger.error(f"Final response generation failed: {str(e)}")
                error_msg = "عذراً، حدث خطأ في توليد الرد. الرجاء المحاولة مرة أخرى." if user_language == 'ar' else "Sorry, there was an error generating the response. Please try again."
                return (error_msg, city_context, brand_context)

        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            error_msg = "عذراً، حدث خطأ في معالجة الاستعلام. الرجاء المحاولة مرة أخرى." if user_language == 'ar' else "Sorry, there was an error processing the query. Please try again."
            return (error_msg, None, None)

# Singleton instance
query_agent = QueryAgent() 
