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

# Import message journey logger
from utils.message_logger import message_journey_logger

app = FastAPI(
    title="Abar Chatbot API",
    description="API for handling WhatsApp messages for Abar water delivery app",
    version="1.0.0"
)

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler to prevent app crashes"""
    print(f"🚨 Global exception: {str(exc)}")
    import traceback
    traceback.print_exc()
    
    return {
        "status": "error", 
        "message": "An unexpected error occurred", 
        "error": str(exc)
    }

# Add UTF-8 response headers for Arabic text
@app.middleware("http")
async def add_utf8_headers(request: Request, call_next):
    response = await call_next(request)
    # Ensure UTF-8 encoding for Arabic text
    if "application/json" in response.headers.get("content-type", ""):
        response.headers["content-type"] = "application/json; charset=utf-8"
    return response

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
    # Start timing the webhook processing
    webhook_start_time = time.time()
    journey_id = None
    
    try:
        data = await request.json()
        print(f"🔍 Received data: {data}")
        # Extract basic message information for logging
        phone_number = data.get("waId")
        message_text = data.get("text", "")
        wati_message_id = data.get("id")
        message_type = data.get("type", "text")
        
        # Start message journey logging
        journey_id = message_journey_logger.start_journey(
            phone_number=phone_number,
            message_text=message_text,
            wati_message_id=wati_message_id,
            message_type=message_type,
            webhook_data=data
        )
        
        # Debug: Print webhook data to understand structure
        print(f"🔍 Webhook received from: {data.get('waId', 'Unknown')}")
        print(f"   Message ID: {data.get('id', 'None')}")
        print(f"   Type: {data.get('type', 'Unknown')}")
        print(f"   Event Type: {data.get('eventType', 'None')}")
        print(f"   From Bot: {data.get('fromBot', False)}")
        print(f"   From Me: {data.get('fromMe', False)}")
        print(f"   Text: {data.get('text', 'N/A')[:100]}...")
        
        # Extract message data
        phone_number = data.get("waId")
        message_type = data.get("type", "text")  # Can be text, audio, etc.
        wati_message_id = data.get("id")  # Extract Wati message ID
        
        # 🚨 CRITICAL: Check message type and ownership to prevent infinite loops
        event_type = data.get("eventType", "")
        is_session_message_sent = event_type == "sessionMessageSent"
        
        # Handle bot/agent replies (sessionMessageSent) - save to database but don't process
        if is_session_message_sent :
            message_journey_logger.add_step(
                journey_id=journey_id,
                step_type="message_filter",
                description=f"Bot/agent reply detected: event_type={event_type}",
                data={
                    "event_type": event_type, 
                    "is_session_message_sent": is_session_message_sent
                },
                status="bot_reply"
            )
            
            # Save bot reply to database but don't process through agents
            try:
                await save_bot_reply_to_database(data, journey_id)
                message_journey_logger.complete_journey(journey_id, status="saved_bot_reply")
                print(f"💾 Bot/agent reply saved to database - Not processing through agents")
                print(f"   eventType: {event_type}, ")
            except Exception as e:
                message_journey_logger.log_error(
                    journey_id=journey_id,
                    error_type="bot_reply_save_error",
                    error_message=str(e),
                    step="save_bot_reply"
                )
                print(f"❌ Error saving bot reply: {str(e)}")
            
            return {"status": "success", "message": "Bot reply saved - not processed"}
        
        # Check if this is a template reply from WATI (button reply, list reply, etc.)
        button_reply = data.get("buttonReply")
        list_reply = data.get("listReply") 
        interactive_button_reply = data.get("interactiveButtonReply")
        
        if button_reply or list_reply or interactive_button_reply or message_type == "button":
            message_journey_logger.add_step(
                journey_id=journey_id,
                step_type="message_filter",
                description="Skipped: Template reply detected",
                data={
                    "button_reply": button_reply,
                    "list_reply": list_reply,
                    "interactive_button_reply": interactive_button_reply
                },
                status="skipped"
            )
            message_journey_logger.complete_journey(journey_id, status="skipped_template_reply")
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
            message_journey_logger.add_step(
                journey_id=journey_id,
                step_type="duplicate_check",
                description=f"Duplicate message detected: {wati_message_id}",
                data={"wati_message_id": wati_message_id},
                status="skipped"
            )
            message_journey_logger.complete_journey(journey_id, status="skipped_duplicate")
            print(f"🔄 Duplicate message detected with ID: {wati_message_id}. Returning success immediately.")
            return {"status": "success", "message": "Already processed"}
        
        # Additional check: Skip if the same message was processed recently (time-based)
        if wati_message_id:
            current_time = time.time()
            if wati_message_id in processed_messages:
                last_processed_time = processed_messages[wati_message_id]
                if current_time - last_processed_time < 30:  # 30 seconds cooldown
                    print(f"🔄 Message {wati_message_id} processed recently. Skipping to prevent spam.")
                    return {"status": "success", "message": "Recently processed"}
            
            # Track this message
            processed_messages[wati_message_id] = current_time
            
            # Clean up old entries (keep only last 1000 messages)
            if len(processed_messages) > 1000:
                old_messages = sorted(processed_messages.items(), key=lambda x: x[1])
                for msg_id, _ in old_messages[:500]:  # Remove oldest 500
                    del processed_messages[msg_id]
        
        # Log the incoming message for debugging
        print(f"📱 New message from {phone_number}: {data.get('text', 'N/A')[:50]}...")
        
        # IMMEDIATE RESPONSE: Send quick response to Wati to prevent duplicate notifications
        immediate_response = {"status": "success", "message": "Processing"}
        
        # Add journey_id to message data for tracking throughout processing
        data['journey_id'] = journey_id
        
        # Log successful webhook validation
        message_journey_logger.add_step(
            journey_id=journey_id,
            step_type="webhook_validation",
            description="Message passed webhook validation",
            data={"phone_number": phone_number, "message_type": message_type},
            duration_ms=int((time.time() - webhook_start_time) * 1000)
        )
        
        # Add message to batch instead of processing immediately
        await add_message_to_batch(phone_number, data)
        
        return immediate_response

    except Exception as e:
        # Log error in journey if journey_id exists
        if journey_id:
            message_journey_logger.log_error(
                journey_id=journey_id,
                error_type="webhook_error",
                error_message=str(e),
                step="webhook_processing",
                exception=e
            )
            message_journey_logger.complete_journey(journey_id, status="failed")
        
        print(f"[Webhook ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        # Return success even on error to prevent Wati from retrying
        return {"status": "error", "message": "Internal error occurred", "error": str(e)}

# Replace the global dictionaries with thread-safe alternatives
class ThreadSafeMessageBatcher:
    def __init__(self):
        self._batches: Dict[str, List[Dict]] = {}
        self._timers: Dict[str, asyncio.Task] = {}
        self._locks: Dict[str, asyncio.Lock] = {}  # Changed from defaultdict to regular dict
        self._last_cleanup = time.time()
    
    def _get_lock(self, phone_number: str) -> asyncio.Lock:
        """Get or create a lock for the given phone number"""
        if phone_number not in self._locks:
            self._locks[phone_number] = asyncio.Lock()
        return self._locks[phone_number]
    
    async def _cleanup_old_data(self):
        """Clean up old locks and empty batches to prevent memory leaks"""
        current_time = time.time()
        
        # Only run cleanup every 5 minutes
        if current_time - self._last_cleanup < 300:
            return
            
        self._last_cleanup = current_time
        phone_numbers_to_clean = []
        
        # Find phone numbers with no active batches or timers
        for phone_number in list(self._locks.keys()):
            has_batch = phone_number in self._batches and self._batches[phone_number]
            has_timer = phone_number in self._timers and not self._timers[phone_number].done()
            
            if not has_batch and not has_timer:
                phone_numbers_to_clean.append(phone_number)
        
        # Clean up old locks (keep only last 100 to prevent unlimited growth)
        if len(phone_numbers_to_clean) > 100:
            for phone_number in phone_numbers_to_clean[:-100]:
                if phone_number in self._locks:
                    del self._locks[phone_number]
                    print(f"🧹 Cleaned up old lock for {phone_number}")
    
    async def add_message_to_batch(self, phone_number: str, message_data: dict):
        """Add a message to user's batch with proper locking"""
        # Periodic cleanup to prevent memory leaks
        await self._cleanup_old_data()
        
        async with self._get_lock(phone_number):
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
            existing_timer = self._timers.get(phone_number)
            if existing_timer and not existing_timer.done():
                existing_timer.cancel()
                try:
                    await existing_timer
                except asyncio.CancelledError:
                    pass  # Expected when cancelling
                except Exception as e:
                    print(f"⚠️ Error cleaning up timer for {phone_number}: {e}")
            
            # Set new timer to process batch after 3 seconds of inactivity
            try:
                self._timers[phone_number] = asyncio.create_task(
                    self._process_batch_delayed(phone_number)
                )
                print(f"📦 Added message to batch for {phone_number}. Batch size: {len(self._batches[phone_number])}")
            except Exception as e:
                print(f"❌ Error creating batch timer for {phone_number}: {e}")
                # If timer creation fails, process immediately to prevent message loss
                await self.process_user_batch(phone_number)
    
    async def _process_batch_delayed(self, phone_number: str):
        """Process batch after delay"""
        try:
            await asyncio.sleep(3)  # Wait 3 seconds for more messages
            await self.process_user_batch(phone_number)
        except asyncio.CancelledError:
            print(f"🔄 Batch timer cancelled for {phone_number}")
            # Don't re-raise - timer cancellation is expected and should not interrupt processing
            return
        except Exception as e:
            print(f"❌ Error in delayed batch processing for {phone_number}: {e}")
            # Still try to process the batch to avoid message loss
            try:
                await self.process_user_batch(phone_number)
            except Exception as inner_e:
                print(f"❌ Failed to process batch after error for {phone_number}: {inner_e}")
    
    async def process_user_batch(self, phone_number: str):
        """Process all messages in user's batch as one conversation"""
        async with self._get_lock(phone_number):
            if phone_number not in self._batches or not self._batches[phone_number]:
                return
            
            batch = self._batches[phone_number]
            print(f"🔄 Processing batch of {len(batch)} messages for {phone_number}")
            
            # Clear the batch and timer first to prevent race conditions
            self._batches[phone_number] = []
            timer_task = self._timers.get(phone_number)
            if timer_task:
                timer_task.cancel()
                # Properly handle the cancelled timer to prevent CancelledError from propagating
                try:
                    await timer_task
                except asyncio.CancelledError:
                    # Expected when cancelling timer - ignore this error
                    pass
                except Exception as e:
                    print(f"⚠️ Unexpected error while cancelling timer for {phone_number}: {e}")
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
            first_message_data = batch[0]['data'].copy()  # Create a copy to avoid mutations
            first_message_data['text'] = combined_text
            first_message_data['is_batch'] = True
            first_message_data['batch_size'] = len(batch)
            first_message_data['batch_message_ids'] = wati_message_ids
            
            # Process the combined message with timeout - INSIDE the lock context
            try:
                await asyncio.wait_for(
                    process_message_async(
                        first_message_data, 
                        phone_number, 
                        first_message_data.get('type', 'text'),
                        f"batch_{phone_number}_{int(time.time())}"
                    ),
                    timeout=120  # 2 minutes timeout
                )
                print(f"✅ Successfully processed batch of {len(batch)} messages for {phone_number}")
            except asyncio.TimeoutError:
                print(f"⏰ Batch processing timed out for {phone_number} (batch size: {len(batch)})")
            except Exception as e:
                print(f"❌ Error processing batch for {phone_number} (batch size: {len(batch)}): {str(e)}")
                import traceback
                traceback.print_exc()

    async def get_stats(self) -> Dict[str, int]:
        """Get statistics about the current batching state"""
        active_batches = len([batch for batch in self._batches.values() if batch])
        active_timers = len([timer for timer in self._timers.values() if not timer.done()])
        total_locks = len(self._locks)
        
        return {
            "active_batches": active_batches,
            "active_timers": active_timers,
            "total_locks": total_locks,
            "total_users": len(self._batches)
        }

