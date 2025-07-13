import os
from fastapi import FastAPI, Request, Depends, HTTPException, Header, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response
from typing import Optional, List
from dotenv import load_dotenv
import uvicorn
import json
import sys
import uuid
from datetime import datetime
import aiohttp
import urllib.parse
import asyncio
import time
import threading
from collections import defaultdict
from typing import Dict, List, Any

# Load environment variables from .env
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '.env')
load_dotenv(dotenv_path=env_path)

# Debug: Print environment variables (remove in production)
print(f"Current working directory: {os.getcwd()}")
print(f"Loading .env from: {env_path}")
print(f"OPENAI_API_KEY set: {'Yes' if os.getenv('OPENAI_API_KEY') else 'No'}")
print(f"WATI_API_KEY set: {'Yes' if os.getenv('WATI_API_KEY') else 'No'}")

from database.db_utils import get_db, DatabaseManager
from database.db_models import MessageType, UserSession, BotReply
from agents.embedding_agent import embedding_agent
from agents.message_classifier import message_classifier
from agents.query_agent import query_agent
from agents.service_request import service_request_agent
from utils.language_utils import language_handler
from services.data_api import data_api
from services.data_scraper import data_scraper
from services.scheduler import scheduler

# Import knowledge_manager
from utils.knowledge_manager import knowledge_manager

app = FastAPI(
    title="Abar Chatbot API",
    description="API for handling WhatsApp messages for Abar water delivery app",
    version="1.0.0"
)

# Add session middleware for login functionality
app.add_middleware(SessionMiddleware, secret_key="abar-secret-key-2024")

# Set up templates directory
templates = Jinja2Templates(directory="templates")

# Login credentials (in production, use environment variables)
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "abar2024"

# Authentication helper functions
def check_authentication(request: Request) -> bool:
    """Check if user is authenticated"""
    return request.session.get("authenticated", False)

def require_authentication(request: Request):
    """Require authentication for protected routes"""
    if not check_authentication(request):
        raise HTTPException(status_code=401, detail="Authentication required")

# Login routes
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Root route - redirect to appropriate page based on authentication"""
    if check_authentication(request):
        return RedirectResponse(url="/knowledge/admin", status_code=302)
    else:
        return RedirectResponse(url="/login", status_code=302)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Display login page"""
    # If already authenticated, redirect to admin panel
    if check_authentication(request):
        return RedirectResponse(url="/knowledge/admin", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request):
    """Handle login form submission"""
    form = await request.form()
    username = form.get("username")
    password = form.get("password")
    
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        request.session["authenticated"] = True
        return RedirectResponse(url="/knowledge/admin", status_code=302)
    else:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "اسم المستخدم أو كلمة المرور غير صحيحة"
        })

@app.get("/logout")
async def logout(request: Request):
    """Handle logout"""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)

# Wati webhook verification token (set this in your .env file)
WATI_WEBHOOK_VERIFY_TOKEN = os.getenv("WATI_WEBHOOK_VERIFY_TOKEN", "your_verification_token")

# Verification endpoint for Wati webhook setup
@app.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token")
):
    """
    Handle webhook verification from Wati.
    This is required for setting up the webhook initially.
    """
    print(f"Received verification request: mode={hub_mode}, challenge={hub_challenge}, token={hub_verify_token}")
    
    # Check if this is a subscribe request and the token matches
    if hub_mode == "subscribe" and hub_verify_token == WATI_WEBHOOK_VERIFY_TOKEN:
        return int(hub_challenge)
    
    raise HTTPException(status_code=403, detail="Verification failed")

# Main webhook endpoint to receive WhatsApp messages from Wati
@app.post("/webhook")
async def webhook(request: Request, db=Depends(get_db)):
    """Handle incoming WhatsApp messages from Wati webhook"""
    try:
        data = await request.json()
        #print(f"Webhook received: {json.dumps(data, indent=2)}")
        
        # Extract message data
        phone_number = data.get("waId")
        message_type = data.get("type", "text")  # Can be text, audio, etc.
        wati_message_id = data.get("id")  # Extract Wati message ID
        
        # Check if this is a template reply from WATI (button reply, list reply, etc.)
        button_reply = data.get("buttonReply")
        list_reply = data.get("listReply") 
        interactive_button_reply = data.get("interactiveButtonReply")
        
        if button_reply or list_reply or interactive_button_reply or message_type == "button":
            print(f"🔘 Template reply detected from WATI - Skipping processing")
            print(f"   Type: {message_type}")
            if button_reply:
                print(f"   Button Reply: {button_reply.get('text', 'N/A')}")
            if list_reply:
                print(f"   List Reply: {list_reply}")
            if interactive_button_reply:
                print(f"   Interactive Button Reply: {interactive_button_reply}")
            
            return {"status": "success", "message": "Template reply - not processed"}
        
        # Early duplicate check with existing session
        if wati_message_id and DatabaseManager.check_message_already_processed(db, wati_message_id):
            print(f"🔄 Duplicate message detected with ID: {wati_message_id}. Returning success immediately.")
            return {"status": "success", "message": "Already processed"}
        
        # Log the incoming message for debugging
        print(f"📱 New message from {phone_number}: {data.get('text', 'N/A')[:50]}...")
        
        # IMMEDIATE RESPONSE: Send quick response to Wati to prevent duplicate notifications
        immediate_response = {"status": "success", "message": "Processing"}
        
        # Add message to batch instead of processing immediately
        await add_message_to_batch(phone_number, data)
        
        return immediate_response

    except Exception as e:
        print(f"[Webhook ERROR] {str(e)}")
        return {"status": "error", "message": str(e)}

