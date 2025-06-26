import os
import openai
from typing import Optional, Dict, Any, Tuple
from vectorstore.chroma_db import chroma_manager
from utils.language_utils import language_handler

class EmbeddingAgent:
    def __init__(self):
        self.openai_client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.similarity_threshold = 0.15  # Lower distance means higher similarity
        self.high_similarity_threshold = 0.08  # Very high similarity threshold
        
    async def process_message(self, user_message: str, conversation_history: list = None, user_language: str = 'ar') -> Dict[str, Any]:
        """
        Process incoming message by comparing to knowledge base using embeddings
        
        Returns:
        - action: 'reply', 'skip', or 'continue_to_classification'
        - response: the response text if action is 'reply'
        - confidence: confidence score
        - matched_question: the matched question from database
        """
        
        print(f"🔍 EmbeddingAgent: Processing message: '{user_message[:50]}...'")
        
        # Search for similar questions in the knowledge base
        search_results = chroma_manager.search(user_message, n_results=3)
        
        if not search_results:
            print(f"📭 EmbeddingAgent: No knowledge base matches found")
            return {
                'action': 'continue_to_classification',
                'response': None,
                'confidence': 0,
                'matched_question': None
            }
        
        # Get the best match (lowest distance = highest similarity)
        best_match = search_results[0]
        similarity_distance = best_match.get('distance', 1.0)
        
        print(f"🎯 EmbeddingAgent: Best match found:")
        print(f"   - Question: {best_match['document'][:50]}...")
        print(f"   - Distance: {similarity_distance:.4f}")
        print(f"   - Metadata: {best_match['metadata']}")
        
        # Check if similarity is good enough
        if similarity_distance > self.similarity_threshold:
            print(f"❌ EmbeddingAgent: Similarity too low ({similarity_distance:.4f} > {self.similarity_threshold})")
            return {
                'action': 'continue_to_classification',
                'response': None,
                'confidence': 0,
                'matched_question': None
            }
        
        # Get the corresponding answer
        matched_document = best_match['document']
        metadata = best_match['metadata']
        
        # If the matched document is a question, find its answer
        if metadata.get('type') == 'question':
            answer_id = metadata.get('answer_id')
            if answer_id:
                # Search for the answer by ID
                answer_results = chroma_manager.collection.get(ids=[answer_id])
                if answer_results and answer_results['documents']:
                    matched_answer = answer_results['documents'][0]
                else:
                    matched_answer = matched_document  # Fallback
            else:
                matched_answer = matched_document  # Fallback
        else:
            # The matched document is already an answer
            matched_answer = matched_document
        
        print(f"📝 EmbeddingAgent: Found answer: '{matched_answer[:50]}...'")
        
        # Check if the answer is empty or too short (likely needs no reply)
        if not matched_answer or matched_answer.strip() == "" or len(matched_answer.strip()) < 3:
            print(f"🚫 EmbeddingAgent: Empty or very short answer - no reply needed")
            return {
                'action': 'skip',
                'response': None,
                'confidence': 1.0 - similarity_distance,
                'matched_question': matched_document
            }
        
        # For very high similarity, skip the ChatGPT evaluation
        if similarity_distance <= self.high_similarity_threshold:
            print(f"✅ EmbeddingAgent: Very high similarity ({similarity_distance:.4f}) - using answer directly")
            return {
                'action': 'reply',
                'response': matched_answer,
                'confidence': 1.0 - similarity_distance,
                'matched_question': matched_document
            }
        
        # Ask ChatGPT to evaluate if the response is appropriate
        evaluation_result = await self._evaluate_response_with_chatgpt(
            user_message, matched_document, matched_answer, user_language
        )
        
        print(f"🤖 EmbeddingAgent: ChatGPT evaluation: {evaluation_result}")
        
        if evaluation_result['action'] == 'reply':
            return {
                'action': 'reply',
                'response': evaluation_result.get('response', matched_answer),
                'confidence': 1.0 - similarity_distance,
                'matched_question': matched_document
            }
        elif evaluation_result['action'] == 'skip':
            return {
                'action': 'skip',
                'response': None,
                'confidence': 1.0 - similarity_distance,
                'matched_question': matched_document
            }
        else:
            return {
                'action': 'continue_to_classification',
                'response': None,
                'confidence': 1.0 - similarity_distance,
                'matched_question': matched_document
            }
    
    async def _evaluate_response_with_chatgpt(self, user_message: str, matched_question: str, 
                                            matched_answer: str, language: str) -> Dict[str, Any]:
        """
        Ask ChatGPT to evaluate if the response is good and appropriate
        """
        
        if language == 'ar':
            evaluation_prompt = f"""أنت مقيم ذكي لجودة الردود في خدمة العملاء لشركة أبار لتوصيل المياه.

سأعطيك:
1. رسالة العميل الحالية
2. سؤال مشابه من قاعدة البيانات
3. الرد المحفوظ في قاعدة البيانات

مهمتك تقييم ما إذا كان الرد المحفوظ مناسب للرسالة الحالية أم لا.

رسالة العميل: "{user_message}"
السؤال المشابه من قاعدة البيانات: "{matched_question}"
الرد المحفوظ: "{matched_answer}"

قم بالتقييم واختر إحدى الخيارات التالية:

1. "reply" - إذا كان الرد مناسب ومفيد ويجيب على سؤال العميل
2. "skip" - إذا كانت رسالة العميل لا تحتاج رد (مثل المشاعر، "أوكي", "شكراً", "تمام")
3. "continue" - إذا كان الرد غير مناسب أو الرسالة تحتاج معالجة أكثر تعقيداً

اكتب فقط الكلمة: reply أو skip أو continue"""
        else:
            evaluation_prompt = f"""You are a smart response quality evaluator for Abar water delivery customer service.

I will give you:
1. Current customer message
2. Similar question from database
3. Stored response from database

Your task is to evaluate whether the stored response is appropriate for the current message.

Customer message: "{user_message}"
Similar question from database: "{matched_question}"
Stored response: "{matched_answer}"

Evaluate and choose one of the following options:

1. "reply" - if the response is appropriate, helpful and answers the customer's question
2. "skip" - if the customer message doesn't need a reply (like emotions, "ok", "thanks", "fine")
3. "continue" - if the response is not appropriate or the message needs more complex processing

Write only the word: reply or skip or continue"""
        
        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "user", "content": evaluation_prompt}
                ],
                max_tokens=10,
                temperature=0.1
            )
            
            evaluation = response.choices[0].message.content.strip().lower()
            
            # Map the response to our action format
            if 'reply' in evaluation:
                return {'action': 'reply'}
            elif 'skip' in evaluation:
                return {'action': 'skip'}
            elif 'continue' in evaluation:
                return {'action': 'continue'}
            else:
                # Default to continue if we can't parse the response
                return {'action': 'continue'}
                
        except Exception as e:
            print(f"❌ EmbeddingAgent: Error evaluating response with ChatGPT: {str(e)}")
            # Default to continue on error
            return {'action': 'continue'}

# Create and export the instance
embedding_agent = EmbeddingAgent() 