# Create thread-safe instance
message_batcher = ThreadSafeMessageBatcher()

# Initialize message tracking to prevent infinite loops
processed_messages = {}

# Remove the old global dictionaries
# user_message_batches = {}  # REMOVED
# batch_timers = {}  # REMOVED

async def add_message_to_batch(phone_number: str, message_data: dict):
    """Add a message to user's batch and set/reset timer"""
    await message_batcher.add_message_to_batch(phone_number, message_data)

async def process_user_batch(phone_number: str):
    """Process all messages in user's batch as one conversation"""
    await message_batcher.process_user_batch(phone_number)

def has_links(text: str) -> bool:
    """
    Check if text contains any URLs or links
    Returns True if links are found, False otherwise
    """
    import re
    
    # Common URL patterns
    url_patterns = [
        r'https?://[^\s]+',  # http:// or https://
        r'www\.[^\s]+',      # www.
        r'[^\s]+\.[a-zA-Z]{2,}(?:/[^\s]*)?',  # domain.com or domain.org/path
        r'[^\s]+\.(?:com|org|net|edu|gov|mil|int|co|uk|de|fr|jp|cn|ru|br|in|au|ca|mx|es|it|nl|ch|se|no|dk|fi|be|at|pl|cz|hu|gr|pt|ie|il|za|tr|kr|th|sg|my|id|ph|vn|tw|hk|nz|ar|cl|pe|ve|uy|py|bo|ec|co|cr|pa|ni|hn|gt|sv|bz|jm|tt|bb|gd|lc|vc|ag|kn|dm|bs|cu|do|ht|mx|us|ca)[^\s]*',  # More TLDs
        r'(?:^|[^a-zA-Z0-9])(?:bit\.ly|tinyurl\.com|t\.co|short\.link|go\.gl|ow\.ly|is\.gd|buff\.ly|adf\.ly|goo\.gl|tiny\.cc|lnkd\.in|short\.link|cutt\.ly|rebrand\.ly|linktr\.ee|linkin\.bio)[^\s]*',  # URL shorteners
        r'(?:^|[^a-zA-Z0-9])(?:instagram\.com|facebook\.com|twitter\.com|youtube\.com|tiktok\.com|snapchat\.com|whatsapp\.com|telegram\.me|t\.me)[^\s]*',  # Social media
    ]
    
    for pattern in url_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    
    return False

