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
        
        # Detailed logging: capture all search results for journey logging
        search_results_for_log = []
        
        for i, result in enumerate(search_results, 1):
            similarity_score = result.get('similarity', result.get('distance', 0.0))
            document_preview = result['document'][:100] + "..." if len(result['document']) > 100 else result['document']
            metadata = result.get('metadata', {})
            
            print(f"   Result {i}:")
            print(f"   - Similarity Score: {similarity_score:.4f}")
            print(f"   - Document Type: {metadata.get('type', 'unknown')}")
            print(f"   - Content Preview: {document_preview}")
            print(f"   - Has Answer Text: {bool(metadata.get('answer_text', '').strip())}")
            print(f"   - Full Metadata: {metadata}")
            print(f"   ---")
            
            # Additional debugging: Check if this is a question without an answer
            if metadata.get('type') == 'question':
                answer_text = metadata.get('answer_text', '')
                if not answer_text or not answer_text.strip():
                    print(f"   ⚠️  WARNING: Question without answer text!")
                elif metadata.get('has_answer') == False:
                    print(f"   ℹ️  Info: Question marked as having no answer")
            
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
        
        print(f"🎯 EmbeddingAgent: Best match selected:")
        print(f"   - Question: {best_match['document'][:100]}...")
        print(f"   - Similarity: {similarity_score:.4f}")
        print(f"   - Type: {best_match.get('metadata', {}).get('type', 'unknown')}")
        print(f"   - Metadata: {best_match['metadata']}")
        print(f"   - Has Answer Text: {bool(best_match.get('metadata', {}).get('answer_text', '').strip())}")
        
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
        
        print(f"🔍 EmbeddingAgent: Processing matched result...")
        print(f"   - Matched Document: {matched_document[:100]}...")
        print(f"   - Document Type: {metadata.get('type', 'unknown')}")
        print(f"   - Metadata: {metadata}")
        
        # CRITICAL: Always get the answer, never return the question
        final_answer = None
        matched_question_text = None
        
        # If the matched document is a question, get its answer from metadata
        if metadata.get('type') == 'question':
            matched_question_text = matched_document
            answer_text = metadata.get('answer_text', '')  # Get answer from metadata
            
            print(f"   - This is a QUESTION: '{matched_question_text}...'")
            print(f"   - Answer from metadata: '{answer_text if answer_text else 'No answer'}...'")
            
            if answer_text and answer_text.strip():
                final_answer = answer_text.strip()
                print(f"   - ✅ Found ANSWER in metadata: '{final_answer}...'")
                
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
                print(f"   - ❌ No answer found in question metadata")
                final_answer = None
                
        else:
            # The matched document is already an answer (shouldn't happen with new approach)
            print(f"   - ⚠️  Matched document appears to be an answer directly (unexpected with new approach)")
            final_answer = matched_document
            matched_question_text = "Direct answer match"

        
        # CRITICAL: If no valid answer found, don't reply
        if not final_answer or final_answer.strip() == "":
            print(f"🚫 EmbeddingAgent: No valid answer found - skipping reply")
            print(f"   - Question: {matched_question_text}")
            print(f"   - Answer: '{final_answer}'")
            return {
                'action': 'skip',
                'response': None,
                'confidence': similarity_score,
                'matched_question': matched_question_text or matched_document,
                'error': 'No valid answer found'
            }
        
        # Check if answer is too short
        if len(final_answer.strip()) < 2:
            print(f"🚫 EmbeddingAgent: Answer too short - skipping reply")
            print(f"   - Answer: '{final_answer}'")
            return {
                'action': 'skip',
                'response': None,
                'confidence': similarity_score,
                'matched_question': matched_question_text or matched_document,
                'error': 'Answer too short'
            }
        
        print(f"📝 EmbeddingAgent: Valid answer found!")
        print(f"   - Question: {matched_question_text[:50]}...")
        print(f"   - Answer: {final_answer[:100]}...")
        print(f"   - Answer Length: {len(final_answer)} characters")
        
        # CRITICAL: Check language matching BEFORE processing
        user_language = language_handler.detect_language(user_message)
        answer_language = language_handler.detect_language(final_answer)
        
        print(f"🌐 Language Check:")
        print(f"   - User message language: {user_language}")
        print(f"   - Answer language: {answer_language}")
        
        # If languages don't match, proceed to classification
        if user_language != answer_language:
            print(f"🔄 Language mismatch: user={user_language}, answer={answer_language} - proceeding to classification")
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
        
        print(f"🤖 EmbeddingAgent: ChatGPT evaluation: {evaluation_result}")
        
        if evaluation_result['action'] == 'reply':
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
            print(f"🌐 Language mismatch: user={user_language}, answer={answer_language} - proceeding to classification")
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

