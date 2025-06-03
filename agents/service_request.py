import os
from typing import Dict, Any, Optional
import aiohttp
import json
from database.db_models import UserSession
from sqlalchemy.orm import Session
import google.generativeai as genai

class ServiceRequestAgent:
    def __init__(self):
        self.api_base_url = os.getenv("API_BASE_URL")
        self.api_key = os.getenv("API_KEY")
        self.model = genai.GenerativeModel('gemini-1.0-pro')

    async def create_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new order through the API."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.api_base_url}/orders",
                json=order_data,
                headers={"Authorization": f"Bearer {self.api_key}"}
            ) as response:
                return await response.json()

    async def validate_order_data(self, text: str, session_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract and validate order information from user message."""
        prompt = f"""
        Extract order information from the following message. The order should include:
        - Product ID (if mentioned)
        - Quantity
        - Delivery Address
        - Preferred Delivery Time (if mentioned)

        Current context: {json.dumps(session_context)}
        User message: "{text}"

        Respond with a JSON object containing the extracted information. If any required field is missing, include a "missing_fields" array.
        """

        response = await self.model.generate_content(prompt)
        try:
            order_info = json.loads(response.text)
            return order_info
        except json.JSONDecodeError:
            return None

    async def handle_service_request(self, text: str, phone_number: str, db: Session) -> str:
        """Process service requests and create orders."""
        # Get or create user session
        session = db.query(UserSession).filter_by(user_id=phone_number).first()
        if not session:
            return "Please start a new conversation first."

        context = json.loads(session.context) if session.context else {}
        
        # Validate order data
        order_data = await self.validate_order_data(text, context)
        
        if not order_data:
            return "I couldn't understand your order request. Please provide more details."

        if "missing_fields" in order_data:
            missing = ", ".join(order_data["missing_fields"])
            return f"Please provide the following information to complete your order: {missing}"

        # Add user information to order data
        order_data["phone_number"] = phone_number
        if "city_id" in context:
            order_data["city_id"] = context["city_id"]
        if "brand_id" in context:
            order_data["brand_id"] = context["brand_id"]

        try:
            # Create the order
            result = await self.create_order(order_data)
            
            if "error" in result:
                return f"Sorry, there was an error creating your order: {result['error']}"
            
            # Update session context with order ID
            context["last_order_id"] = result["order_id"]
            session.context = json.dumps(context)
            db.commit()

            return f"""
            Great! Your order has been created successfully.
            Order ID: {result['order_id']}
            Estimated delivery time: {result.get('estimated_delivery', 'To be confirmed')}
            Total amount: {result.get('total_amount', 'To be calculated')}
            
            You can check your order status anytime by asking about your orders.
            """

        except Exception as e:
            print(f"Error creating order: {str(e)}")
            return "Sorry, I encountered an error while creating your order. Please try again later."

service_request_agent = ServiceRequestAgent() 