async def save_bot_reply_to_database(data, journey_id):
    """Save bot/agent reply to database without processing through agents"""
    from database.db_utils import SessionLocal
    
    db = SessionLocal()
    try:
        phone_number = data.get("waId")
        message_text = data.get("text", "")
        wati_message_id = data.get("id")
        operator_name = data.get("operatorName", "Bot")
        operator_email = data.get("operatorEmail", "")
        
        if not phone_number or not message_text:
            print(f"⚠️ Missing phone_number or message_text for bot reply")
            return
        
        # Get or create user
        user = DatabaseManager.get_user_by_phone(db, phone_number)
        if not user:
            user = DatabaseManager.create_user(db, phone_number)
        
        # Get or create session
        session = db.query(UserSession).filter_by(user_id=user.id).first()
        if not session:
            session = UserSession(
                user_id=user.id,
                session_id=str(uuid.uuid4()),
                started_at=datetime.utcnow()
            )
            db.add(session)
        
        session.last_activity = datetime.utcnow()
        
        # Find the most recent user message to link this reply to
        recent_message = DatabaseManager.get_most_recent_user_message(db, user.id)
        
        if recent_message:
            # Check if we already have a reply for this message
            existing_reply = db.query(BotReply).filter_by(message_id=recent_message.id).first()
            
            if not existing_reply:
                # Create new bot reply record
                bot_reply = DatabaseManager.create_bot_reply(
                    db,
                    message_id=recent_message.id,
                    content=message_text,
                    language="ar"  # Default to Arabic, could be improved with language detection
                )
                
                # Note: operator info available but not stored in current schema
                # operator_name: {operator_name}, operator_email: {operator_email}
                
                message_journey_logger.log_database_operation(
                    journey_id=journey_id,
                    operation="create_bot_reply",
                    table="bot_replies",
                    details={
                        "reply_id": bot_reply.id,
                        "message_id": recent_message.id,
                        "operator": operator_name,
                        "text_length": len(message_text)
                    }
                )
                
                print(f"💾 Bot reply saved: {operator_name} -> {phone_number}")
                
            else:
                print(f"📝 Bot reply already exists for message {recent_message.id}")
        else:
            print(f"⚠️ No recent user message found to link bot reply to")
        
        db.commit()
        
    except Exception as e:
        print(f"❌ Error saving bot reply to database: {str(e)}")
        db.rollback()
        raise e
    finally:
        db.close()