# Replace the global dictionaries with thread-safe alternatives
class ThreadSafeMessageBatcher:
    def __init__(self):
        self._batches: Dict[str, List[Dict]] = {}
        self._timers: Dict[str, asyncio.Task] = {}
        self._locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
    
    async def add_message_to_batch(self, phone_number: str, message_data: dict):
        """Add a message to user's batch with proper locking"""
        async with self._locks[phone_number]:
            current_time = time.time()
            
            # Initialize batch for new user
            if phone_number not in self._batches:
                self._batches[phone_number] = []
            
            # Add message to batch
            self._batches[phone_number].append({
                'data': message_data,
                'timestamp': current_time,
                'text': message_data.get('text', '')
            })
            
            # Cancel existing timer if any
            if phone_number in self._timers:
                self._timers[phone_number].cancel()
            
            # Set new timer to process batch after 3 seconds of inactivity
            self._timers[phone_number] = asyncio.create_task(
                self._process_batch_delayed(phone_number)
            )
            print(f"📦 Added message to batch for {phone_number}. Batch size: {len(self._batches[phone_number])}")
    
    async def _process_batch_delayed(self, phone_number: str):
        """Process batch after delay"""
        await asyncio.sleep(3)  # Wait 3 seconds for more messages
        await self.process_user_batch(phone_number)
    
    async def process_user_batch(self, phone_number: str):
        """Process all messages in user's batch as one conversation"""
        async with self._locks[phone_number]:
            if phone_number not in self._batches or not self._batches[phone_number]:
                return
            
            batch = self._batches[phone_number]
            print(f"🔄 Processing batch of {len(batch)} messages for {phone_number}")
            
            # Clear the batch and timer
            self._batches[phone_number] = []
            if phone_number in self._timers:
                del self._timers[phone_number]
            
            # Combine all messages into one conversation
            combined_messages = []
            wati_message_ids = []
            
            for msg_item in batch:
                combined_messages.append(msg_item['text'])
                if msg_item['data'].get('id'):
                    wati_message_ids.append(msg_item['data']['id'])
            
            # Create combined message text
            if len(combined_messages) == 1:
                combined_text = combined_messages[0]
            else:
                combined_text = "\n".join([f"رسالة {i+1}: {msg}" for i, msg in enumerate(combined_messages)])
            
            # Use the first message data as base
            first_message_data = batch[0]['data']
            first_message_data['text'] = combined_text
            first_message_data['is_batch'] = True
            first_message_data['batch_size'] = len(batch)
            first_message_data['batch_message_ids'] = wati_message_ids
            
            # Process the combined message
            await process_message_async(
                first_message_data, 
                phone_number, 
                first_message_data.get('type', 'text'),
                f"batch_{phone_number}_{int(time.time())}"
            )

# Create thread-safe instance
message_batcher = ThreadSafeMessageBatcher()

# Remove the old global dictionaries
# user_message_batches = {}  # REMOVED
# batch_timers = {}  # REMOVED

async def add_message_to_batch(phone_number: str, message_data: dict):
    """Add a message to user's batch and set/reset timer"""
    await message_batcher.add_message_to_batch(phone_number, message_data)

async def process_user_batch(phone_number: str):
    """Process all messages in user's batch as one conversation"""
    await message_batcher.process_user_batch(phone_number)

