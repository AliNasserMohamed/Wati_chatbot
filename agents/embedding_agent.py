import os
import openai
import time
from typing import Optional, Dict, Any, Tuple
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from vectorstore.chroma_db import chroma_manager
from utils.language_utils import language_handler

# Import message journey logger for detailed logging
try:
    from utils.message_logger import message_journey_logger
    LOGGING_AVAILABLE = True
except ImportError:
    LOGGING_AVAILABLE = False
    print("⚠️ Message journey logger not available - detailed embedding logging disabled")

class EmbeddingAgent:
    def __init__(self):
        # Keep AsyncOpenAI for fallback if needed
        self.openai_client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Initialize LangChain client for better tracing
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.1,
            api_key=os.getenv("OPENAI_API_KEY"),
            tags=["embedding-agent", "abar-chatbot"]
        )
        self.similarity_threshold = 0.50  # Higher cosine similarity means better match
        
    async def process_message(self, user_message: str, conversation_history: list = None, user_language: str = 'ar', journey_id: str = None) -> Dict[str, Any]:
        """
        Process incoming message by comparing to knowledge base using embeddings
        
        Returns:
        - action: 'reply', 'skip', or 'continue_to_classification'
        - response: the response text if action is 'reply'
        - confidence: confidence score
        - matched_question: the matched question from database
        """
        
        # Detect the actual language of the user message
        detected_user_language = language_handler.detect_language(user_message)
        
        # Search for similar questions in the knowledge base
        search_results = await chroma_manager.search(user_message, n_results=3)
        
        if not search_results:
            return {
                'action': 'continue_to_classification',
                'response': None,
                'confidence': 0,
                'matched_question': None
            }
        
        # Detailed logging: capture all search results for journey logging
        search_results_for_log = []
        
        for i, result in enumerate(search_results, 1):
            similarity_score = result.get('similarity', result.get('distance', 0.0))
            document_preview = result['document'][:100] + "..." if len(result['document']) > 100 else result['document']
            metadata = result.get('metadata', {})
            
            # Capture for detailed logging
            search_results_for_log.append({
                "rank": i,
                "similarity_score": similarity_score,
                "document": result['document'],
                "document_type": metadata.get('type', 'unknown'),
                "has_answer_text": bool(metadata.get('answer_text', '').strip()),
                "has_answer": metadata.get('has_answer'),
                "metadata": metadata
            })
        
        # Log all search results to journey if logging is available
        if LOGGING_AVAILABLE and journey_id:
            message_journey_logger.add_step(
                journey_id=journey_id,
                step_type="embedding_search_results",
                description=f"Found {len(search_results)} similar questions in knowledge base",
                data={
                    "search_results": search_results_for_log,
                    "user_message": user_message,
                    "top_similarity": search_results_for_log[0]["similarity_score"] if search_results_for_log else 0
                }
            )
        
        # Get the best match (highest similarity)
        best_match = search_results[0]
        similarity_score = best_match.get('similarity', 0.0)  # Use 'similarity' not 'cosine_similarity'
        
        # Check if similarity is good enough (higher is better)
        if similarity_score < self.similarity_threshold:
            return {
                'action': 'continue_to_classification',
                'response': None,
                'confidence': 0,
                'matched_question': None
            }
        
        # Get the corresponding answer
        matched_document = best_match['document']
        metadata = best_match['metadata']
        
        # CRITICAL: Always get the answer, never return the question
        final_answer = None
        matched_question_text = None
        
        # If the matched document is a question, get its answer from metadata
        if metadata.get('type') == 'question':
            matched_question_text = matched_document
            answer_text = metadata.get('answer_text', '')  # Get answer from metadata
            
            if answer_text and answer_text.strip():
                final_answer = answer_text.strip()
                
                # Log the matched question-answer pair for journey tracking
                if LOGGING_AVAILABLE and journey_id:
                    message_journey_logger.add_step(
                        journey_id=journey_id,
                        step_type="embedding_qa_match",
                        description="Successfully matched question with answer from knowledge base",
                        data={
                            "matched_question": matched_question_text,
                            "matched_answer": final_answer,
                            "similarity_score": similarity_score,
                            "answer_source": "metadata",
                            "question_metadata": metadata
                        }
                    )
            else:
                final_answer = None
                
        else:
            # The matched document is already an answer (shouldn't happen with new approach)
            final_answer = matched_document
            matched_question_text = "Direct answer match"

        
        # CRITICAL: If no valid answer found, don't reply
        if not final_answer or final_answer.strip() == "":
            return {
                'action': 'skip',
                'response': None,
                'confidence': similarity_score,
                'matched_question': matched_question_text or matched_document,
                'error': 'No valid answer found'
            }
        
        # Check if answer is too short
        if len(final_answer.strip()) < 2:
            return {
                'action': 'skip',
                'response': None,
                'confidence': similarity_score,
                'matched_question': matched_question_text or matched_document,
                'error': 'Answer too short'
            }
        
        # CRITICAL: Check language matching BEFORE processing
        user_language = language_handler.detect_language(user_message)
        answer_language = language_handler.detect_language(final_answer)
        
        # If languages don't match, proceed to classification
        if user_language != answer_language:
            return {
                'action': 'continue_to_classification',
                'response': None,
                'confidence': similarity_score,
                'matched_question': matched_question_text or matched_document,
                'error': f'Language mismatch: user={user_language}, answer={answer_language}'
            }
        
       
        
        # Ask ChatGPT to evaluate if the response is appropriate
        evaluation_result = await self._evaluate_response_with_chatgpt(
            user_message, matched_question_text or matched_document, final_answer, detected_user_language, conversation_history, journey_id
        )
        
        if evaluation_result['action'] == 'reply':
            print(f"🤖 EmbeddingAgent Reply: {evaluation_result.get('response', final_answer)[:100]}...")
            return {
                'action': 'reply',
                'response': evaluation_result.get('response', final_answer),
                'confidence': similarity_score,
                'matched_question': matched_question_text or matched_document
            }
        elif evaluation_result['action'] == 'skip':
            return {
                'action': 'skip',
                'response': None,
                'confidence': similarity_score,
                'matched_question': matched_question_text or matched_document
            }
        else:
            return {
                'action': 'continue_to_classification',
                'response': None,
                'confidence': similarity_score,
                'matched_question': matched_question_text or matched_document
            }
    
    async def _evaluate_response_with_chatgpt(self, user_message: str, matched_question: str, 
                                            matched_answer: str, language: str, conversation_history: list = None, journey_id: str = None) -> Dict[str, Any]:
        """
        Ask ChatGPT to evaluate if the response is good and appropriate
        """
        
        # First check if the user message and matched answer are in the same language
        user_language = language_handler.detect_language(user_message)
        answer_language = language_handler.detect_language(matched_answer)
        
        # If languages don't match, proceed to classification
        if user_language != answer_language:
            return {'action': 'continue'}
        
        # Format conversation history for context
        conversation_context = ""
        if conversation_history:
            # Get the latest 5 messages for context
            recent_messages = conversation_history[-5:] if len(conversation_history) >= 5 else conversation_history
            
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