async def process_message_async(data, phone_number, message_type, wati_message_id):
    """Process the message asynchronously after responding to Wati"""
    # Extract journey_id from data or create a new one if missing
    journey_id = data.get('journey_id')
    if not journey_id:
        # Fallback: create journey if not provided (for backward compatibility)
        journey_id = message_journey_logger.start_journey(
            phone_number=phone_number,
            message_text=data.get('text', ''),
            wati_message_id=wati_message_id,
            message_type=message_type,
            webhook_data=data
        )
    
    # Start timing the async processing
    async_start_time = time.time()
    
    # Create a new database session for async processing
    from database.db_utils import SessionLocal
    db = SessionLocal()
    
    try:
        message_journey_logger.add_step(
            journey_id=journey_id,
            step_type="async_processing_start",
            description=f"Started async processing for {wati_message_id}",
            data={"phone_number": phone_number, "message_type": message_type}
        )
        
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
        
        # SELECTIVE ACCESS LOGIC: Determine user permissions
        # All users can access INQUIRY and SERVICE_REQUEST categories (query agent)
        # Other categories are restricted to allowed users only
        allowed_numbers = [
            "201142765209",
            "966138686475",  # 966 13 868 6475 (spaces removed)
            "966505281144",  
            "966541794866",
            "201003754330",
        ]
        
        # Normalize phone number by removing spaces and special characters
        normalized_phone = "".join(char for char in str(phone_number) if char.isdigit())
        
        # Check if user is in allowed list (for full access to all categories)
        is_allowed_user = normalized_phone in allowed_numbers
        is_test_user = normalized_phone in allowed_numbers  # For now, all allowed users are test users
        
        if is_allowed_user:
            print(f"✅ Allowed user detected: {phone_number} - Full functionality enabled")
        else:
            print(f"🔒 Regular user detected: {phone_number} - Access to INQUIRY and SERVICE_REQUEST categories only")
        
        # Get or create user session
        db_start_time = time.time()
        user = DatabaseManager.get_user_by_phone(db, phone_number)
        if not user:
            user = DatabaseManager.create_user(db, phone_number)
            message_journey_logger.log_database_operation(
                journey_id=journey_id,
                operation="create_user",
                table="users",
                details={"phone_number": phone_number, "user_id": user.id}
            )
        
        session = db.query(UserSession).filter_by(user_id=user.id).first()
        if not session:
            session = UserSession(
                user_id=user.id,
                session_id=str(uuid.uuid4()),
                started_at=datetime.utcnow()
            )
            db.add(session)
        
        session.last_activity = datetime.utcnow()
        
        # Log user and session setup
        message_journey_logger.log_database_operation(
            journey_id=journey_id,
            operation="get_or_create_session",
            table="user_sessions",
            details={"user_id": user.id, "is_allowed_user": is_allowed_user},
            duration_ms=int((time.time() - db_start_time) * 1000)
        )
        
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

        # Check for links in the message and skip processing if found
        if message_text and has_links(message_text):
            print(f"🔗 Message contains links - skipping processing to prevent spam/harmful content")
            return

        # ISSUE 2: Get enhanced conversation history FIRST (last 5 messages and their replies) 
        history_start_time = time.time()
        conversation_history = DatabaseManager.get_user_message_history(db, user.id, limit=5)
        
        message_journey_logger.log_database_operation(
            journey_id=journey_id,
            operation="get_message_history",
            table="user_messages",
            details={"user_id": user.id, "history_count": len(conversation_history)},
            duration_ms=int((time.time() - history_start_time) * 1000)
        )
        
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
        create_msg_start_time = time.time()
        user_message = DatabaseManager.create_message(
            db,
            user_id=user.id,
            content=message_text,
            wati_message_id=wati_message_id
        )
        
        message_journey_logger.log_database_operation(
            journey_id=journey_id,
            operation="create_message",
            table="user_messages",
            details={
                "message_id": user_message.id,
                "user_id": user.id,
                "message_length": len(message_text),
                "wati_message_id": wati_message_id
            },
            duration_ms=int((time.time() - create_msg_start_time) * 1000)
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
        
        embedding_start_time = time.time()
        embedding_result = await embedding_agent.process_message(
            user_message=message_text,
            conversation_history=conversation_history,
            user_language=temp_language,
            journey_id=journey_id
        )
        
        # Log embedding agent processing
        message_journey_logger.log_embedding_agent(
            journey_id=journey_id,
            user_message=message_text,
            action=embedding_result['action'],
            confidence=embedding_result['confidence'],
            matched_question=embedding_result.get('matched_question'),
            response=embedding_result.get('response'),
            duration_ms=int((time.time() - embedding_start_time) * 1000)
        )
        
        print(f"🎯 Embedding agent result: {embedding_result['action']} (confidence: {embedding_result['confidence']:.3f})")
        print(f"🔍 Full embedding result: {embedding_result}")
        
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
            message_journey_logger.add_step(
                journey_id=journey_id,
                step_type="embedding_skip",
                description="Embedding agent determined no reply needed",
                data={"reason": "no_reply_needed"}
            )
            message_journey_logger.complete_journey(journey_id, status="completed_no_reply")
            print(f"🚫 Embedding agent determined no reply needed")
            return
            
        else:
            if not is_allowed_user:
                return ""
            # Continue to classification agent
            message_journey_logger.add_step(
                journey_id=journey_id,
                step_type="embedding_continue",
                description="Embedding agent passed to classification agent",
                data={"action": "continue_to_classification"}
            )
            print(f"🔄 Embedding agent passed to classification agent")
            
            # Proceed to classification - selective access will be checked after classification
            print(f"🔄 Proceeding to classification for user: {phone_number}")
            
            # Classify message and detect language WITH conversation history
            classification_start_time = time.time()
            classified_message_type, detected_language = await message_classifier.classify_message(
                message_text, db, user_message, conversation_history
            )
            
            # Log message classification
            message_journey_logger.log_classification(
                journey_id=journey_id,
                message_text=message_text,
                classified_type=str(classified_message_type),
                detected_language=detected_language,
                duration_ms=int((time.time() - classification_start_time) * 1000)
            )
            
            print(f"🧠 Message classified as: {classified_message_type} in language: {detected_language}")
            
            # SELECTIVE ACCESS CHECK: Allow INQUIRY and SERVICE_REQUEST for all users
            # Other categories only for allowed users
            if not is_allowed_user:
                # Check if regular user is trying to access restricted categories
                restricted_categories = [
                    MessageType.GREETING, 
                    MessageType.THANKING, 
                    MessageType.COMPLAINT, 
                    MessageType.SUGGESTION,
                    MessageType.TEMPLATE_REPLY,
                    MessageType.OTHERS
                ]
                
                if classified_message_type in restricted_categories:
                    message_journey_logger.add_step(
                        journey_id=journey_id,
                        step_type="access_restriction",
                        description=f"Regular user restricted from {classified_message_type} category",
                        data={"phone_number": phone_number, "classified_type": str(classified_message_type), "is_allowed": False}
                    )
                    message_journey_logger.complete_journey(journey_id, status="completed_restricted")
                    print(f"🔒 Regular user cannot access {classified_message_type} category - no response sent")
                    return
                else:
                    print(f"✅ Regular user has access to {classified_message_type} category")
            
            # Store the detected language in session context
            context = json.loads(session.context) if session.context else {}
            context['language'] = detected_language
            session.context = json.dumps(context)
            
            # Route message to appropriate handler based on classification
            response_text = None
            #Should be removed after testing
            if classified_message_type == MessageType.SERVICE_REQUEST:
                classified_message_type = MessageType.INQUIRY
                print(f"🔍 Converting SERVICE_REQUEST to INQUIRY")
                print(f"🔍 Converting SERVICE_REQUEST to INQUIRY")
            
            if classified_message_type == MessageType.GREETING:
                # Send greetings directly to LLM for natural response
                print(f"👋 Sending GREETING directly to LLM")
                
                greeting_start_time = time.time()
                
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
                
                # Log LLM interaction for greeting
                message_journey_logger.log_llm_interaction(
                    journey_id=journey_id,
                    llm_type="openai",
                    prompt=greeting_prompt,
                    response=response_text,
                    model="gpt-4",
                    duration_ms=int((time.time() - greeting_start_time) * 1000)
                )
                
            elif classified_message_type == MessageType.COMPLAINT:
                # Handle complaints with default response
                print(f"📝 Handling COMPLAINT with default response")
                response_text = message_classifier.get_default_response(classified_message_type, detected_language)
                
            elif classified_message_type == MessageType.THANKING:
                # Send thanking directly to LLM for natural response
                print(f"🙏 Sending THANKING directly to LLM")
                
                thanking_start_time = time.time()
                
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
                
                # Log LLM interaction for thanking
                message_journey_logger.log_llm_interaction(
                    journey_id=journey_id,
                    llm_type="openai",
                    prompt=thanking_prompt,
                    response=response_text,
                    model="gpt-4",
                    duration_ms=int((time.time() - thanking_start_time) * 1000)
                )
                
            elif classified_message_type == MessageType.SUGGESTION:
                # Handle suggestions with default response
                print(f"💡 Handling SUGGESTION with default response")
                response_text = message_classifier.get_default_response(classified_message_type, detected_language)
                
            elif classified_message_type == MessageType.INQUIRY:
                # Send inquiries to query agent
                print(f"🔍 Sending INQUIRY to query agent")
                inquiry_start_time = time.time()
                response_text = await query_agent.process_query(
                    user_message=message_text,
                    conversation_history=conversation_history,
                    user_language=detected_language,
                    journey_id=journey_id
                )
                
                message_journey_logger.log_agent_processing(
                    journey_id=journey_id,
                    agent_name="query_agent",
                    action="process_inquiry",
                    input_data={"message_type": "INQUIRY", "language": detected_language},
                    output_data={"response_length": len(response_text) if response_text else 0},
                    duration_ms=int((time.time() - inquiry_start_time) * 1000)
                )
                
            elif classified_message_type == MessageType.SERVICE_REQUEST:
                # Send service requests to service agent
                print(f"🛠️ Sending SERVICE_REQUEST to service agent")
                service_start_time = time.time()
                response_text = await service_request_agent.process_service_request(
                    user_message=message_text,
                    conversation_history=conversation_history,
                    user_language=detected_language
                )
                
                message_journey_logger.log_agent_processing(
                    journey_id=journey_id,
                    agent_name="service_request_agent",
                    action="process_service_request",
                    input_data={"message_type": "SERVICE_REQUEST", "language": detected_language},
                    output_data={"response_length": len(response_text) if response_text else 0},
                    duration_ms=int((time.time() - service_start_time) * 1000)
                )
                
            elif classified_message_type == MessageType.TEMPLATE_REPLY:
                # Send template replies to query agent for context-aware processing
                print(f"🔘 Sending TEMPLATE_REPLY to query agent")
                template_start_time = time.time()
                response_text = await query_agent.process_query(
                    user_message=message_text,
                    conversation_history=conversation_history,
                    user_language=detected_language,
                    journey_id=journey_id
                )
                
                message_journey_logger.log_agent_processing(
                    journey_id=journey_id,
                    agent_name="query_agent",
                    action="process_template_reply",
                    input_data={"message_type": "TEMPLATE_REPLY", "language": detected_language},
                    output_data={"response_length": len(response_text) if response_text else 0},
                    duration_ms=int((time.time() - template_start_time) * 1000)
                )
                
            else:
                # Fallback for unclassified or OTHER messages - send to query agent
                print(f"❓ Sending unclassified/OTHER message to query agent")
                fallback_start_time = time.time()
                response_text = await query_agent.process_query(
                    user_message=message_text,
                    conversation_history=conversation_history,
                    user_language=detected_language,
                    journey_id=journey_id
                )
                
                message_journey_logger.log_agent_processing(
                    journey_id=journey_id,
                    agent_name="query_agent",
                    action="process_fallback",
                    input_data={"message_type": "OTHER/FALLBACK", "language": detected_language},
                    output_data={"response_length": len(response_text) if response_text else 0},
                    duration_ms=int((time.time() - fallback_start_time) * 1000)
                )
        
        # Check if we have a response to send
        if not response_text:
            message_journey_logger.add_step(
                journey_id=journey_id,
                step_type="response_check",
                description="No response generated - skipping message sending",
                status="skipped"
            )
            message_journey_logger.complete_journey(journey_id, status="completed_no_response")
            print(f"🔇 No response generated - skipping message sending")
            return
        

        if response_text and response_text.startswith("bot: "):
            response_text = response_text[5:]  # Remove "bot: " prefix
        elif response_text and response_text.startswith("bot:"):
            response_text = response_text[4:]  # Remove "bot:" prefix
        
        user_type = "ALLOWED" if is_allowed_user else "REGULAR"
        print(f"📤 Sending response for {classified_message_type or 'UNKNOWN'} ({user_type} user) in {detected_language}: {response_text[:50]}...")

        # Log the final response preparation
        message_journey_logger.add_step(
            journey_id=journey_id,
            step_type="response_preparation",
            description=f"Prepared final response for {classified_message_type}",
            data={
                "response_length": len(response_text),
                "detected_language": detected_language,
                "user_type": "ALLOWED" if is_allowed_user else "REGULAR"
            }
        )

        # Create bot reply record with language (prevent double replies)
        reply_save_start_time = time.time()
        bot_reply = DatabaseManager.create_bot_reply(
            db,
            message_id=user_message.id,
            content=response_text,
            language=detected_language
        )

        # Commit before sending message to ensure duplicate prevention works
        db.commit()
        
        message_journey_logger.log_database_operation(
            journey_id=journey_id,
            operation="create_bot_reply",
            table="bot_replies",
            details={
                "reply_id": bot_reply.id,
                "message_id": user_message.id,
                "response_length": len(response_text),
                "language": detected_language
            },
            duration_ms=int((time.time() - reply_save_start_time) * 1000)
        )
        
        print(f"💾 Message and reply saved to database")

        # Send response via WhatsApp with timeout
        whatsapp_start_time = time.time()
        try:
            result = await asyncio.wait_for(
                send_whatsapp_message(phone_number, response_text),
                timeout=30  # 30 seconds timeout
            )
            
            # Log successful WhatsApp send
            message_journey_logger.log_whatsapp_send(
                journey_id=journey_id,
                phone_number=phone_number,
                message=response_text,
                status="success",
                response_data=result,
                duration_ms=int((time.time() - whatsapp_start_time) * 1000)
            )
            
            # Complete the journey successfully
            message_journey_logger.complete_journey(journey_id, final_response=response_text, status="completed")
            
            print(f"✅ Response sent to {phone_number}: {response_text[:100]}...")
        except asyncio.TimeoutError:
            message_journey_logger.log_whatsapp_send(
                journey_id=journey_id,
                phone_number=phone_number,
                message=response_text,
                status="timeout",
                error="WhatsApp message sending timed out",
                duration_ms=int((time.time() - whatsapp_start_time) * 1000)
            )
            message_journey_logger.complete_journey(journey_id, final_response=response_text, status="completed_with_timeout")
            print(f"⏰ WhatsApp message sending timed out for {phone_number}")
        except Exception as e:
            message_journey_logger.log_whatsapp_send(
                journey_id=journey_id,
                phone_number=phone_number,
                message=response_text,
                status="failed",
                error=str(e),
                duration_ms=int((time.time() - whatsapp_start_time) * 1000)
            )
            message_journey_logger.complete_journey(journey_id, final_response=response_text, status="completed_with_error")
            print(f"❌ Error sending WhatsApp message to {phone_number}: {str(e)}")

    except Exception as e:
        # Log the error in the journey
        message_journey_logger.log_error(
            journey_id=journey_id,
            error_type="async_processing_error",
            error_message=str(e),
            step="message_processing",
            exception=e
        )
        message_journey_logger.complete_journey(journey_id, status="failed")
        
        print(f"[Async Message Processing ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        # Log final processing completion
        total_processing_time = int((time.time() - async_start_time) * 1000)
        message_journey_logger.add_step(
            journey_id=journey_id,
            step_type="processing_complete",
            description=f"Async processing completed for {wati_message_id}",
            data={"total_processing_time_ms": total_processing_time},
            duration_ms=total_processing_time
        )
        
        # Clean up old journeys (only occasionally to avoid overhead)
        if hash(journey_id) % 100 == 0:  # Run cleanup 1% of the time
            message_journey_logger.cleanup_old_journeys()
        
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
        print(f"🔤 Original message: {message}")
        
        # URL encode the message to handle special characters, including Arabic
        encoded_message = urllib.parse.quote(message, safe='', encoding='utf-8')
        
        # Use sendSessionMessage endpoint as shown in working examples
        send_url = f"{wati_api_url}/sendSessionMessage/{phone_number}?messageText={encoded_message}"
        
        print(f"📡 Request URL: {send_url[:80]}...")  # Show partial URL for debugging
        
        # Headers based on working examples with proper UTF-8 support
        headers = {
            "Authorization": f"Bearer {wati_api_key}",
            "Content-Type": "application/json; charset=utf-8",
            "accept": "*/*",
            "accept-language": "ar,en-GB;q=0.9,en;q=0.8,ar-EG;q=0.7,en-US;q=0.6",
            "accept-charset": "utf-8",
            "origin": "https://live.wati.io",
            "referer": "https://live.wati.io/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
        }
        
        # Empty payload as message is in URL (as per working examples)
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
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
        print(f"🔍 Received data: {data}")
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
        # Run the sync in a separate thread to avoid blocking
        import asyncio
        import concurrent.futures
        
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as executor:
            result = await loop.run_in_executor(executor, scheduler.run_manual_sync)
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
    """Add a question-answer pair to the Excel file and then to the knowledge base"""
    try:
        data = await request.json()
        question = data.get("question")
        answer = data.get("answer")
        metadata = data.get("metadata", {"source": "api"})
        
        if not question:
            raise HTTPException(status_code=400, detail="Question is required")
        
        # Allow empty answers - questions without answers are valid
        if not answer:
            answer = ""  # Set empty string for questions without answers
        
        # Extract category, language, and other fields from metadata
        category = metadata.get("category", "general")
        language = metadata.get("language", "ar")
        source = metadata.get("source", "admin")
        priority = metadata.get("priority", "normal")
        
        # Import required modules
        from utils.excel_manager import csv_manager
        from vectorstore.chroma_db import chroma_manager
        
        # First add to Excel file (simple direct call)
        csv_success = csv_manager.add_qa_pair(
            question=question,
            answer=answer,
            category=category,
            language=language,
            source=source,
            priority=priority,
            metadata=metadata
        )
        
        if not csv_success:
            raise HTTPException(status_code=500, detail="Failed to add Q&A pair to Excel file")
        
        # Then add to vector database using simple method from populate_from_csv_light.py
        questions = [question]
        answers = [answer]
        metadatas = [metadata]
        
        try:
            # Use the same logic as populate_from_csv_light.py
            result = chroma_manager.add_knowledge_sync(
                questions=questions,
                answers=answers,
                metadatas=metadatas,
                check_duplicates=False  # Skip duplicate checking for speed
            )
            
            # The result is a list of IDs when check_duplicates=False
            if isinstance(result, list) and len(result) > 0:
                return {
                    "status": "success", 
                    "id": result[0],
                    "message": "Q&A pair added successfully to Excel and knowledge base",
                    "added_count": 1,
                    "skipped_count": 0
                }
            else:
                raise HTTPException(status_code=500, detail="Failed to add Q&A pair to vector database")
                
        except Exception as vector_error:
            print(f"[Vector DB Add ERROR] {str(vector_error)}")
            # Still return success since Excel was saved successfully
            return {
                "status": "success", 
                "id": "excel_only",
                "message": "Q&A pair added to Excel successfully (vector database failed)",
                "added_count": 1,
                "skipped_count": 0
            }
                
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Knowledge Add ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/knowledge/check-duplicate")
async def check_duplicate_knowledge(request: Request):
    """Check if a question already exists in the Excel file (fast method)"""
    try:
        data = await request.json()
        question = data.get("question")
        similarity_threshold = data.get("similarity_threshold", 0.85)
        
        if not question:
            raise HTTPException(status_code=400, detail="Question is required")
        
        # Use Excel-based duplicate check (much faster)
        from utils.excel_manager import csv_manager
        from difflib import SequenceMatcher
        
        # Read existing questions from Excel
        qa_pairs = csv_manager.read_qa_pairs()
        
        # Check for duplicates using string similarity
        question_lower = question.lower().strip()
        
        for pair in qa_pairs:
            existing_question = pair.get("question", "").lower().strip()
            if not existing_question:
                continue
                
            # Calculate similarity using SequenceMatcher
            similarity = SequenceMatcher(None, question_lower, existing_question).ratio()
            
            if similarity >= similarity_threshold:
                return {
                    "status": "duplicate_found",
                    "duplicate": True,
                    "existing_question": pair.get("question", ""),
                    "similarity": similarity,
                    "metadata": pair.get("metadata", {})
                }
        
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
async def list_knowledge(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=500, description="Items per page"),
    category: Optional[str] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Search in questions and answers"),
    sort_by: str = Query("id", description="Sort by field"),
    sort_order: str = Query("asc", description="Sort order: asc or desc")
):
    """
    List Q&A pairs from the Excel file with pagination, filtering, and sorting
    """
    try:
        # Get all items from the Excel file
        from utils.excel_manager import csv_manager
        
        qa_pairs = csv_manager.read_qa_pairs()
        
        # Convert to our format
        items = []
        for i, pair in enumerate(qa_pairs):
            items.append({
                "id": f"excel_{i}",  # Use Excel index as ID
                "question": pair.get("question", ""),
                "answer": pair.get("answer", ""),
                "metadata": {
                    "category": pair.get("category", "general"),
                    "language": pair.get("language", "ar"),
                    "source": pair.get("source", "excel"),
                    "priority": pair.get("priority", "normal"),
                    **pair.get("metadata", {})
                }
            })
        
        # Apply filters
        filtered_items = items
        
        # Filter by category
        if category:
            filtered_items = [item for item in filtered_items 
                            if item.get("metadata", {}).get("category") == category]
        
        # Filter by search term
        if search:
            search_lower = search.lower()
            filtered_items = [item for item in filtered_items 
                            if search_lower in item.get("question", "").lower() or 
                               search_lower in item.get("answer", "").lower()]
        
        # Sort items
        reverse = sort_order.lower() == "desc"
        if sort_by == "question":
            filtered_items.sort(key=lambda x: x.get("question", ""), reverse=reverse)
        elif sort_by == "answer":
            filtered_items.sort(key=lambda x: x.get("answer", ""), reverse=reverse)
        elif sort_by == "category":
            filtered_items.sort(key=lambda x: x.get("metadata", {}).get("category", ""), reverse=reverse)
        
        # Calculate pagination
        total_items = len(filtered_items)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_items = filtered_items[start_idx:end_idx]
        
        # Calculate pagination info
        total_pages = (total_items + page_size - 1) // page_size
        has_next = page < total_pages
        has_prev = page > 1
        
        return {
            "status": "success",
            "items": paginated_items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_items": total_items,
                "total_pages": total_pages,
                "has_next": has_next,
                "has_prev": has_prev
            },
            "filters": {
                "category": category,
                "search": search,
                "sort_by": sort_by,
                "sort_order": sort_order
            }
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
        
        if not qa_id or not question:
            raise HTTPException(status_code=400, detail="Missing required fields: ID and question are required")
        
        # Allow empty answers
        if not answer:
            answer = ""
        
        # Extract Excel index from ID
        if qa_id.startswith("excel_"):
            excel_index = int(qa_id.replace("excel_", ""))
            
            # Update in Excel file
            from utils.excel_manager import csv_manager
            success = csv_manager.update_qa_pair(
                index=excel_index,
                question=question,
                answer=answer,
                category=metadata.get("category", "general"),
                language=metadata.get("language", "ar"),
                source=metadata.get("source", "excel"),
                priority=metadata.get("priority", "normal"),
                metadata=metadata
            )
            
            if not success:
                raise HTTPException(status_code=500, detail="Failed to update Q&A pair in Excel file")
        
        # Also update in vector database if it exists (only questions are embedded now)
        try:
            from vectorstore.chroma_db import chroma_manager
            
            # We no longer embed answers separately - only update the question document
            question_id = f"q_{qa_id}"
            question_metadata = {"answer_id": qa_id, "type": "question", "answer_text": answer, **metadata}
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
        except Exception as e:
            print(f"Warning: Failed to update vector database: {str(e)}")
        
        return {
            "status": "success",
            "message": "Q&A pair updated successfully",
            "id": qa_id
        }
    except Exception as e:
        print(f"Error updating knowledge: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/knowledge/validate-delete/{qa_id}")
async def validate_delete(qa_id: str):
    """
    Validate what would be deleted without actually deleting it
    """
    try:
        if qa_id.startswith("excel_"):
            excel_index = int(qa_id.replace("excel_", ""))
            
            from utils.excel_manager import csv_manager
            all_qa_pairs = csv_manager.read_qa_pairs()
            
            # Validation checks
            if excel_index < 0 or excel_index >= len(all_qa_pairs):
                return {
                    "status": "error",
                    "message": f"Invalid index {excel_index}. Valid range: 0-{len(all_qa_pairs)-1}"
                }
            
            # Get the item that would be deleted
            target_item = all_qa_pairs[excel_index]
            
            # Get surrounding context
            context = {
                "target_index": excel_index,
                "target_question": target_item.get('question', '')[:100],
                "target_answer": target_item.get('answer', '')[:100],
                "total_items": len(all_qa_pairs)
            }
            
            # Add surrounding items for context
            if excel_index > 0:
                context["item_above"] = {
                    "index": excel_index - 1,
                    "question": all_qa_pairs[excel_index - 1].get('question', '')[:100]
                }
            
            if excel_index + 1 < len(all_qa_pairs):
                context["item_below"] = {
                    "index": excel_index + 1,
                    "question": all_qa_pairs[excel_index + 1].get('question', '')[:100]
                }
            
            return {
                "status": "success",
                "message": "Validation successful",
                "qa_id": qa_id,
                "excel_index": excel_index,
                "context": context
            }
        else:
            return {
                "status": "error", 
                "message": "Invalid ID format - expected format: excel_{index}"
            }
            
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.delete("/knowledge/delete/{qa_id}")
async def delete_knowledge(qa_id: str):
    """
    Delete a Q&A pair by ID from Excel file, vector database, and dashboard
    """
    try:
        # Extract Excel index from ID
        if qa_id.startswith("excel_"):
            excel_index = int(qa_id.replace("excel_", ""))
            
            # Get the question text before deleting (needed for vector DB cleanup)
            from utils.excel_manager import csv_manager
            qa_pair = csv_manager.get_qa_pair_by_index(excel_index)
            
            if not qa_pair:
                raise HTTPException(status_code=404, detail=f"Q&A pair not found at index {excel_index}")
            
            question_text = qa_pair.get('question', '')
            
            # Delete from Excel file
            success = csv_manager.delete_qa_pair(excel_index)
            
            if not success:
                raise HTTPException(status_code=500, detail="Failed to delete Q&A pair from Excel file")
        
            # Delete from vector database (only questions are embedded now)
            try:
                from vectorstore.chroma_db import chroma_manager
                
                if question_text:
                    # Use the new method to delete by question text
                    chroma_manager.delete_question_by_text(question_text)
                        
            except Exception as e:
                print(f"⚠️ Failed to delete from vector database: {str(e)}")
                # Continue execution - Excel deletion succeeded
        
        else:
            raise HTTPException(status_code=400, detail="Invalid ID format - expected format: excel_{index}")
        
        return {
            "status": "success",
            "message": "Q&A pair deleted successfully from Excel file and vector database",
            "id": qa_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error deleting knowledge: {str(e)}")
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

@app.get("/debug/knowledge-structure")
async def debug_knowledge_structure():
    """Debug endpoint to test knowledge base structure"""
    try:
        result = await embedding_agent.debug_knowledge_base_structure(sample_size=10)
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/debug/test-embedding")
async def debug_test_embedding(message: str):
    """Debug endpoint to test embedding agent with a specific message"""
    try:
        result = await embedding_agent.process_message(
            user_message=message,
            conversation_history=[],
            user_language='ar'
        )
        return {
            "status": "success",
            "user_message": message,
            "result": result
        }
    except Exception as e:
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
        results = await data_scraper.full_sync(db)
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
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
   