async def process_message_async(data, phone_number, message_type, wati_message_id):
    """Process the message asynchronously after responding to Wati"""
    # Create a new database session for async processing
    from database.db_utils import SessionLocal
    db = SessionLocal()
    
    try:
        print(f"🔄 Starting async processing for message {wati_message_id} from {phone_number}")
        
        # Check if this is a batch message
        is_batch = data.get('is_batch', False)
        batch_size = data.get('batch_size', 1)
        
        if is_batch:
            print(f"📦 Processing combined batch of {batch_size} messages from {phone_number}")
        
        # Double-check for duplicate message processing with fresh session
        if wati_message_id and not wati_message_id.startswith('batch_') and DatabaseManager.check_message_already_processed(db, wati_message_id):
            print(f"🔄 Duplicate message detected during async processing with ID: {wati_message_id}. Skipping.")
            return
        
        # TESTING LOGIC: Determine user type
        allowed_numbers = [
            "201142765209",
            "966138686475",  # 966 13 868 6475 (spaces removed)
            "966505281144",  
            "966541794866",
            "201003754330",
        ]
        
        # Normalize phone number by removing spaces and special characters
        normalized_phone = "".join(char for char in str(phone_number) if char.isdigit())
        
        # Check if user is allowed to access full bot functionality
        is_allowed_user = normalized_phone in allowed_numbers
        is_test_user = normalized_phone in allowed_numbers  # For now, all allowed users are test users
        
        if is_allowed_user:
            print(f"✅ Allowed user detected: {phone_number} - Full functionality enabled")
        else:
            print(f"🔒 Non-allowed user detected: {phone_number} - Limited to embedding agent replies only")
        
        # Get or create user session
        user = DatabaseManager.get_user_by_phone(db, phone_number)
        if not user:
            user = DatabaseManager.create_user(db, phone_number)
        
        session = db.query(UserSession).filter_by(user_id=user.id).first()
        if not session:
            session = UserSession(
                user_id=user.id,
                session_id=str(uuid.uuid4()),
                started_at=datetime.utcnow()
            )
            db.add(session)
        
        session.last_activity = datetime.utcnow()
        
        # Handle different message types
        if message_type == "audio":
            # Convert audio to text using Gemini
            audio_data = data.get("audio", {}).get("data")
            if audio_data:
                message_text = await message_classifier.process_audio(audio_data)
                if not message_text:
                    print("Failed to process audio message")
                    return
            else:
                print("No audio data received")
                return
        else:
            message_text = data.get("text", "")

        print(f"📝 Processing message text: '{message_text[:100]}...'")

        # ISSUE 2: Get enhanced conversation history FIRST (last 5 messages and their replies) 
        conversation_history = DatabaseManager.get_user_message_history(db, user.id, limit=5)
        print(f"📚 Retrieved conversation history: {len(conversation_history)} messages")
        
        # Print the complete conversation history content
        if conversation_history:
            print(f"💬 Complete Conversation History:")
            print(f"   {'='*60}")
            for i, msg in enumerate(conversation_history, 1):
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')
                timestamp = msg.get('timestamp', 'N/A')
                language = msg.get('language', 'N/A')
                print(f"   {i}. [{role.upper()}] ({timestamp}) [{language}]")
                print(f"      Content: {content}")
                print(f"      {'-'*50}")
        else:
            print(f"💬 No previous conversation history found")
        
        # Also get formatted conversation string for LLM context
        formatted_conversation = DatabaseManager.get_formatted_conversation_for_llm(db, user.id, limit=5)
        if formatted_conversation != "No previous conversation history.":
            print(f"🔤 Formatted conversation for LLM:")
            print(f"   {formatted_conversation}")
            print(f"   {'='*60}")
        else:
            print(f"🔤 No formatted conversation history")

        # Create user message record with Wati message ID
        user_message = DatabaseManager.create_message(
            db,
            user_id=user.id,
            content=message_text,
            wati_message_id=wati_message_id
        )

        # Check if we already replied to this mesFsage (prevent double replies)
        existing_reply = db.query(BotReply).filter_by(message_id=user_message.id).first()
        if existing_reply:
            print(f"🔄 Already replied to message {user_message.id}. Skipping to prevent double reply.")
            return

        # 🚀 STEP 1: First, try the embedding agent to find similar questions in knowledge base
        print(f"🎯 Starting embedding agent processing...")
        
        # Quick language detection for embedding agent
        temp_language = language_handler.detect_language(message_text)
        
        embedding_result = await embedding_agent.process_message(
            user_message=message_text,
            conversation_history=conversation_history,
            user_language=temp_language
        )
        
        print(f"🎯 Embedding agent result: {embedding_result['action']} (confidence: {embedding_result['confidence']:.3f})")
        
        if embedding_result['action'] == 'reply':
            # Found a good match in knowledge base - use it directly
            response_text = embedding_result['response']
            detected_language = temp_language
            classified_message_type = MessageType.OTHERS  # Use existing enum value
            
            print(f"✅ Using embedding agent response: '{response_text[:50]}...'")
            print(f"📝 Matched question: '{embedding_result['matched_question'][:50]}...'")
            
            # Store the detected language in session context
            context = json.loads(session.context) if session.context else {}
            context['language'] = detected_language
            session.context = json.dumps(context)
            
            # Skip to response sending
            user_message.language = detected_language
            db.commit()
            
        elif embedding_result['action'] == 'skip':
            # Message doesn't need a reply (emotions, ok, etc.)
            print(f"🚫 Embedding agent determined no reply needed")
            return
            
        else:
            # Continue to classification agent
            print(f"🔄 Embedding agent passed to classification agent")
            
            # Check if user is allowed to access other agents
            if not is_allowed_user:
                print(f"🔒 Non-allowed user cannot access other agents - no response sent")
                return
            
            # Classify message and detect language WITH conversation history
            classified_message_type, detected_language = await message_classifier.classify_message(
                message_text, db, user_message, conversation_history
            )
            
            print(f"🧠 Message classified as: {classified_message_type} in language: {detected_language}")
            
            # Store the detected language in session context
            context = json.loads(session.context) if session.context else {}
            context['language'] = detected_language
            session.context = json.dumps(context)
            
            # Route message to appropriate handler based on classification
            response_text = None
            
            if classified_message_type == MessageType.GREETING:
                # Send greetings directly to LLM for natural response
                print(f"👋 Sending GREETING directly to LLM")
                
                # Build a simple greeting prompt
                if detected_language == 'ar':
                    greeting_prompt = f"""أنت موظف خدمة عملاء في شركة أبار لتوصيل المياه في السعودية.
رد على التحية التالية بطريقة طبيعية وودودة تماماً كما يرد أي موظف خدمة عملاء حقيقي:

رسالة العميل: {message_text}

ملاحظات مهمة:
- رد بطريقة طبيعية وإنسانية تماماً 
- لا تستخدم عبارات مثل "رد الذكاء الاصطناعي" أو "رد المساعد"
- اجعل الرد قصير وودود
- يمكنك أن تسأل كيف يمكنك مساعدته اليوم"""
                else:
                    greeting_prompt = f"""You are a customer service employee at Abar Water Delivery Company in Saudi Arabia.
Respond to the following greeting in a natural and friendly way, exactly like a real customer service employee would:

Customer message: {message_text}

Important notes:
- Respond naturally and humanly
- Don't use phrases like "AI response" or "Assistant reply"  
- Keep the response short and friendly
- You can ask how you can help them today"""
                
                response_text = await language_handler.process_with_openai(greeting_prompt)
                
            elif classified_message_type == MessageType.COMPLAINT:
                # Handle complaints with default response
                print(f"📝 Handling COMPLAINT with default response")
                response_text = message_classifier.get_default_response(classified_message_type, detected_language)
                
            elif classified_message_type == MessageType.THANKING:
                # Send thanking directly to LLM for natural response
                print(f"🙏 Sending THANKING directly to LLM")
                
                # Build a simple thanking response prompt
                if detected_language == 'ar':
                    thanking_prompt = f"""أنت موظف خدمة عملاء في شركة أبار لتوصيل المياه في السعودية.
رد على رسالة الشكر التالية بطريقة طبيعية وودودة تماماً كما يرد أي موظف خدمة عملاء حقيقي:

رسالة العميل: {message_text}

ملاحظات مهمة:
- رد بطريقة طبيعية وإنسانية تماماً
- لا تستخدم عبارات مثل "رد الذكاء الاصطناعي" أو "رد المساعد"
- اجعل الرد قصير ومناسب
- يمكنك أن تسأل إذا كان يحتاج أي مساعدة أخرى"""
                else:
                    thanking_prompt = f"""You are a customer service employee at Abar Water Delivery Company in Saudi Arabia.
Respond to the following thank you message in a natural and friendly way, exactly like a real customer service employee would:

Customer message: {message_text}

Important notes:
- Respond naturally and humanly  
- Don't use phrases like "AI response" or "Assistant reply"
- Keep the response short and appropriate
- You can ask if they need any other assistance"""
                
                response_text = await language_handler.process_with_openai(thanking_prompt)
                
            elif classified_message_type == MessageType.SUGGESTION:
                # Handle suggestions with default response
                print(f"💡 Handling SUGGESTION with default response")
                response_text = message_classifier.get_default_response(classified_message_type, detected_language)
                
            elif classified_message_type == MessageType.INQUIRY:
                # Send inquiries to query agent
                print(f"🔍 Sending INQUIRY to query agent")
                response_text = await query_agent.process_query(
                    user_message=message_text,
                    conversation_history=conversation_history,
                    user_language=detected_language
                )
                
            elif classified_message_type == MessageType.SERVICE_REQUEST:
                # Send service requests to service agent
                print(f"🛠️ Sending SERVICE_REQUEST to service agent")
                response_text = await service_request_agent.process_service_request(
                    user_message=message_text,
                    conversation_history=conversation_history,
                    user_language=detected_language
                )
                
            elif classified_message_type == MessageType.TEMPLATE_REPLY:
                # Send template replies to query agent for context-aware processing
                print(f"🔘 Sending TEMPLATE_REPLY to query agent")
                response_text = await query_agent.process_query(
                    user_message=message_text,
                    conversation_history=conversation_history,
                    user_language=detected_language
                )
                
            else:
                # Fallback for unclassified or OTHER messages - send to query agent
                print(f"❓ Sending unclassified/OTHER message to query agent")
                response_text = await query_agent.process_query(
                    user_message=message_text,
                    conversation_history=conversation_history,
                    user_language=detected_language
                )
        
        # Check if we have a response to send
        if not response_text:
            print(f"🔇 No response generated - skipping message sending")
            return
        

        if response_text and response_text.startswith("bot: "):
            response_text = response_text[5:]  # Remove "bot: " prefix
        elif response_text and response_text.startswith("bot:"):
            response_text = response_text[4:]  # Remove "bot:" prefix
        
        user_type = "ALLOWED" if is_allowed_user else "RESTRICTED"
        print(f"📤 Sending response for {classified_message_type or 'UNKNOWN'} ({user_type} user) in {detected_language}: {response_text[:50]}...")

        # Create bot reply record with language (prevent double replies)
        DatabaseManager.create_bot_reply(
            db,
            message_id=user_message.id,
            content=response_text,
            language=detected_language
        )

        # Commit before sending message to ensure duplicate prevention works
        db.commit()
        print(f"💾 Message and reply saved to database")

        # Send response via WhatsApp
        result = await send_whatsapp_message(phone_number, response_text)
        print(f"✅ Response sent to {phone_number}: {response_text[:100]}...")

    except Exception as e:
        print(f"[Async Message Processing ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        # Always close the database session
        db.close()
        print(f"🔄 Async processing completed for message {wati_message_id}")

async def send_whatsapp_message(phone_number: str, message: str):
    """Send message through Wati API"""
    wati_api_key = os.getenv("WATI_API_KEY")
    
    # Check for both possible environment variable names
    wati_api_url = os.getenv("WATI_API_URL") or os.getenv("WATI_INSTANCE_ID")
    
    # If neither is set, use the user's default URL
    if not wati_api_url:
        wati_api_url = "https://live-mt-server.wati.io/301269/api/v1"
        print(f"💡 Using default Wati URL: {wati_api_url}")
    
    # Check if Wati configuration is complete
    if not wati_api_key:
        error_msg = "WATI_API_KEY environment variable is not set"
        print(f"❌ [Wati Config Error] {error_msg}")
        return {"error": error_msg}
    
    # Clean up the URL if it doesn't end with /api/v1
    if not wati_api_url.endswith('/api/v1'):
        if wati_api_url.endswith('/'):
            wati_api_url = wati_api_url + 'api/v1'
        else:
            wati_api_url = wati_api_url + '/api/v1'
    
    try:
        print(f"📤 Sending WhatsApp message to {phone_number}")
        print(f"🔗 Using Wati API URL: {wati_api_url}")
        
        # URL encode the message to handle special characters
        encoded_message = urllib.parse.quote(message)
        
        # Use sendSessionMessage endpoint as shown in working examples
        send_url = f"{wati_api_url}/sendSessionMessage/{phone_number}?messageText={encoded_message}"
        
        print(f"📡 Request URL: {send_url[:80]}...")  # Show partial URL for debugging
        
        # Headers based on working examples
        headers = {
            "Authorization": f"Bearer {wati_api_key}",
            "Content-Type": "application/json",
            "accept": "*/*",
            "accept-language": "en-GB,en;q=0.9,ar-EG;q=0.8,ar;q=0.7,en-US;q=0.6",
            "origin": "https://live.wati.io",
            "referer": "https://live.wati.io/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
        }
        
        # Empty payload as message is in URL (as per working examples)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                send_url,
                headers=headers,
                data={}  # Empty payload
            ) as response:
                if response.status == 200:
                    print(f"✅ Message sent successfully to {phone_number}")
                    # Try to parse JSON response, but handle if it's not JSON
                    try:
                        result = await response.json()
                    except:
                        result = {"status": "success", "text": await response.text()}
                else:
                    print(f"⚠️ Wati API returned status {response.status}")
                    response_text = await response.text()
                    print(f"Response: {response_text}")
                    
                    # Try alternative endpoints if primary fails
                    print("🔄 Trying alternative endpoint...")
                    alt_url = f"{wati_api_url}/sendMessage?whatsappNumber={phone_number}&messageText={encoded_message}"
                    async with session.post(alt_url, headers=headers, data={}) as alt_response:
                        if alt_response.status == 200:
                            print(f"✅ Alternative endpoint successful!")
                            try:
                                result = await alt_response.json()
                            except:
                                result = {"status": "success", "text": await alt_response.text()}
                        else:
                            print(f"❌ Alternative endpoint also failed: {alt_response.status}")
                            result = {"error": f"HTTP {response.status}", "response": response_text}
                
                return result
                
    except Exception as e:
        error_msg = f"Failed to send WhatsApp message: {str(e)}"
        print(f"❌ [Wati API Error] {error_msg}")
        return {"error": error_msg}

