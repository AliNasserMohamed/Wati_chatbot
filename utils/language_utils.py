import openai
from typing import Dict
import re
import os

class LanguageHandler:
    def __init__(self):
        # Use AsyncOpenAI for async operations
        self.openai_client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.supported_languages = ['en', 'ar']
        self.default_language = 'ar'

    def detect_language(self, text: str) -> str:
        """Detect the language of the input text using regex patterns."""
        try:
            # Arabic Unicode ranges
            arabic_pattern = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]+')
            
            # Count Arabic characters
            arabic_chars = len(arabic_pattern.findall(text))
            
            # Count English characters
            english_pattern = re.compile(r'[a-zA-Z]+')
            english_chars = len(english_pattern.findall(text))
            
            # If more Arabic characters or equal, consider it Arabic
            if arabic_chars >= english_chars:
                return 'ar'
            return 'en'
            
        except Exception as e:
            print(f"Error detecting language: {str(e)}")
            return self.default_language

    def get_default_responses(self, language: str) -> Dict[str, str]:
        """Get default responses in the specified language."""
        responses = {
            'ar': {
                'COMPLAINT': 'آسف لسماع شكواك. فريقنا راح يراجع الشكوى ويرد عليك بأقرب وقت ممكن.',
                'SUGGESTION': 'شكراً على اقتراحك! نقدر ملاحظاتك وراح ناخذها بعين الاعتبار.',
                'GREETING': 'هلا! كيف اقدر اساعدك اليوم؟',
                'UNKNOWN': 'عذراً، ما فهمت طلبك. ممكن توضح اكثر؟',
                'TEMPLATE_REPLY': 'تم استلام ردك على الرسالة. شكراً لك.',
                'OTHERS': 'شكراً لتواصلك معنا. فريقنا راح يرد عليك بأقرب وقت ممكن.',
                'CITY_FIRST': 'الرجاء اختيار المدينة اول.',
                'BRAND_FIRST': 'الرجاء اختيار الماركة اول.',
                'NO_ORDERS': 'ما عندك اي طلبات حالياً.',
                'TEAM_WILL_REPLY': 'شكراً لتواصلك معنا. فريقنا راح يرد عليك بأقرب وقت ممكن إن شاء الله.',
                'INQUIRY_TEAM_REPLY': 'شكراً على استفسارك. فريق الدعم الفني راح يرد عليك بأقرب وقت ممكن.',
                'SERVICE_REQUEST_TEAM_REPLY': 'تم استلام طلبك. فريق خدمة العملاء راح يتواصل معك قريباً لتنسيق الخدمة.',
                'ORDER_SUCCESS': """
                ممتاز! تم انشاء طلبك بنجاح.
                رقم الطلب: {order_id}
                وقت التوصيل المتوقع: {delivery_time}
                المبلغ الاجمالي: {total_amount}
                
                تقدر تتابع حالة طلبك في اي وقت عن طريق السؤال عن طلباتك.
                """,
                'ORDER_ERROR': 'عذراً، صار خطأ اثناء انشاء طلبك. حاول مرة ثانية.',
                'MISSING_INFO': 'نحتاج المعلومات التالية لإكمال طلبك: {fields}'
            },
            'en': {
                'COMPLAINT': "We're sorry to hear about your complaint. Our team will review it and get back to you as soon as possible.",
                'SUGGESTION': "Thank you for your suggestion! We appreciate your feedback and will take it into consideration.",
                'GREETING': "Hello! How can I assist you today?",
                'UNKNOWN': "I'm not sure what you mean. Could you please clarify?",
                'TEMPLATE_REPLY': 'Your reply to the message has been received. Thank you.',
                'OTHERS': 'Thank you for contacting us. Our team will get back to you as soon as possible.',
                'CITY_FIRST': "Please select a city first.",
                'BRAND_FIRST': "Please select a brand first.",
                'NO_ORDERS': "You don't have any orders yet.",
                'TEAM_WILL_REPLY': 'Thank you for contacting us. Our team will get back to you as soon as possible.',
                'INQUIRY_TEAM_REPLY': 'Thank you for your inquiry. Our support team will respond to you as soon as possible.',
                'SERVICE_REQUEST_TEAM_REPLY': 'Your request has been received. Our customer service team will contact you shortly to coordinate the service.',
                'ORDER_SUCCESS': """
                Great! Your order has been created successfully.
                Order ID: {order_id}
                Estimated delivery time: {delivery_time}
                Total amount: {total_amount}
                
                You can check your order status anytime by asking about your orders.
                """,
                'ORDER_ERROR': "Sorry, there was an error creating your order. Please try again.",
                'MISSING_INFO': "We need the following information to complete your order: {fields}"
            }
        }
        return responses.get(language, responses['ar'])

    async def process_with_openai(self, prompt: str, system_prompt: str = None) -> str:
        """Process text with OpenAI using Saudi Arabic context."""
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = await self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=messages,
                temperature=0.7
            )
            
            # Check if response and content exist before calling strip()
            if response and response.choices and len(response.choices) > 0:
                content = response.choices[0].message.content
                if content:
                    return content.strip()
            
            print("OpenAI response was empty or invalid")
            return None
            
        except Exception as e:
            print(f"Error processing with OpenAI: {str(e)}")
            return None

    async def translate_to_arabic(self, text: str) -> str:
        """Translate English text to Saudi Arabic."""
        system_prompt = """
        أنت مترجم محترف متخصص في الترجمة إلى اللهجة السعودية.
        يجب أن تكون الترجمة:
        1. باللهجة السعودية الدارجة
        2. مناسبة للمحادثات اليومية
        3. تحافظ على المعنى الأصلي
        4. تستخدم التعابير السعودية المألوفة
        """
        
        return await self.process_with_openai(
            f"ترجم النص التالي إلى اللهجة السعودية:\n{text}",
            system_prompt
        )

    async def translate_response(self, text: str, target_language: str) -> str:
        """Translate response to target language."""
        if target_language == 'ar':
            return await self.translate_to_arabic(text)
        elif target_language == 'en':
            # If target is English, assume text is Arabic and translate to English
            system_prompt = """
            You are a professional translator specializing in translating Saudi Arabic dialect to English.
            The translation should be:
            1. Natural and fluent English
            2. Suitable for everyday conversations
            3. Maintain the original meaning
            4. Use appropriate English expressions
            """
            
            return await self.process_with_openai(
                f"Translate the following Saudi Arabic text to English:\n{text}",
                system_prompt
            )
        else:
            # Return original text if language not supported
            return text

language_handler = LanguageHandler() 