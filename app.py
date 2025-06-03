import os
from fastapi import FastAPI, Request, Depends, HTTPException, Header, Query
from typing import Optional, List
from dotenv import load_dotenv
import uvicorn
import json
import sys
import uuid
from datetime import datetime
import aiohttp
import urllib.parse

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
from database.db_models import MessageType, UserSession
from agents.message_classifier import message_classifier
from agents.query_agent import query_agent
from agents.service_request import service_request_agent
from utils.language_utils import language_handler
from services.data_api import data_api
from services.data_scraper import data_scraper
from services.scheduler import scheduler

app = FastAPI(
    title="Abar Chatbot API",
    description="API for handling WhatsApp messages for Abar water delivery app",
    version="1.0.0"
)

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
        print(f"Webhook received: {json.dumps(data, indent=2)}")
        
        # Extract message data
        phone_number = data.get("waId")
        message_type = data.get("type", "text")  # Can be text, audio, etc.
        
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
                    return {"status": "error", "message": "Failed to process audio"}
            else:
                return {"status": "error", "message": "No audio data received"}
        else:
            message_text = data.get("text", "")

        # Create user message record
        user_message = DatabaseManager.create_message(
            db,
            user_id=user.id,
            content=message_text
        )

        # Classify message and detect language
        message_type, detected_language = await message_classifier.classify_message(message_text, db, user_message)
        
        # Store the detected language in session context
        context = json.loads(session.context) if session.context else {}
        context['language'] = detected_language
        session.context = json.dumps(context)
        
        # Handle message based on classification
        if message_type in [MessageType.COMPLAINT, MessageType.SUGGESTION, MessageType.GREETING]:
            response_text = message_classifier.get_default_response(message_type, detected_language)
        
        elif message_type == MessageType.INQUIRY:
            # Get response in English first
            response_text = await query_agent.handle_query(message_text, phone_number, db)
            # Translate if needed
            if detected_language == 'ar':
                response_text = await language_handler.translate_response(response_text, 'ar')
        
        elif message_type == MessageType.SERVICE_REQUEST:
            # Get response in English first
            response_text = await service_request_agent.handle_service_request(message_text, phone_number, db)
            # Translate if needed
            if detected_language == 'ar':
                response_text = await language_handler.translate_response(response_text, 'ar')
        
        else:
            response_text = language_handler.get_default_responses(detected_language)['UNKNOWN']

        # Create bot reply record with language
        DatabaseManager.create_bot_reply(
            db,
            message_id=user_message.id,
            content=response_text,
            language=detected_language
        )

        # Send response via WhatsApp
        result = await send_whatsapp_message(phone_number, response_text)
        print(f"Response sent to {phone_number}: {response_text}")

        db.commit()
        return {"status": "success"}

    except Exception as e:
        print(f"[Webhook ERROR] {str(e)}")
        return {"status": "error", "message": str(e)}

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
        return {"status": "success", "data": cities}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/cities/{city_id}")
async def get_city(city_id: int, db=Depends(get_db)):
    """Get a specific city by ID"""
    city = data_api.get_city_by_id(db, city_id)
    if not city:
        raise HTTPException(status_code=404, detail="City not found")
    return {"status": "success", "data": city}

@app.get("/api/cities/{city_id}/brands")
async def get_city_brands(city_id: int, db=Depends(get_db)):
    """Get all brands for a specific city"""
    try:
        brands = data_api.get_brands_by_city(db, city_id)
        return {"status": "success", "data": brands}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/cities/{city_id}/full")
async def get_city_with_brands_products(city_id: int, db=Depends(get_db)):
    """Get a city with all its brands and products"""
    city_data = data_api.get_city_with_brands_and_products(db, city_id)
    if not city_data:
        raise HTTPException(status_code=404, detail="City not found")
    return {"status": "success", "data": city_data}

@app.get("/api/brands")
async def get_brands(search: str = None, db=Depends(get_db)):
    """Get all brands or search brands by title"""
    try:
        if search:
            brands = data_api.search_brands(db, search)
        else:
            brands = data_api.get_all_brands(db)
        return {"status": "success", "data": brands}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/brands/{brand_id}")
async def get_brand(brand_id: int, db=Depends(get_db)):
    """Get a specific brand by ID"""
    brand = data_api.get_brand_by_id(db, brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    return {"status": "success", "data": brand}

@app.get("/api/brands/{brand_id}/products")
async def get_brand_products(brand_id: int, db=Depends(get_db)):
    """Get all products for a specific brand"""
    try:
        products = data_api.get_products_by_brand(db, brand_id)
        return {"status": "success", "data": products}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/brands/{brand_id}/full")
async def get_brand_with_products(brand_id: int, db=Depends(get_db)):
    """Get a brand with all its products"""
    brand_data = data_api.get_brand_with_products(db, brand_id)
    if not brand_data:
        raise HTTPException(status_code=404, detail="Brand not found")
    return {"status": "success", "data": brand_data}

@app.get("/api/products")
async def get_products(search: str = None, db=Depends(get_db)):
    """Get all products or search products by title/barcode"""
    try:
        if search:
            products = data_api.search_products(db, search)
        else:
            products = data_api.get_all_products(db)
        return {"status": "success", "data": products}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/products/{product_id}")
async def get_product(product_id: int, db=Depends(get_db)):
    """Get a specific product by ID"""
    product = data_api.get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"status": "success", "data": product}

# Knowledge management endpoints
@app.post("/knowledge/add")
async def add_knowledge(request: Request):
    """Add a question-answer pair to the knowledge base"""
    try:
        data = await request.json()
        question = data.get("question")
        answer = data.get("answer")
        metadata = data.get("metadata", {"source": "api"})
        
        if not question or not answer:
            raise HTTPException(status_code=400, detail="Question and answer are required")
        
        id = knowledge_manager.add_qa_pair(question, answer, metadata)
        return {"status": "success", "id": id}
    except Exception as e:
        print(f"[Knowledge Add ERROR] {str(e)}")
        return {"status": "error", "message": str(e)}

@app.get("/knowledge/search")
async def search_knowledge(query: str, n_results: int = 3):
    """Search the knowledge base"""
    try:
        results = knowledge_manager.search_knowledge(query, n_results)
        return {"status": "success", "results": results}
    except Exception as e:
        print(f"[Knowledge Search ERROR] {str(e)}")
        return {"status": "error", "message": str(e)}

# Initialize knowledge base with default data
@app.post("/knowledge/populate")
async def populate_knowledge():
    """Populate the knowledge base with default data"""
    try:
        ids = knowledge_manager.populate_abar_knowledge()
        return {"status": "success", "count": len(ids), "ids": ids}
    except Exception as e:
        print(f"[Knowledge Populate ERROR] {str(e)}")
        return {"status": "error", "message": str(e)}

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
   
