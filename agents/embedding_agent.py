import os
import openai
from typing import Optional, Dict, Any, Tuple
from vectorstore.chroma_db import chroma_manager
from utils.language_utils import language_handler

class EmbeddingAgent:
    def __init__(self):
        self.openai_client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.similarity_threshold = 0.50  # Higher cosine similarity means better match
        self.high_similarity_threshold = 0.60  # Very high similarity threshold for direct answers
        
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
        
        # Detect the actual language of the user message
        detected_user_language = language_handler.detect_language(user_message)
        print(f"🌐 EmbeddingAgent: User message language detected as: {detected_user_language}")
        
        # Search for similar questions in the knowledge base
        search_results = await chroma_manager.search(user_message, n_results=3)
        
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
        
        # Get the best match (highest similarity)
        best_match = search_results[0]
        similarity_score = best_match.get('similarity', 0.0)  # Use 'similarity' not 'cosine_similarity'
        
        print(f"🎯 EmbeddingAgent: Best match selected:")
        print(f"   - Question: {best_match['document'][:50]}...")
        print(f"   - Similarity: {similarity_score:.4f}")
        print(f"   - Metadata: {best_match['metadata']}")
        
        # Check if similarity is good enough (higher is better)
        if similarity_score < self.similarity_threshold:
            print(f"❌ EmbeddingAgent: Similarity too low ({similarity_score:.4f} < {self.similarity_threshold})")
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
                answer_results = chroma_manager.get_collection_safe().get(ids=[answer_id])
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
                'confidence': similarity_score,
                'matched_question': matched_document
            }
        
        # For very high similarity, skip the ChatGPT evaluation
        if similarity_score >= self.high_similarity_threshold:
            print(f"✅ EmbeddingAgent: Very high similarity ({similarity_score:.4f}) - using answer directly")
            return {
                'action': 'reply',
                'response': matched_answer,
                'confidence': similarity_score,
                'matched_question': matched_document
            }
        
        # Ask ChatGPT to evaluate if the response is appropriate
        evaluation_result = await self._evaluate_response_with_chatgpt(
            user_message, matched_document, matched_answer, detected_user_language, conversation_history
        )
        
        print(f"🤖 EmbeddingAgent: ChatGPT evaluation: {evaluation_result}")
        
        if evaluation_result['action'] == 'reply':
            return {
                'action': 'reply',
                'response': evaluation_result.get('response', matched_answer),
                'confidence': similarity_score,
                'matched_question': matched_document
            }
        elif evaluation_result['action'] == 'skip':
            return {
                'action': 'skip',
                'response': None,
                'confidence': similarity_score,
                'matched_question': matched_document
            }
        else:
            return {
                'action': 'continue_to_classification',
                'response': None,
                'confidence': similarity_score,
                'matched_question': matched_document
            }
    
    async def _evaluate_response_with_chatgpt(self, user_message: str, matched_question: str, 
                                            matched_answer: str, language: str, conversation_history: list = None) -> Dict[str, Any]:
        """
        Ask ChatGPT to evaluate if the response is good and appropriate
        """
        
        # First check if the user message and matched answer are in the same language
        user_language = language_handler.detect_language(user_message)
        answer_language = language_handler.detect_language(matched_answer)
        
        # If languages don't match, skip the response
        if user_language != answer_language:
            print(f"🌐 Language mismatch: user={user_language}, answer={answer_language} - skipping response")
            return {'action': 'skip'}
        
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
            evaluation_prompt = f"""أنت مقيم صارم جداً لجودة الردود في خدمة العملاء لشركة أبار لتوصيل المياه. 

مهمتك الوحيدة: تحديد إذا كانت رسالة العميل تحية أو شكر حقيقي فقط.

- رسالة العميل الحالية: "{user_message}"
- السؤال المشابه من قاعدة البيانات: "{matched_question}"
- الرد المحفوظ: "{matched_answer}"
{conversation_context}

قواعد صارمة:
- "reply": فقط للتحيات الحقيقية البسيطة: (السلام عليكم، مرحبا، أهلا، مساء الخير، صباح الخير)
- "reply": فقط للشكر المباشر البسيط: (شكراً، يعطيك العافية، الله يوفقكم، جزاك الله خير)
- "skip": لأي رسالة أخرى مهما كانت مؤدبة أو تحتوي على تحية

أمثلة للرسائل التي لا تُعتبر تحية أو شكر:
- "السلام عليكم، عندي استفسار" → continue (يحتوي على سؤال)
- "شكراً لك، بس عندي سؤال" → continue (يحتوي على سؤال)
- "أبي أطلب مياه" → continue (طلب خدمة)
- "ممكن تساعدني؟" → continue (طلب مساعدة)
- "كيف أقدر أطلب؟" → continue (سؤال)

إذا كانت الرسالة تحتوي على أي شيء غير التحية أو الشكر فقط، اختر "continue".

اختر واحد فقط: reply أو skip أو continue"""
        else:
            evaluation_prompt = f"""You are a very strict response quality evaluator for Abar water delivery customer service.

Your only task: Determine if the customer message is ONLY a greeting or thanks.

- Current customer message: "{user_message}"
- Similar question from database: "{matched_question}"
- Stored response: "{matched_answer}"
{conversation_context}

Strict rules:
- "reply": Only for simple genuine greetings: (Hello, Hi, Good morning, Good evening, Peace be upon you)
- "reply": Only for simple direct thanks: (Thank you, Thanks, God bless you, I appreciate it)
- "skip": For any other message no matter how polite or containing greetings

Examples of messages that are NOT greetings or thanks:
- "Hello, I have a question" → continue (contains question)
- "Thank you, but I need help" → continue (contains request)
- "I want to order water" → continue (service request)
- "Can you help me?" → continue (request for help)
- "How can I order?" → continue (question)

If the message contains anything other than ONLY greeting or thanks, choose "continue".

Choose only one: reply or skip or continue"""
        
        try:
            print(f"🤖 ChatGPT evaluation prompt: {evaluation_prompt}")
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": """
                        You are an extremely strict evaluator for customer service response quality at Abar Water Delivery.

                        Your ONLY task: Determine if the customer message is PURELY a greeting or thanks with NO additional content.

                        Rules:
                        - reply: ONLY if the message is a simple standalone greeting (e.g. السلام عليكم, مرحبا, أهلا) or simple direct thanks (e.g. شكراً, يعطيك العافية, الله يوفقكم), with ABSOLUTELY NO other content.
                        - skip: If the message needs no response (e.g. أوكي, تمام, نعم).
                        - continue: If the message includes ANY question, request, scheduling, or information — even if it starts with greetings or thanks.

                        Critical examples of messages that are NOT greetings/thanks:
                        - "السلام عليكم، عندي استفسار" → continue (contains question)
                        - "شكراً لك، بس عندي سؤال" → continue (contains question)
                        - "أبي أطلب مياه" → continue (service request)  
                        - "ممكن تساعدني؟" → continue (request for help)
                        - "كيف أقدر أطلب؟" → continue (question)
                        - "يمدي توصلونه اليوم اكون شاكر لكم" → continue (question with thanks)
                        - "ابيه الليلة" → continue (request)
                        - "موعدنا بكره باذن الله" → continue (informational statement)

                        Only pure greetings/thanks are allowed:
                        - "السلام عليكم" → reply
                        - "شكراً" → reply
                        - "يعطيك العافية" → reply
                        - "مرحبا" → reply

                        Final instruction:
                        Be extremely conservative — choose `reply` ONLY if you are 100% certain it's PURELY a greeting or thanks with NO other content.
                        
                        """},
                    {"role": "user", "content": evaluation_prompt}
                ],
                max_tokens=20,
                temperature=0.1
            )
            
            evaluation = response.choices[0].message.content.strip().lower()
            
            # Log the evaluation for debugging
            print(f"🤖 ChatGPT evaluation result: '{evaluation}'")
            
            # Map the response to our action format
            if 'reply' in evaluation:
                return {'action': 'reply'}
            elif 'skip' in evaluation:
                return {'action': 'skip'}
            elif 'continue' in evaluation:
                return {'action': 'continue'}
            else:
                # Default to continue if we can't parse the response
                print(f"⚠️ Could not parse evaluation result, defaulting to continue")
                return {'action': 'continue'}
                
        except Exception as e:
            print(f"❌ EmbeddingAgent: Error evaluating response with ChatGPT: {str(e)}")
            # Default to continue on error
            return {'action': 'continue'}

# Create and export the instance
embedding_agent = EmbeddingAgent() 