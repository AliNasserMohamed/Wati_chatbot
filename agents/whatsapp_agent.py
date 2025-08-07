import os
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_core.messages import HumanMessage, AIMessage
from typing import List, Dict, Any, Optional
import requests
from sqlalchemy.orm import Session
from dotenv import load_dotenv
import json

from database.db_utils import DatabaseManager
from vectorstore.chroma_db import chroma_manager

# Ensure environment variables are loaded
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

class WhatsAppAgent:
    def __init__(self):
        # Load API keys from environment
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        if not self.openai_api_key:
            print("WARNING: OPENAI_API_KEY not found in environment variables!")
            print(f"Current directory: {os.getcwd()}")
            print(f".env file location should be: {os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')}")
        else:
            # Clean the API key by stripping whitespace and newlines
            self.openai_api_key = self.openai_api_key.strip()
        
        self.wati_api_key = os.getenv("WATI_API_KEY")
        if self.wati_api_key:
            # Clean the Wati API key by stripping whitespace and newlines
            self.wati_api_key = self.wati_api_key.strip()
        
        self.wati_api_url = os.getenv("WATI_API_URL", "https://live-mt-server.wati.io/301269/api/v1")
        if self.wati_api_url:
            # Clean the URL as well
            self.wati_api_url = self.wati_api_url.strip()
        
        # Initialize language model
        self.setup_agent()
        
        # Headers for Wati API
        self.wati_headers = {
            "Authorization": f"Bearer {self.wati_api_key}",
            "Content-Type": "application/json"
        }
    
    def setup_agent(self):
        """Set up the LangChain components"""
        # Initialize OpenAI chat model
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set. Please check your .env file.")
            
        self.chat_model = ChatOpenAI(
            temperature=0.7,
            model="gpt-4o",
            api_key=self.openai_api_key,  # Explicitly pass the API key
            parallel_tool_calls=False  # Disable parallel function calling
        )
        
        # Define the system prompt
        system_prompt = """
        أنت مساعد ذكي يجيب على استفسارات العملاء لتطبيق ابار.
        تطبيق ابار هو تطبيق لتوصيل المياه المعبأة من مختلف العلامات التجارية.
        يوجد أكثر من 200 علامة تجارية للمياه في التطبيق.
        التوصيل مجاني 100%.
        
        قواعد مهمة:
        1. يجب أن تجيب باللهجة السعودية العامية وليس الفصحى.
        2. كن ودودا ومحترما في إجاباتك.
        3. إذا لم تعرف الإجابة، قل "للأسف ما عندي معلومة عن هذا الموضوع، حاب أوصلك مع فريق خدمة العملاء؟"
        4. لا تخترع معلومات ليست موجودة في السياق.
        5. استخدم المعلومات من قاعدة المعرفة إذا كانت متاحة.
        
        معلومات عن المستخدم:
        {user_info}
        
        سجل المحادثة السابقة:
        {chat_history}
        
        معلومات ذات صلة من قاعدة المعرفة:
        {knowledge_base}
        """
        
        # Create the prompt template
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{message}")
        ])
        
        # Build the chain
        self.chain = (
            {
                "message": lambda x: x["message"],
                "user_info": lambda x: x.get("user_info", "لا توجد معلومات متاحة عن المستخدم حاليًا."),
                "chat_history": lambda x: self._format_chat_history(x.get("chat_history", [])),
                "knowledge_base": lambda x: x["message"]  # Pass message to be processed separately
            }
            | self.prompt
            | self.chat_model
            | StrOutputParser()
        )
    
    def _format_chat_history(self, history: List[Dict[str, Any]]) -> str:
        """Format chat history for the prompt"""
        if not history:
            return "لا توجد محادثة سابقة."
        
        formatted_history = ""
        for entry in history:
            role = "المستخدم" if entry["role"] == "user" else "المساعد"
            formatted_history += f"{role}: {entry['content']}\n"
        
        return formatted_history
    
    async def _get_relevant_knowledge(self, query: str) -> str:
        """Get relevant knowledge from vector database"""
        results = await chroma_manager.search(query, n_results=2)
        
        if not results:
            return "لا توجد معلومات ذات صلة في قاعدة المعرفة."
        
        formatted_knowledge = ""
        for i, result in enumerate(results, 1):
            formatted_knowledge += f"{i}. {result['document']}\n"
        
        return formatted_knowledge
    
    def _extract_user_info(self, user_id: int, db: Session) -> str:
        """Get user information from database"""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return "لا توجد معلومات متاحة عن المستخدم."
        
        info = f"رقم الهاتف: {user.phone_number}\n"
        if user.name:
            info += f"الاسم: {user.name}\n"
        if user.conclusion:
            info += f"ملاحظات: {user.conclusion}\n"
        
        return info
    
    async def process_message(self, message: str, user_id: Optional[int] = None, 
                        phone_number: Optional[str] = None, db: Optional[Session] = None) -> str:
        """Process incoming message and generate response"""
        try:
            # Prepare conversation context
            context = {"message": message}
            
            # Get relevant knowledge asynchronously
            knowledge_base = await self._get_relevant_knowledge(message)
            context["knowledge_base"] = knowledge_base
            
            # Add user info and chat history if database is available
            if db and (user_id or phone_number):
                # Get user by ID or phone number
                user = None
                if user_id:
                    user = db.query(User).filter(User.id == user_id).first()
                elif phone_number:
                    user = DatabaseManager.get_user_by_phone(db, phone_number)
                    if not user:
                        user = DatabaseManager.create_user(db, phone_number)
                
                if user:
                    # Add user info to context
                    context["user_info"] = self._extract_user_info(user.id, db)
                    
                    # Save the message
                    user_message = DatabaseManager.save_user_message(db, user.id, message)
                    
                    # Get chat history
                    context["chat_history"] = DatabaseManager.get_user_message_history(db, user.id)
                    
                    # Generate response
                    response = await self.chain.ainvoke(context)
                    
                    # Save the response
                    DatabaseManager.save_bot_reply(db, user_message.id, response)
                    
                    return response
            
            # If no database or user, just process the message
            return await self.chain.ainvoke(context)
            
        except Exception as e:
            print(f"[Error processing message] {str(e)}")
            return "عذراً، حدث خطأ أثناء معالجة رسالتك. الرجاء المحاولة مرة أخرى."
    
    def send_whatsapp_message(self, to_number: str, message: str) -> Dict[str, Any]:
        """Send a message via Wati API"""
        # Ensure there's no trailing slash in the API URL and correct the path format
        base_url = self.wati_api_url.rstrip('/')
        
        # Make sure the base_url has the correct format with /api/v1
        if not base_url.endswith('/api/v1'):
            # If the URL doesn't already end with /api/v1, add it
            if '/api/' not in base_url:
                base_url = f"{base_url}/api/v1"
        
        # URL encode the message and include it as a query parameter
        import urllib.parse
        encoded_message = urllib.parse.quote(message)
        url = f"{base_url}/sendSessionMessage/{to_number}?messageText={encoded_message}"
        
        print(f"Sending WhatsApp message to: {to_number}")
        print(f"API URL: {url}")
        
        # Extended headers based on user's working example
        headers = {
            "Authorization": f"Bearer {self.wati_api_key.strip()}",
            "Content-Type": "application/json",
            "accept": "*/*",
            "accept-language": "en-GB,en;q=0.9,ar-EG;q=0.8,ar;q=0.7,en-US;q=0.6",
            "origin": "https://live.wati.io",
            "referer": "https://live.wati.io/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
        }
        
        # Empty payload as message is in URL
        payload = {}
        
        try:
            # Use POST request with empty payload as in the user's example
            response = requests.post(url, headers=headers, data=payload)
            print(f"Response status code: {response.status_code}")
            
            # Log response content for debugging
            try:
                response_content = response.json() if response.content else {"status": "empty_response"}
                print(f"Response content: {json.dumps(response_content, indent=2)}")
            except Exception as e:
                print(f"Failed to parse response: {str(e)}")
                print(f"Raw response: {response.text}")
            
            if response.status_code >= 400:
                print(f"ERROR: API returned error status {response.status_code}")
                # Try the alternative endpoint if this one fails
                return self._try_alternative_endpoints_query_param(to_number, message)
                
            return {"status": "success", "response": response.text}
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            print(f"[WATI ERROR] {error_msg}")
            return self._try_alternative_endpoints_query_param(to_number, message)
    
    def _try_alternative_endpoints_query_param(self, to_number: str, message: str) -> Dict[str, Any]:
        """Try alternative API endpoints using query parameter approach"""
        print("Trying alternative API endpoints with query parameter approach...")
        
        # Import for URL encoding
        import urllib.parse
        
        # Clean base URL to ensure proper formatting
        base_url = self.wati_api_url.rstrip('/')
        if not base_url.endswith('/api/v1'):
            if '/api/' not in base_url:
                base_url = f"{base_url}/api/v1"
        
        # URL encode the message
        encoded_message = urllib.parse.quote(message)
        
        # Extended headers based on user's working example
        headers = {
            "Authorization": f"Bearer {self.wati_api_key.strip()}",
            "Content-Type": "application/json",
            "accept": "*/*",
            "accept-language": "en-GB,en;q=0.9,ar-EG;q=0.8,ar;q=0.7,en-US;q=0.6",
            "origin": "https://live.wati.io",
            "referer": "https://live.wati.io/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
        }
        
        # Empty payload as message is in URL
        payload = {}
        
        # List of alternative endpoints to try
        endpoints = [
            f"{base_url}/sendSessionMessage/{to_number}?messageText={encoded_message}",
            f"{base_url}/sendMessage/{to_number}?messageText={encoded_message}",
            f"{base_url}/sendMessage?whatsappNumber={to_number}&messageText={encoded_message}",
            f"{base_url.replace('/api/v1', '')}/api/v1/sendSessionMessage/{to_number}?messageText={encoded_message}"
        ]
        
        for i, endpoint in enumerate(endpoints, 1):
            print(f"Trying endpoint #{i}: {endpoint}")
            try:
                response = requests.post(endpoint, headers=headers, data=payload)
                print(f"Response status code: {response.status_code}")
                
                try:
                    response_content = response.json() if response.content else {"status": "empty_response"}
                    print(f"Response content: {json.dumps(response_content, indent=2)}")
                except Exception:
                    print(f"Raw response: {response.text}")
                
                if response.status_code < 400:
                    print(f"✅ Endpoint #{i} successful!")
                    return {"status": f"success_with_alternative_endpoint_{i}", "response": response.text}
            except Exception as e:
                print(f"❌ Endpoint #{i} failed: {str(e)}")
        
        return {"error": "All API endpoints failed", "message": message, "recipient": to_number}

# For importing
from database.db_models import User

# Create an instance
whatsapp_agent = WhatsAppAgent() 