مهمتك الوحيدة: تصنيف رسالة العميل بدقة إلى واحدة من ثلاث حالات.

- رسالة العميل الحالية: "{user_message}"
- السؤال المشابه من قاعدة البيانات : "{matched_question}"
- الرد المحفوظ: "{matched_answer}"

-المحادثة السابقة:
{conversation_context}

التصنيف يجب أن يعتمد على القواعد التالية:

🟢 "reply":
-✅reply  إذا كانت رسالة العميل الحالية مشابهة لسؤال موجود في قاعدة البيانات ، وكان لدينا رد محفوظ له — سواء كانت تحية أو استفسار أو طلب — يجب اختيار 

- أو إذا كانت الرسالة مجرد تحية أو شكر بسيط بدون أي محتوى إضافي (مع أو بدون علامات ترقيم مثل النقاط أو المسافات)
  - مثل: (السلام عليكم، مرحبا، أهلاً، هلا، هلا وغلا، صباح الخير، مساء الخير، شكراً، يعطيك العافية، جزاك الله خير، الله يوفقكم، شكرا لك، مشكور)
  - أو نفس التحيات مع علامات ترقيم مثل: (هلا...، مرحبا.، السلام عليكم!!، شكرا...) يجب اختيار reply

🟡 "skip":
- إذا كانت الرسالة قصيرة ولا تتطلب رد مثل: (تمام، طيب، أوك، أوكي، تمام التمام، خلاص)

🔴 "continue":
- إذا لم تكن تحية أو شكر بسيط
- ولم نجد لها تطابقًا واضحًا في قاعدة البيانات (أي لم تكن مشابهة لسؤال موجود لدينا)
- أو كانت تحتوي على تحية أو شكر لكن مرفقة بسؤال أو طلب

❗️ملحوظة:
- إذا وُجد تطابق في قاعدة البيانات وكان هناك رد محفوظ، اختر "reply"
- إذا كانت الرسالة فقط "شكراً" أو "السلام عليكم"، اختر "reply"
- إذا كانت مثل "تمام" أو "أوك"، اختر "skip"
- إذا كانت تحتوي على سؤال أو استفسار ولم نجد لها تطابقاً في قاعدة البيانات، اختر "continue"
 ❗️ملحوظه مهمة جدا جدا 
- اذا كان السؤاال عن ماركة مياه معينة او منتج معين او سعر منتج معين او السوال عن الاسعار او الماركات في مدينة معينةاختر "continue"
- إذا أخبرنا العميل بهذا الرد مسبقاً "بتحصل الاصناف والاسعار في التطبيق وهذا هو الرابط https://onelink.to/abar_app https://abar.app/en/store/ وايضا عن طريق الموقع الالكتروني"
فلا يجب الرد بهذا الرد مرة ثانية ويجب اختيار continue 
-

اخرج فقط واحدة من: reply أو skip أو continue
"""

        else:
            evaluation_prompt = f"""You are a very strict response quality evaluator for Abar water delivery customer service.

Your task: Determine the appropriate action based on the customer message and whether it matches any known question in the database.

Inputs:
- Current customer message: "{user_message}"
- Similar question from database: "{matched_question}"
- Stored response: "{matched_answer}"
{conversation_context}

Rules:

✅ "reply":
- If the customer message is semantically similar to a known question in the database (even if it contains more than a greeting or thanks), reply using the stored answer.
- OR if the message is **only** a simple genuine greeting or thanks, such as:
    - Greetings: ("Hello", "Hi", "Peace be upon you", "Good morning", "Good evening")
    - Thanks: ("Thanks", "Thank you", "God bless you", "Much appreciated")

🚫 "skip":
- If the message is something like: ("ok", "okay", "fine", "great", "alright", "noted", "sure") — it does not require a reply.

🔁 "continue":
- If the message contains anything beyond a simple greeting or thanks and does not match any known question in the database.
- Examples:
    - "Hi, I have a question" → continue
    - "Thank you, but I need help" → continue
    - "How do I order?" → continue
    - "Can I speak to someone?" → continue

📌 Summary:
- If there's a semantic match with a known question → **reply**
- If it's ONLY a greeting or thanks → **reply**
- If it's a short acknowledgment → **skip**
- Everything else → **continue**

Return only one value: reply, skip, or continue
"""

        
        try:
            print(f"🤖 ChatGPT evaluation prompt: {evaluation_prompt}")
            
            # Build the complete messages for the API call
            system_content ="""You are an extremely strict evaluator for customer service response quality at Abar Water Delivery.

Your ONLY task: Decide how to handle a customer's message based on its content and whether it matches any known question in the company database.

