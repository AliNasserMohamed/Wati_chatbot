import os
import json
from pathlib import Path
import openai
import google.generativeai as genai  # Only for audio
from database.db_models import MessageType, Complaint, Suggestion, UserMessage
from sqlalchemy.orm import Session
import base64
from utils.language_utils import language_handler
from typing import Tuple
import re

# Configure APIs
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))  # Only for audio
openai_client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))  # Changed to AsyncOpenAI

class MessageClassifier:
    def __init__(self):
        self.audio_model = genai.GenerativeModel('gemini-1.5-flash-002')  # Only for audio
        
    async def process_audio(self, audio_data: bytes) -> str:
        """Convert audio to text using Gemini."""
        try:
            # Convert audio bytes to base64
            audio_b64 = base64.b64encode(audio_data).decode('utf-8')
            
            # Call Gemini model for audio transcription
            response = await self.audio_model.generate_content({
                "audio": {"data": audio_b64}
            })
            
            return response.text
        except Exception as e:
            print(f"Error transcribing audio: {str(e)}")
            return None

    async def classify_message(self, text: str, db: Session, user_message: UserMessage, conversation_history: list = None) -> Tuple[MessageType, str]:
        """Classify the message into one of the predefined types and detect language."""
        # Detect language using static method
        language = language_handler.detect_language(text)
        user_message.language = language

        # Build context-aware classification prompt
        system_prompt = """
        أنت مساعد ذكي متخصص في تصنيف رسائل العملاء لشركة توصيل المياه في السعودية.

        معلومات عن الشركة:
        - نحن شركة توصيل مياه في السعودية (أبار)
        - نقدم خدمات توصيل المياه لمختلف المدن
        - لدينا عدة علامات تجارية ومنتجات مياه
        - نتلقى رسائل من العملاء عبر الواتس اب
        - نحتاج لتصنيف هذه الرسائل لتوجيهها للقسم المناسب

        أهداف التصنيف:
        1. توجيه الاستفسارات والشكاوى للفرق المختصة
        2. معالجة طلبات الخدمة بسرعة
        3. الرد على التحيات والرسائل العامة تلقائياً
        4. تحديد الردود على الرسائل التفاعلية (القوالب)

        أنواع الرسائل المطلوب تصنيفها:
        - طلب خدمة: طلبات توصيل مياه، طلبات جديدة، استفسارات عن الخدمة
        - استفسار: أسئلة عن المدن، الأسعار، العلامات التجارية، 
        - شكوى: مشاكل في الخدمة، تأخير التوصيل، جودة المياه
        - اقتراح أو ملاحظة: اقتراحات للتحسين، ملاحظات إيجابية، آراء
        - تحية: السلام عليكم، مرحبا، هلا، صباح الخير، مساء الخير فقط
        - شكر: شكراً، مشكور، يعطيك العافية، الله يعطيك العافية، تسلم
        - رد على قالب: ردود على رسائل تفاعلية، أزرار اختيار، قوائم، رسائل نظام الواتس اب
        - أخرى: رسائل عامة، استفسارات غير محددة، رسائل خارج نطاق العمل

        ملاحظات مهمة عن "رد على قالب":
        - رسائل الواتس اب التفاعلية (quick replies, buttons, lists)
        - ردود على رسائل النظام الآلية
        - اختيارات من قائمة أو أزرار
        - أرقام أو نصوص مختصرة كردود على خيارات
        - رسائل الرضا والشكر مثل "راضي تماماً"، "شكراً"، "ممتاز"
        - ردود تقييم الخدمة أو التأكيد

        مهم جداً:
        1. "تحية" فقط للتحيات المباشرة الواضحة
        2. الرسائل العامة أو غير المحددة تصنف كـ "أخرى"
        3. إذا كانت الرسالة غير مترابطة مع سياق المحادثة، صنفها حسب محتواها المستقل
        4. ركز على تحديد الردود على القوالب التفاعلية بدقة
        
        اكتب فقط اسم الفئة بدون أي إضافات.
        """

        # Build the complete message with context
        if conversation_history and len(conversation_history) > 0:
            # Get last 3 messages for context (to avoid too much context)
            recent_history = conversation_history[-3:] if len(conversation_history) > 3 else conversation_history
            context_lines = []
            
            for msg in recent_history:
                if msg.get("raw_content"):  # Use raw content for classification
                    context_lines.append(msg["content"])  # This includes "user:" or "bot:" prefix
            
            # Add current message
            current_message_formatted = f"user: {text}"
            context_lines.append(current_message_formatted)
            
            # Build full context
            full_context = "\n".join(context_lines)
            
            # Enhanced prompt for context-aware classification
            classification_prompt = f"""سياق المحادثة:
{full_context}

تعليمات التصنيف للشركة:
1. إذا كانت الرسالة الأخيرة مترابطة مع سياق المحادثة، صنفها حسب السياق الكامل
2. إذا كانت الرسالة الأخيرة غير مترابطة مع المحادثة (موضوع جديد تماماً)، صنفها بناءً على محتواها المستقل
3. إذا كانت رداً على رسالة قالب أو تفاعلية من البوت، صنفها كـ "رد على قالب"
4. ابحث عن مؤشرات الردود على القوالب: أرقام منفردة، كلمات مختصرة، اختيارات من قائمة
5. رسائل الرضا والشكر مثل "راضي تماماً"، "شكراً"، "ممتاز" تعتبر "رد على قالب"
6. الرسائل العامة أو غير المحددة تصنف كـ "أخرى"
7. "تحية" فقط للتحيات المباشرة الواضحة

صنف الرسالة الأخيرة من المستخدم:"""
            
            print(f"🔄 Using conversation context for classification:")
            print(f"📝 Context: {full_context[:150]}...")
        else:
            # If message is in English, translate it first
            if language == 'en':
                text_to_classify = await language_handler.translate_to_arabic(text)
                # If translation fails, use original text
                if not text_to_classify:
                    text_to_classify = text
            else:
                text_to_classify = text
            
            classification_prompt = f"صنف الرسالة التالية:\n{text_to_classify}"
            print(f"📝 Classifying without context: {text[:50]}...")

        classification = await language_handler.process_with_openai(
            classification_prompt,
            system_prompt
        )

        # Check if classification is None or empty
        if not classification:
            print("Classification failed - using default UNKNOWN type")
            user_message.message_type = None
            return None, language

        try:
            # Map Arabic classification to English enum values
            classification_map = {
                'طلب خدمة': MessageType.SERVICE_REQUEST,
                'استفسار': MessageType.INQUIRY,
                'شكوى': MessageType.COMPLAINT,
                'اقتراح أو ملاحظة': MessageType.SUGGESTION,
                'تحية': MessageType.GREETING,
                'شكر': MessageType.THANKING,
                'رد على قالب': MessageType.TEMPLATE_REPLY,
                'أخرى': MessageType.OTHERS
            }
            
            # Safely strip whitespace
            classification_clean = classification.strip() if classification else ""
            print(f"🔍 Classification received: '{classification}' -> '{classification_clean}'")
            
            # Get the MessageType enum directly
            message_type = classification_map.get(classification_clean)
            
            if not message_type:
                print(f"❌ Invalid classification received: '{classification_clean}'")
                print(f"📋 Available classifications: {list(classification_map.keys())}")
                user_message.message_type = None
                return None, language

            print(f"✅ Mapped to MessageType: {message_type}")
            user_message.message_type = message_type

            # Handle special cases
            if message_type == MessageType.COMPLAINT:
                complaint = Complaint(
                    user_id=user_message.user_id,
                    message_id=user_message.id,
                    content=text
                )
                db.add(complaint)
                print("📝 Created complaint record")
            
            elif message_type == MessageType.SUGGESTION:
                suggestion = Suggestion(
                    user_id=user_message.user_id,
                    message_id=user_message.id,
                    content=text
                )
                db.add(suggestion)
                print("📝 Created suggestion record")

            db.commit()
            return message_type, language

        except (ValueError, AttributeError) as e:
            print(f"❌ Error processing classification '{classification}': {str(e)}")
            user_message.message_type = None
            return None, language

    def get_default_response(self, message_type: MessageType, language: str) -> str:
        """Get default response based on message type and language."""
        responses = language_handler.get_default_responses(language)
        
        if message_type == MessageType.COMPLAINT:
            return responses['COMPLAINT']
        elif message_type == MessageType.SUGGESTION:
            return responses['SUGGESTION']
        elif message_type == MessageType.GREETING:
            return responses['GREETING']
        elif message_type == MessageType.THANKING:
            return responses['THANKING']
        else:
            return responses['UNKNOWN']

message_classifier = MessageClassifier() 