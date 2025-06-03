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

    async def classify_message(self, text: str, db: Session, user_message: UserMessage) -> Tuple[MessageType, str]:
        """Classify the message into one of the predefined types and detect language."""
        # Detect language using static method
        language = language_handler.detect_language(text)
        user_message.language = language

        # Create classification prompt in Arabic
        system_prompt = """
        أنت مساعد متخصص في تصنيف الرسائل.
        صنف الرسالة إلى واحدة من الفئات التالية:
        - طلب خدمة
        - استفسار
        - شكوى
        - اقتراح أو ملاحظة
        - تحية أو رسائل عامة

        اكتب فقط اسم الفئة بدون أي إضافات.
        """

        # If message is in English, translate it first
        if language == 'en':
            text_to_classify = await language_handler.translate_to_arabic(text)
            # If translation fails, use original text
            if not text_to_classify:
                text_to_classify = text
        else:
            text_to_classify = text

        classification = await language_handler.process_with_openai(
            f"صنف الرسالة التالية:\n{text_to_classify}",
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
                'طلب خدمة': 'SERVICE_REQUEST',
                'استفسار': 'INQUIRY',
                'شكوى': 'COMPLAINT',
                'اقتراح أو ملاحظة': 'SUGGESTION',
                'تحية أو رسائل عامة': 'GREETING'
            }
            
            # Safely strip whitespace
            classification_clean = classification.strip() if classification else ""
            enum_value = classification_map.get(classification_clean)
            
            if not enum_value:
                print(f"Invalid classification received: '{classification}' -> '{classification_clean}'")
                user_message.message_type = None
                return None, language

            message_type = MessageType(enum_value)
            user_message.message_type = message_type

            # Handle special cases
            if message_type == MessageType.COMPLAINT:
                complaint = Complaint(
                    user_id=user_message.user_id,
                    message_id=user_message.id,
                    content=text
                )
                db.add(complaint)
            
            elif message_type == MessageType.SUGGESTION:
                suggestion = Suggestion(
                    user_id=user_message.user_id,
                    message_id=user_message.id,
                    content=text
                )
                db.add(suggestion)

            db.commit()
            return message_type, language

        except (ValueError, AttributeError) as e:
            print(f"Error processing classification '{classification}': {str(e)}")
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