مهمتك الوحيدة: تصنيف رسالة العميل بدقة إلى واحدة من ثلاث حالات مع مراعاة سياق المحادثة السابقة.

- رسالة العميل الحالية: "{user_message}"
- السؤال المشابه من قاعدة البيانات : "{matched_question}"
- الرد المحفوظ: "{matched_answer}"

-المحادثة السابقة:
{conversation_context}

⚠️ **اختبار المعنى الدلالي المطلوب:**
قبل اختيار "reply"، يجب أن تتأكد أن رسالة العميل والسؤال من قاعدة البيانات لهما **نفس المعنى والقصد** تماماً.
- إذا كان المعنى مختلف أو القصد مختلف، اختر "continue" حتى لو كانت الكلمات متشابهة
- إذا كان العميل يسأل عن شيء والسؤال في قاعدة البيانات عن شيء آخر، اختر "continue"
- فقط إذا كان المعنى والقصد متطابق تماماً، يمكن اختيار "reply"

التصنيف يجب أن يعتمد على القواعد التالية مع مراعاة سياق المحادثة:

🟢 "reply":
- ✅ فقط إذا كانت رسالة العميل والسؤال من قاعدة البيانات لهما **نفس المعنى والقصد تماماً** وكان لدينا رد محفوظ مناسب
- ✅ أو إذا كانت الرسالة مجرد تحية أو شكر بسيط بدون أي محتوى إضافي (مع أو بدون علامات ترقيم مثل النقاط أو المسافات)
  - مثل: (السلام عليكم، مرحبا، أهلاً، هلا، هلا وغلا، صباح الخير، مساء الخير، شكراً، يعطيك العافية، جزاك الله خير، الله يوفقكم، شكرا لك، مشكور)
  - أو نفس التحيات مع علامات ترقيم مثل: (هلا...، مرحبا.، السلام عليكم!!، شكرا...) يجب اختيار reply