# Direct client message endpoint
@app.post("/send-message")
async def send_message(request: Request, db=Depends(get_db)):
    """
    Endpoint for directly sending messages to clients.
    Expects JSON with phone_number and message fields.
    """
    try:
        data = await request.json()
        phone_number = data.get("phone_number")
        message = data.get("message")
        
        if not phone_number or not message:
            raise HTTPException(status_code=400, detail="Phone number and message are required")
        
        # Send to WhatsApp directly
        result = await send_whatsapp_message(phone_number, message)
        return {"status": "success", "result": result}
    
    except Exception as e:
        print(f"[Send Message ERROR] {str(e)}")
        return {"status": "error", "message": str(e)}

# Data Scraping and Management Endpoints
@app.post("/data/sync")
async def manual_data_sync():
    """Manually trigger a full data sync"""
    try:
        result = scheduler.run_manual_sync()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/data/sync/status")
async def get_sync_status():
    """Get the status of the data sync scheduler"""
    return scheduler.get_scheduler_status()

@app.post("/data/sync/start")
async def start_scheduler(daily_time: str = "02:00"):
    """Start the data sync scheduler"""
    try:
        scheduler.start_scheduler(daily_time)
        return {"status": "success", "message": f"Scheduler started with daily sync at {daily_time}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/data/sync/stop")