Inputs provided:
- Customer message: the message sent by the user.
- Matched question from vector database (if any): the most semantically similar known question.
- Stored answer: the saved response for that matched question (if available).
- Conversation context: last few messages exchanged.

You must classify the message into **only one** of the following:

 reply:
- If the message is **semantically similar** to a known question in the database AND we have a saved answer — regardless of whether the message is a greeting, request, or question.
- OR if the message is a **pure standalone greeting or thanks**, with no additional text.
  - Valid examples: "السلام عليكم", "شكراً", "يعطيك العافية", "مرحبا", "أهلا", "الله يوفقكم"

 skip:
- If the message contains **acknowledgements** or **neutral confirmations** that don’t need a response.
  - Examples: "تمام", "أوكي", "نعم", "طيب", "انتهيت", "أوكيه", "خلاص", "أكيد", "اوكي تمام"

   continue:
- If the message contains **any other content** (question, request, statement, scheduling info), and we do **not** have a match from the database.
  - Even if the message starts with a greeting or thanks, but continues with more — it’s continue.
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
- It has a clear semantic match in the database with a saved answer.

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
            
            # Log the evaluation for debugging
            print(f"🤖 ChatGPT evaluation result: '{evaluation}'")
            print(f"🤖 Raw ChatGPT response: '{response.content}'")
            print(f"🤖 User message: '{user_message}'")
            print(f"🤖 Matched question: '{matched_question}'")
            print(f"🤖 Matched answer: '{matched_answer[:100]}...'")
            
            # Map the response to our action format
            if 'reply' in evaluation:
                print(f"✅ EmbeddingAgent: ChatGPT says REPLY - will send response")
                return {'action': 'reply'}
            elif 'skip' in evaluation:
                print(f"🚫 EmbeddingAgent: ChatGPT says SKIP - no response will be sent")
                return {'action': 'skip'}
            elif 'continue' in evaluation:
                print(f"🔄 EmbeddingAgent: ChatGPT says CONTINUE - passing to classification agent")
                return {'action': 'continue'}
            else:
                # Default to continue if we can't parse the response
                print(f"⚠️ Could not parse evaluation result '{evaluation}', defaulting to continue")
                return {'action': 'continue'}
                
        except Exception as e:
            print(f"❌ EmbeddingAgent: Error evaluating response with ChatGPT: {str(e)}")
            # Default to continue on error
            return {'action': 'continue'}

    async def debug_knowledge_base_structure(self, sample_size: int = 5) -> Dict[str, Any]:
        """
        Debug method to check the knowledge base structure and verify question-answer linking
        """
        print(f"🔍 DEBUG: Testing knowledge base structure...")
        
        try:
            # Get a sample of documents from the knowledge base
            from vectorstore.chroma_db import chroma_manager
            
            # Get all documents
            all_data = chroma_manager.get_collection_safe().get(include=["documents", "metadatas", "embeddings"])
            
            if not all_data or not all_data['documents']:
                print(f"❌ DEBUG: No documents found in knowledge base")
                return {"status": "error", "message": "No documents found"}
            
            documents = all_data['documents']
            metadatas = all_data['metadatas']
            ids = all_data['ids']
            
            print(f"📊 DEBUG: Found {len(documents)} total documents")
            
            # Count questions and answers
            questions = []
            answers = []
            
            for i, (doc, metadata, doc_id) in enumerate(zip(documents, metadatas, ids)):
                if metadata.get('type') == 'question':
                    questions.append({'doc': doc, 'metadata': metadata, 'id': doc_id})
                else:
                    answers.append({'doc': doc, 'metadata': metadata, 'id': doc_id})
            
            print(f"📈 DEBUG: Found {len(questions)} questions and {len(answers)} answers")
            
            # Test a few question-answer pairs
            test_results = []
            
            for i, question_info in enumerate(questions[:sample_size]):
                print(f"\n🔍 DEBUG Test {i+1}:")
                print(f"   Question: {question_info['doc'][:100]}...")
                print(f"   Question ID: {question_info['id']}")
                print(f"   Question Metadata: {question_info['metadata']}")
                
                answer_text = question_info['metadata'].get('answer_text', '')
                if answer_text and answer_text.strip():
                    print(f"   ✅ Found Answer in metadata: {answer_text[:100]}...")
                    
                    test_results.append({
                        "question": question_info['doc'][:100],
                        "answer": answer_text[:100],
                        "status": "success"
                    })
                else:
                    print(f"   ❌ No answer found in metadata")
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
            print(f"❌ DEBUG: Error testing knowledge base structure: {str(e)}")
            return {"status": "error", "message": str(e)}

# Create and export the instance
embedding_agent = EmbeddingAgent() 