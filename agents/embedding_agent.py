import os
import openai
from typing import Optional, Dict, Any, Tuple
from vectorstore.chroma_db import chroma_manager
from utils.language_utils import language_handler

class EmbeddingAgent:
    def __init__(self):
        self.openai_client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.similarity_threshold = 0.20  # Higher cosine similarity means better match
        self.high_similarity_threshold = 0.80  # Very high similarity threshold for direct answers
        
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
        
        # Print detailed information about all search results
        print(f"📊 EmbeddingAgent: Found {len(search_results)} similar results:")
        for i, result in enumerate(search_results, 1):
            similarity_score = result.get('similarity', result.get('distance', 0.0))
            document_preview = result['document'][:100] + "..." if len(result['document']) > 100 else result['document']
            metadata = result.get('metadata', {})
            
            print(f"   Result {i}:")
            print(f"   - Similarity Score: {similarity_score:.4f}")
            print(f"   - Document Type: {metadata.get('type', 'unknown')}")
            print(f"   - Content Preview: {document_preview}")
            print(f"   - Full Metadata: {metadata}")
            print(f"   ---")
        
        # Get the best match (highest cosine similarity)
        best_match = search_results[0]
        cosine_similarity = best_match.get('cosine_similarity', 0.0)  # Default to 0 if not found
        
        print(f"🎯 EmbeddingAgent: Best match selected:")
        print(f"   - Question: {best_match['document'][:50]}...")
        print(f"   - Cosine Similarity: {cosine_similarity:.4f}")
        print(f"   - Metadata: {best_match['metadata']}")
        
        # Check if cosine similarity is good enough (higher is better)
        if cosine_similarity < self.similarity_threshold:
            print(f"❌ EmbeddingAgent: Cosine similarity too low ({cosine_similarity:.4f} < {self.similarity_threshold})")
            return {
                'action': 'continue_to_classification',
                'response': None,
                'confidence': 0,
                'matched_question': None
            }
        
        # Get the corresponding answer
        matched_document = best_match['document']
        metadata = best_match['metadata']
        
        print(f"🔍 EmbeddingAgent: Retrieving answer for matched question...")
        print(f"   - Matched Question Full Text: {matched_document}")
        
        # If the matched document is a question, find its answer
        if metadata.get('type') == 'question':
            answer_id = metadata.get('answer_id')
            print(f"   - Looking for answer with ID: {answer_id}")
            if answer_id:
                # Search for the answer by ID
                answer_results = chroma_manager.collection.get(ids=[answer_id])
                if answer_results and answer_results['documents']:
                    matched_answer = answer_results['documents'][0]
                    print(f"   - Found answer by ID: {matched_answer[:100]}...")
                else:
                    matched_answer = matched_document  # Fallback
                    print(f"   - Answer ID not found, using question as fallback")
            else:
                matched_answer = matched_document  # Fallback
                print(f"   - No answer ID provided, using question as answer")
        else:
            # The matched document is already an answer
            matched_answer = matched_document
            print(f"   - Matched document is already an answer")
        
        print(f"📝 EmbeddingAgent: Final answer retrieved:")
        print(f"   - Answer Length: {len(matched_answer)} characters")
        print(f"   - Answer Preview: '{matched_answer[:100]}...'")
        print(f"   - Answer Full Text: {matched_answer}")
        
        # Check if the answer is empty or too short (likely needs no reply)
        if not matched_answer or matched_answer.strip() == "" or len(matched_answer.strip()) < 3:
            print(f"🚫 EmbeddingAgent: Empty or very short answer - no reply needed")
            return {
                'action': 'skip',
                'response': None,
                'confidence': cosine_similarity,
                'matched_question': matched_document
            }
        
        # For very high cosine similarity, skip the ChatGPT evaluation
        if cosine_similarity >= self.high_similarity_threshold:
            print(f"✅ EmbeddingAgent: Very high cosine similarity ({cosine_similarity:.4f}) - using answer directly")
            return {
                'action': 'reply',
                'response': matched_answer,
                'confidence': cosine_similarity,
                'matched_question': matched_document
            }
        
        # Ask ChatGPT to evaluate if the response is appropriate
        evaluation_result = await self._evaluate_response_with_chatgpt(
            user_message, matched_document, matched_answer, user_language, conversation_history
        )
        
        print(f"🤖 EmbeddingAgent: ChatGPT evaluation: {evaluation_result}")
        
        if evaluation_result['action'] == 'reply':
            return {
                'action': 'reply',
                'response': evaluation_result.get('response', matched_answer),
                'confidence': cosine_similarity,
                'matched_question': matched_document
            }
        elif evaluation_result['action'] == 'skip':
            return {
                'action': 'skip',
                'response': None,
                'confidence': cosine_similarity,
                'matched_question': matched_document
            }
        else:
            return {
                'action': 'continue_to_classification',
                'response': None,
                'confidence': cosine_similarity,
                'matched_question': matched_document
            }
    
    async def _evaluate_response_with_chatgpt(self, user_message: str, matched_question: str, 
                                            matched_answer: str, language: str, conversation_history: list = None) -> Dict[str, Any]:
        """
        Ask ChatGPT to evaluate if the response is good and appropriate
        """
        
        # Format conversation history for context
        conversation_context = ""
        if conversation_history:
            # Get the latest 3 messages for context
            recent_messages = conversation_history[-3:] if len(conversation_history) >= 3 else conversation_history
            
            if language == 'ar':
                conversation_context = "\n\nسياق المحادثة (آخر 3 رسائل):\n"
                for i, msg in enumerate(recent_messages, 1):
                    role = "العميل" if msg.get('role') == 'user' else "الوكيل"
                    conversation_context += f"{i}. {role}: {msg.get('content', '')}\n"
            else:
                conversation_context = "\n\nConversation context (last 3 messages):\n"
                for i, msg in enumerate(recent_messages, 1):
                    role = "Customer" if msg.get('role') == 'user' else "Agent"
                    conversation_context += f"{i}. {role}: {msg.get('content', '')}\n"
        
        if language == 'ar':
            evaluation_prompt = f"""أنت مقيم ذكي لجودة الردود في خدمة العملاء لشركة أبار لتوصيل المياه.

سأعطيك:
1. رسالة العميل الحالية
2. سؤال مشابه من قاعدة البيانات
3. الرد المحفوظ في قاعدة البيانات
4. سياق المحادثة للرسائل السابقة{conversation_context}

رسالة العميل الحالية: "{user_message}"
السؤال المشابه من قاعدة البيانات: "{matched_question}"
الرد المحفوظ: "{matched_answer}"

مهمتك تقييم ما إذا كان الرد المحفوظ مناسب للرسالة الحالية أم لا، مع مراعاة سياق المحادثة.

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
4. Conversation context from previous messages{conversation_context}

Current customer message: "{user_message}"
Similar question from database: "{matched_question}"
Stored response: "{matched_answer}"

Your task is to evaluate whether the stored response is appropriate for the current message, considering the conversation context.

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