🟡 "skip":
- إذا كانت الرسالة لا تتطلب رد مثل: (تمام، طيب، أوك، أوكي، تمام التمام، خلاص)

🔴 "continue":
- إذا لم تكن تحية أو شكر بسيط
- ولم نجد لها تطابقًا واضحًا في قاعدة البيانات (أي لم تكن مشابهة لسؤال موجود لدينا)
- أو كانت تحتوي على تحية أو شكر لكن مرفقة بسؤال أو طلب
- اذا كان سياق المحادثة يشير ام العميل يستفسر عن المنتجات او اعلامات التجارية او المدن او الاسعار
- 🚨 إذا ذكر العميل علامات تجارية للمياه - هذه علامات مياه حقيقية ويجب إرسالها للتصنيف
- أسماء العلامات التجارية الشائعة: نستله، أكوافينا، العين، القصيم، المراعي، نوفا، نقي، تانيا، صافية، بنما، أروى، مساء، سدير، صحتك، صحتين، وي، المنهل، حلوة، هنا، صفا مكة، أوسكا
- 🔍 مهم: يمكن التعرف على العلامات التجارية من سياق المحادثة السابقة أيضاً - إذا ذُكرت علامة تجارية في الرسائل السابقة، يجب إرسال الرسالة الحالية للتصنيف 

❗️قواعد مراعاة سياق المحادثة:
- **الردود المتكررة**: إذا أرسلنا نفس النوع من الرد (مثل روابط التطبيق أو معلومات الأسعار) خلال آخر 3-5 رسائل، اختر "continue"
- **السياق التطويري**: إذا كان العميل يسأل عن شيء محدد بعد أن حصل على رد عام، اختر "continue" للحصول على معلومات أكثر تفصيلاً

❗️ملحوظة:
- إذا وُجد تطابق في قاعدة البيانات وكان هناك رد محفوظ ولم نرسله مؤخراً، اختر "reply"
- إذا كانت الرسالة فقط "شكراً" أو "السلام عليكم"، اختر "reply"
- إذا كانت مثل "تمام" أو "أوك"، اختر "skip"
- إذا كانت تحتوي على سؤال أو استفسار ولم نجد لها تطابقاً في قاعدة البيانات، اختر "continue"
 ❗️ملحوظه مهمة جدا جدا 
- اذا كان السؤاال عن ماركة مياه معينة او منتج معين او سعر منتج معين او السوال عن الاسعار او الماركات في مدينة معينةاختر "continue"
- **تحليل الروابط والمعلومات المتكررة**: إذا كان الرد المحفوظ يحتوي على روابط أو معلومات أرسلناها للعميل في آخر 3 رسائل، اختر "continue"

اخرج فقط واحدة من: reply أو skip أو continue
"""

        else:
            evaluation_prompt = f"""You are a very strict response quality evaluator for Abar water delivery customer service.

Your task: Determine the appropriate action based on the customer message, database match, and conversation history context.

Inputs:
- Current customer message: "{user_message}"
- Similar question from database: "{matched_question}"
- Stored response: "{matched_answer}"
{conversation_context}

⚠️ **Required Semantic Meaning Check:**
Before choosing "reply", you must ensure that the customer message and the database question have **exactly the same meaning and intent**.
- If the meaning is different or the intent is different, choose "continue" even if the words are similar
- If the customer is asking about one thing and the database question is about something else, choose "continue"
- Only if the meaning and intent are exactly the same, you may choose "reply"

Rules with conversation context consideration:

✅ "reply":
- ONLY if the customer message and database question have **exactly the same meaning and intent** and we have an appropriate stored response
- OR if the message is **only** a simple genuine greeting or thanks, such as:
    - Greetings: ("Hello", "Hi", "Peace be upon you", "Good morning", "Good evening")
    - Thanks: ("Thanks", "Thank you", "God bless you", "Much appreciated")

🚫 "skip":
- If the message is something like: ("ok", "okay", "fine", "great", "alright", "noted", "sure") — it does not require a reply.