async def stop_scheduler():
    """Stop the data sync scheduler"""
    try:
        scheduler.stop_scheduler()
        return {"status": "success", "message": "Scheduler stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Internal Data API Endpoints
@app.get("/api/cities")
async def get_cities(search: str = None, db=Depends(get_db)):
    """Get all cities or search cities by name"""
    try:
        if search:
            cities = data_api.search_cities(db, search)
        else:
            cities = data_api.get_all_cities(db)
        return {"success": True, "data": cities}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/cities/search")
async def search_cities(q: str, db=Depends(get_db)):
    """Search cities by name"""
    try:
        cities = data_api.search_cities(db, q)
        return {"success": True, "data": cities}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/cities/{city_id}")
async def get_city(city_id: int, db=Depends(get_db)):
    """Get a specific city by ID"""
    city = data_api.get_city_by_id(db, city_id)
    if not city:
        raise HTTPException(status_code=404, detail="City not found")
    return {"success": True, "data": city}

@app.get("/api/cities/{city_id}/brands")
async def get_city_brands(city_id: int, db=Depends(get_db)):
    """Get all brands for a specific city"""
    try:
        brands = data_api.get_brands_by_city(db, city_id)
        return {"success": True, "data": brands}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/cities/{city_id}/full")
async def get_city_with_brands_products(city_id: int, db=Depends(get_db)):
    """Get a city with all its brands and products"""
    city_data = data_api.get_city_with_brands_and_products(db, city_id)
    if not city_data:
        raise HTTPException(status_code=404, detail="City not found")
    return {"success": True, "data": city_data}

@app.get("/api/brands")
async def get_brands(search: str = None, db=Depends(get_db)):
    """Get all brands or search brands by title"""
    try:
        if search:
            brands = data_api.search_brands(db, search)
        else:
            brands = data_api.get_all_brands(db)
        return {"success": True, "data": brands}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/brands/{brand_id}")
async def get_brand(brand_id: int, db=Depends(get_db)):
    """Get a specific brand by ID"""
    brand = data_api.get_brand_by_id(db, brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    return {"success": True, "data": brand}

@app.get("/api/brands/{brand_id}/products")
async def get_brand_products(brand_id: int, db=Depends(get_db)):
    """Get all products for a specific brand"""
    try:
        products = data_api.get_products_by_brand(db, brand_id)
        return {"success": True, "data": products}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/brands/{brand_id}/full")
async def get_brand_with_products(brand_id: int, db=Depends(get_db)):
    """Get a brand with all its products"""
    brand_data = data_api.get_brand_with_products(db, brand_id)
    if not brand_data:
        raise HTTPException(status_code=404, detail="Brand not found")
    return {"success": True, "data": brand_data}

@app.get("/api/products")
async def get_products(search: str = None, db=Depends(get_db)):
    """Get all products or search products by title/barcode"""
    try:
        if search:
            products = data_api.search_products(db, search)
        else:
            products = data_api.get_all_products(db)
        return {"success": True, "data": products}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/products/search")
async def search_products(q: str, db=Depends(get_db)):
    """Search products by name or keyword"""
    try:
        products = data_api.search_products(db, q)
        return {"success": True, "data": products}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/products/{product_id}")
async def get_product(product_id: int, db=Depends(get_db)):
    """Get a specific product by ID"""
    product = data_api.get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"success": True, "data": product}

# Knowledge management endpoints
@app.post("/knowledge/add")
async def add_knowledge(request: Request):
    """Add a question-answer pair to the knowledge base with duplicate checking"""
    try:
        data = await request.json()
        question = data.get("question")
        answer = data.get("answer")
        metadata = data.get("metadata", {"source": "api"})
        
        if not question or not answer:
            raise HTTPException(status_code=400, detail="Question and answer are required")
        
        # Add Q&A pair with duplicate checking
        result = knowledge_manager.add_qa_pair(question, answer, metadata)
        
        if result["success"]:
            return {
                "status": "success", 
                "id": result.get("id"),
                "message": result.get("message", "Q&A pair added successfully"),
                "added_count": result.get("added_count", 1),
                "skipped_count": result.get("skipped_count", 0)
            }
        else:
            if "duplicate" in result.get("error", "").lower():
                return {
                    "status": "warning",
                    "message": "Question already exists in the knowledge base",
                    "error": result["error"],
                    "duplicate_info": result.get("duplicate_info"),
                    "skipped_count": result.get("skipped_count", 1)
                }
            else:
                raise HTTPException(status_code=400, detail=result["error"])
                
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Knowledge Add ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/knowledge/check-duplicate")
async def check_duplicate_knowledge(request: Request):
    """Check if a question already exists in the knowledge base"""
    try:
        data = await request.json()
        question = data.get("question")
        similarity_threshold = data.get("similarity_threshold", 0.85)
        
        if not question:
            raise HTTPException(status_code=400, detail="Question is required")
        
        duplicate = knowledge_manager.check_duplicate(question, similarity_threshold)
        
        if duplicate:
            return {
                "status": "duplicate_found",
                "duplicate": True,
                "existing_question": duplicate["document"],
                "similarity": duplicate.get("cosine_similarity", 0),
                "metadata": duplicate.get("metadata", {})
            }
        else:
            return {
                "status": "no_duplicate",
                "duplicate": False,
                "message": "No duplicate found, safe to add"
            }
            
    except Exception as e:
        print(f"[Knowledge Check Duplicate ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/knowledge/search")
async def search_knowledge(query: str, n_results: int = 3):
    """Search the knowledge base"""
    try:
        results = knowledge_manager.search_knowledge(query, n_results)
        return {"status": "success", "results": results, "total": len(results)}
    except Exception as e:
        print(f"[Knowledge Search ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/knowledge/stats")
async def get_knowledge_stats():
    """Get knowledge base statistics"""
    try:
        stats_result = knowledge_manager.get_knowledge_stats()
        if stats_result["success"]:
            return {"status": "success", "stats": stats_result["stats"]}
        else:
            raise HTTPException(status_code=500, detail=stats_result["error"])
    except Exception as e:
        print(f"[Knowledge Stats ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/knowledge/populate")
async def populate_knowledge():
    """
    Populate the knowledge base with default Abar-specific QA pairs
    """
    try:
        print("🚀 API: Starting knowledge base population...")
        result = knowledge_manager.populate_abar_knowledge()
        
        if result["success"]:
            return {
                "status": "success", 
                "message": result["message"],
                "added_count": result["added_count"],
                "skipped_count": result["skipped_count"],
                "added_ids": result["added_ids"],
                "skipped_duplicates": result.get("skipped_duplicates", [])
            }
        else:
            raise HTTPException(status_code=500, detail=result["error"])
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error populating knowledge: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/knowledge/admin", response_class=HTMLResponse)
async def knowledge_admin_page(request: Request):
    """
    Serve the knowledge base admin interface (protected route)
    """
    if not check_authentication(request):
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("knowledge_admin.html", {"request": request})

@app.get("/knowledge/list")
async def list_knowledge():
    """
    List all Q&A pairs in the knowledge base
    """
    try:
        # Get all items from the vector database
        from vectorstore.chroma_db import chroma_manager
        
        # Query with a broad search to get all items
        results = chroma_manager.get_collection_safe().get()
        
        items = []
        if results and results.get("documents"):
            for i, doc in enumerate(results["documents"]):
                metadata = results["metadatas"][i] if results.get("metadatas") else {}
                item_id = results["ids"][i] if results.get("ids") else str(i)
                
                # Skip question documents, only show answers
                if metadata.get("type") == "question":
                    continue
                    
                # Try to find the corresponding question
                question = "سؤال غير متوفر"
                question_id = f"q_{item_id}"
                try:
                    question_results = chroma_manager.get_collection_safe().get(ids=[question_id])
                    if question_results and question_results.get("documents"):
                        question = question_results["documents"][0]
                except:
                    pass
                
                items.append({
                    "id": item_id,
                    "question": question,
                    "answer": doc,
                    "metadata": metadata
                })
        
        return {
            "status": "success",
            "items": items,
            "total": len(items)
        }
    except Exception as e:
        print(f"Error listing knowledge: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/knowledge/update")
async def update_knowledge(request: Request):
    """
    Update an existing Q&A pair
    """
    try:
        data = await request.json()
        qa_id = data.get("id")
        question = data.get("question")
        answer = data.get("answer")
        metadata = data.get("metadata", {})
        
        if not qa_id or not question or not answer:
            raise HTTPException(status_code=400, detail="Missing required fields")
        
        from vectorstore.chroma_db import chroma_manager
        
        # Update the answer document
        chroma_manager.get_collection_safe().update(
            ids=[qa_id],
            documents=[answer],
            metadatas=[metadata]
        )
        
        # Update the question document
        question_id = f"q_{qa_id}"
        question_metadata = {"answer_id": qa_id, "type": "question", **metadata}
        try:
            chroma_manager.get_collection_safe().update(
                ids=[question_id],
                documents=[question],
                metadatas=[question_metadata]
            )
        except:
            # If question doesn't exist, create it
            chroma_manager.get_collection_safe().add(
                ids=[question_id],
                documents=[question],
                metadatas=[question_metadata]
            )
        
        return {
            "status": "success",
            "message": "Q&A pair updated successfully",
            "id": qa_id
        }
    except Exception as e:
        print(f"Error updating knowledge: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/knowledge/delete/{qa_id}")
async def delete_knowledge(qa_id: str):
    """
    Delete a Q&A pair from the knowledge base
    """
    try:
        from vectorstore.chroma_db import chroma_manager
        
        # Delete the answer document
        chroma_manager.get_collection_safe().delete(ids=[qa_id])
        
        # Delete the question document
        question_id = f"q_{qa_id}"
        try:
            chroma_manager.get_collection_safe().delete(ids=[question_id])
        except:
            pass  # Question might not exist
        
        return {
            "status": "success",
            "message": "Q&A pair deleted successfully",
            "id": qa_id
        }
    except Exception as e:
        print(f"Error deleting knowledge: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# User management endpoints
@app.post("/user/update-conclusion")
async def update_user_conclusion(request: Request, db=Depends(get_db)):
    """Update user conclusion"""
    try:
        data = await request.json()
        phone_number = data.get("phone_number")
        conclusion = data.get("conclusion")
        
        if not phone_number or not conclusion:
            raise HTTPException(status_code=400, detail="Phone number and conclusion are required")
        
        # Get or create user
        user = DatabaseManager.get_user_by_phone(db, phone_number)
        if not user:
            user = DatabaseManager.create_user(db, phone_number)
        
        # Update conclusion
        DatabaseManager.update_user_conclusion(db, user.id, conclusion)
        return {"status": "success", "user_id": user.id}
    except Exception as e:
        print(f"[Update User ERROR] {str(e)}")
        return {"status": "error", "message": str(e)}

# API health check endpoint
@app.get("/health")
async def health_check():
    """Check if the API is running"""
    return {"status": "healthy", "version": "1.0.0"}

# Model cache management endpoints
@app.get("/models/cache/info")
async def get_model_cache_info():
    """Get information about cached embedding models"""
    try:
        from vectorstore.model_cache import model_cache
        cache_info = model_cache.get_cache_info()
        return {"status": "success", "cache_info": cache_info}
    except Exception as e:
        print(f"[Model Cache INFO ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/models/cache/preload")
async def preload_models():
    """Pre-load all embedding models used by the application"""
    try:
        from vectorstore.model_cache import model_cache
        
        models_to_preload = [
            "mohamed2811/Muffakir_Embedding_V2",  # Arabic model
            "all-MiniLM-L6-v2"  # Lightweight model
        ]
        
        results = []
        for model_name in models_to_preload:
            try:
                model = model_cache.load_model(model_name)
                results.append({"model": model_name, "status": "loaded", "cached": True})
            except Exception as e:
                results.append({"model": model_name, "status": "error", "error": str(e)})
        
        cache_info = model_cache.get_cache_info()
        return {
            "status": "success", 
            "message": "Model preloading completed",
            "results": results,
            "cache_info": cache_info
        }
    except Exception as e:
        print(f"[Model Preload ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Scraped Data Interface
@app.get("/server/scrapped_data", response_class=HTMLResponse)
async def scraped_data_interface(request: Request):
    """Serve the HTML interface for viewing scraped data (protected route)"""
    if not check_authentication(request):
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("scraped_data.html", {"request": request})

# Trigger initial data sync
@app.post("/server/trigger_sync")
async def trigger_initial_sync(db=Depends(get_db)):
    """Trigger initial data synchronization"""
    try:
        print("🔄 Starting initial data sync...")
        results = data_scraper.full_sync(db)
        print(f"✅ Initial sync completed: {results}")
        return {"status": "success", "message": "Data sync completed", "results": results}
    except Exception as e:
        print(f"❌ Initial sync failed: {str(e)}")
        return {"status": "error", "message": str(e)}

@app.on_event("startup")
async def startup_event():
    """Run on application startup"""
    print("Starting Abar Chatbot API...")
    
    # Initialize the data sync scheduler
    try:
        scheduler.start_scheduler("02:00")  # Start daily sync at 2 AM
        print("Data sync scheduler initialized successfully")
    except Exception as e:
        print(f"Failed to initialize scheduler: {str(e)}")
    
    # You can uncomment this to populate the knowledge base on startup
    # knowledge_manager.populate_abar_knowledge()

if __name__ == "__main__":
    print("Starting Abar Chatbot API...")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
   
