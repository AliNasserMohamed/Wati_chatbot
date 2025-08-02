#!/usr/bin/env python3
"""
Configuration file for Query Agent
Contains all hardcoded data that was previously embedded in the main agent
"""

# Size terms and their descriptions
SIZE_TERMS = {
    "ابو ربع": "200-250 مل",
    "ابو نص": "300-330 مل", 
    "ابو ريال": "550-600 مل",
    "ابو ريالين": "1.5 لتر"
}

# Size keywords to detect in messages
SIZE_KEYWORDS = ["ربع", "نص", "ريال", "ريالين"]

# Response words for yes/no detection
YES_WORDS = ["نعم", "أي", "أيوة", "اي", "yes", "yeah", "yep", "sure", "ok", "okay"]

# Price inquiry keywords
PRICE_KEYWORDS = [
    "الأسعار", "قائمة الأسعار", "كم الأسعار", "ايش الأسعار",  
    "أسعاركم", "جميع الأسعار", "كل الأسعار", "الاسعار كلها",
    "prices", "price list", "all prices", "total prices", "price menu"
]

# Underground water brands
UNDERGROUND_BRANDS = [
    "نوفا", "نقي", "بيرين", "موارد", "بي", "فيو", "مايلز", "أكويا", 
    "أكوا 8", "مانا", "تانيا", "آبار حائل", "أوسكا", "نستله", "آفا", 
    "هنا", "سقيا المدينة", "ديمان", "هني", "صحتك", "حلوة", "عذب", 
    "أوس", "قطاف", "رست", "إيفال", "وي"
]

# Gallon exchange services
GALLON_EXCHANGE = {
    "تانيا": ["الرياض"],
    "صافية": ["الرياض"], 
    "ينابيع المحبوبة": ["المدينة المنورة"]
}

# Keywords for underground water detection
UNDERGROUND_KEYWORDS = ["ابار", "جوفية"]

# Keywords for gallon detection  
GALLON_KEYWORDS = ["جوالين", "جالون"]

# Classification prompt templates
CLASSIFICATION_PROMPTS = {
    "ar": """أنت مصنف رسائل لشركة توصيل المياه. حدد إذا كانت الرسالة متعلقة بخدماتنا.

متعلقة بالخدمة:
✅ أسئلة عن المدن والعلامات التجارية والمنتجات والأسعار
✅ طلبات الطلب أو الشراء
✅ ذكر العلامات التجارية أو الرد بـ "نعم"

غير متعلقة:
❌ التحيات والشكر
❌ مشاكل التوصيل والشكاوي
❌ مواضيع عامة غير متعلقة بالمياه

أجب بـ "relevant" أو "not_relevant".""",

    "en": """You are a message classifier for a water delivery company. Determine if the message is service-related.

Service-related:
✅ Questions about cities, brands, products, and prices
✅ Order requests or purchase inquiries
✅ Brand mentions or "yes" replies

Not service-related:
❌ Greetings and thanks
❌ Delivery problems and complaints  
❌ General non-water topics

Reply with "relevant" or "not_relevant"."""
}

# System message templates
SYSTEM_MESSAGES = {
    "ar": """أنت موظف خدمة عملاء في شركة أبار لتوصيل المياه في السعودية.

مهامك:
1. مساعدة العملاء في العثور على المدن المتاحة
2. عرض العلامات التجارية والمنتجات 
3. الإجابة على أسئلة الأسعار
4. توجيه طلبات الطلب للتطبيق

أسلوب التواصل:
- كن طبيعي وودود كموظف حقيقي
- لا تذكر أنك ذكاء اصطناعي
- اتبع التسلسل: مدينة → علامة تجارية → منتجات

للطلبات: وجه للتطبيق: https://onelink.to/abar_app""",

    "en": """You are a customer service employee at Abar Water Delivery Company in Saudi Arabia.

Your tasks:
1. Help customers find available cities
2. Show brands and products
3. Answer price questions  
4. Direct orders to the app

Communication style:
- Be natural and friendly like a real employee
- Don't mention you're AI
- Follow sequence: city → brand → products

For orders: Direct to app: https://onelink.to/abar_app"""
}

# Function definitions (simplified)
FUNCTION_DEFINITIONS = [
    {
        "name": "get_all_cities",
        "description": "Get all cities we serve",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_city_id_by_name", 
        "description": "Get city ID from name",
        "parameters": {
            "type": "object",
            "properties": {"city_name": {"type": "string", "description": "City name"}},
            "required": ["city_name"]
        }
    },
    {
        "name": "get_brands_by_city",
        "description": "Get brands available in city", 
        "parameters": {
            "type": "object",
            "properties": {"city_id": {"type": "integer", "description": "City ID"}},
            "required": ["city_id"]
        }
    },
    {
        "name": "get_products_by_brand",
        "description": "Get products from brand",
        "parameters": {
            "type": "object", 
            "properties": {"brand_id": {"type": "integer", "description": "Brand ID"}},
            "required": ["brand_id"]
        }
    },
    {
        "name": "search_cities",
        "description": "Search cities by name",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search term"}},
            "required": ["query"]
        }
    },
    {
        "name": "check_city_availability", 
        "description": "Check brand/product availability in city",
        "parameters": {
            "type": "object",
            "properties": {
                "city_name": {"type": "string", "description": "City name"},
                "item_type": {"type": "string", "enum": ["brand", "product"]},
                "item_name": {"type": "string", "description": "Brand or product name"}
            },
            "required": ["city_name", "item_type", "item_name"]
        }
    }
] 