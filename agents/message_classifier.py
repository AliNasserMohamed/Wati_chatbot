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

# Configure APIs
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))  # Only for audio
openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
        أنت مساعد متخصص في تصنيف الرسائل.
        صنف الرسالة إلى واحدة من الفئات التالية:
        - طلب خدمة
        - استفسار
        - شكوى
        - اقتراح أو ملاحظة
        - تحية أو رسائل عامة
        - رد على قالب (إذا كانت الرسالة رداً على رسالة قالب من الواتس اب)
        - أخرى (للرسائل التي لا تنتمي لأي فئة من الفئات المذكورة)

        مهم: استخدم سياق المحادثة السابقة لفهم الرسالة بشكل أفضل.
        إذا كانت الرسالة رداً على سؤال سابق، صنفها حسب السياق الكامل.
        
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
            classification_prompt = f"""سياق المحادثة:
{full_context}

صنف الرسالة الأخيرة من المستخدم مع مراعاة سياق المحادثة السابقة."""
            
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
                'تحية أو رسائل عامة': MessageType.GREETING,
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
        else:
            return responses['UNKNOWN']

message_classifier = MessageClassifier() 