🔁 "continue":
- If the message contains anything beyond a simple greeting or thanks and does not match any known question in the database.
- 🚨 If customer mentions water brand names - these are real water brands and should be sent to classification
- Common water brand names: نستله (Nestle), أكوافينا (Aquafina), العين (Al-Ain), القصيم (Al-Qassim), المراعي (Almarai), نوفا (Nova), نقي (Naqi), تانيا (Tania), صافية (Safia), بنما (Banama), أروى (Arwa), مساء (Massa), سدير (Sudair), صحتك (Sahtak), صحتين (Sahtain), وي (Wi), المنهل (Al-Manhal), حلوة (Helwa), هنا (Hena), صفا مكة (Safa Makkah), أوسكا (Oska)
- 🔍 Important: Brand names can also be identified from conversation history context - if a brand was mentioned in previous messages, current message should be sent to classification
- Examples:
    - "Hi, I have a question" → continue
    - "Thank you, but I need help" → continue
    - "How do I order?" → continue
    - "Can I speak to someone?" → continue

🔄 **Conversation History Rules**:
- **Repeated Response Types**: If we sent the same type of response (like app links or pricing info) within the last 3-5 messages, choose "continue"
- **Contextual Follow-up**: If the customer asks for something specific after receiving a general response, choose "continue" for more detailed information
- **Link/Information Analysis**: If the stored response contains links or information we already sent to the customer in the last 3 messages, choose "continue"

📌 Summary:
- If there's a semantic match with a known question AND we haven't sent similar response recently → **reply**
- If it's ONLY a greeting or thanks → **reply**
- If it's a short acknowledgment → **skip**
- If we recently sent similar response or customer needs follow-up → **continue**
- Everything else → **continue**

Return only one value: reply, skip, or continue
"""

        
        try:
            # Build the complete messages for the API call
            system_content ="""You are an extremely strict evaluator for customer service response quality at Abar Water Delivery.

Your ONLY task: Decide how to handle a customer's message based on its content and whether it has the **exact same meaning** as any known question in the company database.

⚠️ **CRITICAL SEMANTIC MEANING REQUIREMENT:**
You must perform a strict semantic meaning check. The customer message and database question must have **exactly the same meaning and intent** - not just similar words or topics.

Inputs provided:
- Customer message: the message sent by the user.
- Matched question from vector database (if any): the most semantically similar known question.
- Stored answer: the saved response for that matched question (if available).
- Conversation context: last few messages exchanged.

You must classify the message into **only one** of the following:

 reply:
- ONLY if the message has **exactly the same meaning and intent** as a known question in the database AND we have a saved answer
- OR if the message is a **pure standalone greeting or thanks**, with no additional text.
  - Valid examples: "السلام عليكم", "شكراً", "يعطيك العافية", "مرحبا", "أهلا", "الله يوفقكم"

 skip:
- If the message contains **acknowledgements** or **neutral confirmations** that don’t need a response.
  - Examples: "تمام", "أوكي", "نعم", "طيب", "انتهيت", "أوكيه", "خلاص", "أكيد", "اوكي تمام"

   continue:
- If the message contains **any other content** (question, request, statement, scheduling info), and we do **not** have a match from the database.
  - Even if the message starts with a greeting or thanks, but continues with more — it's continue.
  - 🚨 If customer mentions water brand names - these are real water brands and should be sent to classification
  - Common water brand names: نستله (Nestle), أكوافينا (Aquafina), العين (Al-Ain), القصيم (Al-Qassim), المراعي (Almarai), نوفا (Nova), نقي (Naqi), تانيا (Tania), صافية (Safia), بنما (Banama), أروى (Arwa), مساء (Massa), سدير (Sudair), صحتك (Sahtak), صحتين (Sahtain), وي (Wi), المنهل (Al-Manhal), حلوة (Helwa), هنا (Hena), صفا مكة (Safa Makkah), أوسكا (Oska)
  - 🔍 Important: Brand names can also be identified from conversation history context - if a brand was mentioned in previous messages, current message should be sent to classification
  - Examples:
    - "السلام عليكم، عندي استفسار"
    - "أبي أطلب مياه"
    - "متى توصلون؟"
    - "يعطيك العافية، بس عندي سؤال"

 Strict enforcement:
- DO NOT reply to partial greetings, mixed messages, or polite phrases that contain extra content — unless they match a known question and we have a stored answer.
- DO NOT skip if the message contains any intent or need for help.

Final instruction:
Be extremely conservative. Use `reply` ONLY when:
- The message is a 100% pure greeting/thanks, OR
- It has **exactly the same meaning and intent** as a question in the database with a saved answer.

