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
                'COMPLAINT': 'شكراً لتواصلك معنا بخصوص هذه الشكوى. نحن نقدر ملاحظاتك ونأخذها على محمل الجد. سيتم توجيه شكواك إلى الفريق المختص للمراجعة والمتابعة معك في أقرب وقت.',
                'SUGGESTION': 'شكراً لك على هذا الاقتراح القيم! نحن نقدر آراء عملائنا ونسعى دائماً للتحسين. سيتم مراجعة اقتراحك من قبل الفريق المختص.',
                'GREETING': 'وعليكم السلام ورحمة الله وبركاته، أهلاً وسهلاً بك! 🌟\n\nأنا مساعدك الذكي في شركة أبار لتوصيل المياه في السعودية. يمكنني مساعدتك في:\n\n💧 طلب توصيل المياه\n🏙️ معرفة المدن المتاحة\n🏷️ الاستفسار عن العلامات التجارية والأسعار\n📞 تقديم الشكاوى والاقتراحات\n\nكيف يمكنني مساعدتك اليوم؟',
                'THANKING': 'عفواً! 😊',
                'UNKNOWN': 'عذراً، لم أتمكن من فهم طلبك. يمكنك إعادة صياغة السؤال أو التواصل مع فريق الدعم.',
                'TEMPLATE_REPLY': 'تم استلام ردك على الرسالة. شكراً لك.',
                'OTHERS': 'مرحباً! شكراً لتواصلك معنا. كيف ممكن نساعدك اليوم؟',
                'CITY_FIRST': 'الرجاء اختيار المدينة اول.',
                'BRAND_FIRST': 'الرجاء اختيار الماركة اول.',
                'NO_ORDERS': 'ما عندك اي طلبات حالياً.',
                'TEAM_WILL_REPLY': 'شكراً لتواصلك معنا! تم استلام رسالتك وسيتواصل معك أحد أعضاء فريقنا قريباً.',
                'INQUIRY_TEAM_REPLY': 'شكراً لاستفسارك! سيتواصل معك فريق المبيعات للإجابة على أسئلتك وتقديم المساعدة.',
                'SERVICE_REQUEST_TEAM_REPLY': 'تم استلام طلبك! سيتواصل معك فريق خدمة العملاء لمعالجة طلبك في أقرب وقت.',
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
                'COMPLAINT': 'Thank you for contacting us regarding this complaint. We appreciate your feedback and take it seriously. Your complaint will be forwarded to the relevant team for review and follow-up.',
                'SUGGESTION': 'Thank you for this valuable suggestion! We appreciate our customers\' feedback and always strive for improvement. Your suggestion will be reviewed by the relevant team.',
                'GREETING': 'Hello and welcome! 🌟\n\nI am your smart assistant at Abar Water Delivery Company in Saudi Arabia. I can help you with:\n\n💧 Water delivery orders\n🏙️ Available cities information\n🏷️ Brands and pricing inquiries\n📞 Complaints and suggestions\n\nHow can I help you today?',
                'THANKING': 'You\'re welcome! 😊',
                'UNKNOWN': 'Sorry, I could not understand your request. Please rephrase your question or contact our support team.',
                'TEMPLATE_REPLY': 'Your reply to the message has been received. Thank you.',
                'OTHERS': 'Hello! Thank you for contacting us. How can we help you today?',
                'CITY_FIRST': "Please select a city first.",
                'BRAND_FIRST': "Please select a brand first.",
                'NO_ORDERS': "You don't have any orders yet.",
                'TEAM_WILL_REPLY': 'Thank you for contacting us! We have received your message and one of our team members will contact you soon.',
                'INQUIRY_TEAM_REPLY': 'Thank you for your inquiry! Our sales team will contact you to answer your questions and provide assistance.',
                'SERVICE_REQUEST_TEAM_REPLY': 'Your request has been received! Our customer service team will contact you to process your request as soon as possible.',
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
            
            # Enhanced system prompt to ensure natural responses
            if not system_prompt:
                system_prompt = """أنت موظف خدمة عملاء في شركة أبار لتوصيل المياه في السعودية.

قواعد مهمة:
- رد بطريقة طبيعية تماماً مثل أي موظف حقيقي
- لا تستخدم أبداً عبارات مثل "رد الذكاء الاصطناعي:" أو "رد المساعد:" أو "أنا ذكاء اصطناعي"
- ابدأ الرد مباشرة بالمحتوى
- كن ودود وطبيعي ومفيد"""
            
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
                    # Clean any potential robotic prefixes
                    cleaned_content = content.strip()
                    
                    # Remove common robotic prefixes if they appear
                    prefixes_to_remove = [
                        "رد الذكاء الاصطناعي:",
                        "رد المساعد:",
                        "الذكاء الاصطناعي:",
                        "المساعد:",
                        "AI response:",
                        "Assistant:"
                    ]
                    
                    for prefix in prefixes_to_remove:
                        if cleaned_content.startswith(prefix):
                            cleaned_content = cleaned_content[len(prefix):].strip()
                            break
                    
                    return cleaned_content
            
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