⚠️ Remember: Similar words ≠ Same meaning. The customer's intent must be identical to the database question's intent.

Return only one of: `reply`, `skip`, or `continue`.
"""
            
            messages = [
                {"role": "system", "content": system_content},
                {"role": "user", "content": evaluation_prompt}
            ]
            
            # Log the complete prompt before sending to LLM
            if LOGGING_AVAILABLE and journey_id:
                complete_prompt = f"SYSTEM: {system_content}\n\nUSER: {evaluation_prompt}"
                message_journey_logger.add_step(
                    journey_id=journey_id,
                    step_type="embedding_llm_evaluation_prompt",
                    description="Sending evaluation prompt to ChatGPT for embedding response validation",
                    data={
                        "complete_prompt": complete_prompt,
                        "system_prompt": system_content,
                        "user_prompt": evaluation_prompt,
                        "user_message": user_message,
                        "matched_question": matched_question,
                        "matched_answer": matched_answer,
                        "model": "gpt-4o-mini"
                    }
                )
            
            # Time the LLM call
            llm_start_time = time.time()
            
            # Convert to LangChain messages
            langchain_messages = [
                SystemMessage(content=messages[0]["content"]),
                HumanMessage(content=messages[1]["content"])
            ]
            
            # Use LangChain with specific parameters
            temp_llm = self.llm.bind(max_tokens=20, temperature=0.1)
            response = await temp_llm.ainvoke(langchain_messages)
            
            llm_duration = int((time.time() - llm_start_time) * 1000)
            evaluation = response.content.strip().lower()
            
            # Log the complete response from LLM
            if LOGGING_AVAILABLE and journey_id:
                message_journey_logger.log_llm_interaction(
                    journey_id=journey_id,
                    llm_type="openai",
                    prompt=f"SYSTEM: {system_content}\n\nUSER: {evaluation_prompt}",
                    response=evaluation,
                    model="gpt-4o-mini",
                    duration_ms=llm_duration,
                    tokens_used={"total_tokens": None}  # LangChain response doesn't include token usage directly
                )
                
                message_journey_logger.add_step(
                    journey_id=journey_id,
                    step_type="embedding_llm_evaluation_result",
                    description=f"ChatGPT evaluation completed: {evaluation}",
                    data={
                        "evaluation_result": evaluation,
                        "raw_response": response.content,
                        "duration_ms": llm_duration,
                        "tokens_used": None,  # LangChain response doesn't include token usage directly
                        "user_message": user_message,
                        "matched_question": matched_question,
                        "matched_answer": matched_answer
                    }
                )
            
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
            # Default to continue on error
            return {'action': 'continue'}

    async def debug_knowledge_base_structure(self, sample_size: int = 5) -> Dict[str, Any]:
        """
        Debug method to check the knowledge base structure and verify question-answer linking
        """

        
        try:
            # Get a sample of documents from the knowledge base
            from vectorstore.chroma_db import chroma_manager
            
            # Get all documents
            all_data = chroma_manager.get_collection_safe().get(include=["documents", "metadatas", "embeddings"])
            
            if not all_data or not all_data['documents']:
                return {"status": "error", "message": "No documents found"}
            
            documents = all_data['documents']
            metadatas = all_data['metadatas']
            ids = all_data['ids']
            

            
            # Count questions and answers
            questions = []
            answers = []
            
            for i, (doc, metadata, doc_id) in enumerate(zip(documents, metadatas, ids)):
                if metadata.get('type') == 'question':
                    questions.append({'doc': doc, 'metadata': metadata, 'id': doc_id})
                else:
                    answers.append({'doc': doc, 'metadata': metadata, 'id': doc_id})
            

            
            # Test a few question-answer pairs
            test_results = []
            
            for i, question_info in enumerate(questions[:sample_size]):
                answer_text = question_info['metadata'].get('answer_text', '')
                if answer_text and answer_text.strip():
                    test_results.append({
                        "question": question_info['doc'][:100],
                        "answer": answer_text[:100],
                        "status": "success"
                    })
                else:
                    test_results.append({
                        "question": question_info['doc'][:100],
                        "answer": None,
                        "status": "no_answer_in_metadata"
                    })
            
            return {
                "status": "success",
                "total_documents": len(documents),
                "questions_count": len(questions),
                "answers_count": len(answers),
                "test_results": test_results
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}

# Create and export the instance
embedding_agent = EmbeddingAgent() 