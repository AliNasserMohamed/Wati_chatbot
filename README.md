# Abar WhatsApp Chatbot

A webhook-based WhatsApp chatbot for the Abar water delivery app using FastAPI, SQLite, and Chroma vector database.

## Features

- **WhatsApp Integration**: Receive and reply to customer messages through WhatsApp (using Wati API)
- **SQLite Database**: Store user information, messages, and replies
- **Vector Search**: Use Chroma to find relevant answers to user queries
- **Knowledge Base**: API endpoints to manage Q&A data
- **Saudi Arabic Dialect**: AI responses in Saudi dialect

## Project Structure

```
├── app.py                  # Main application entry point
├── agents/                 # AI agent modules
│   ├── __init__.py
│   └── whatsapp_agent.py   # WhatsApp interaction agent
├── database/               # Database modules
│   ├── __init__.py
│   ├── db_models.py        # SQLAlchemy models
│   └── db_utils.py         # Database utilities
├── vectorstore/            # Vector database modules
│   ├── __init__.py
│   ├── chroma_db.py        # Chroma DB implementation
│   └── data/               # Persisted vector data
├── utils/                  # Utility modules
│   ├── __init__.py
│   └── knowledge_manager.py # Knowledge base management
└── requirements.txt        # Dependencies
```

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create a `.env` file with the following variables:
   ```
   OPENAI_API_KEY=your_openai_api_key
   WATI_API_KEY=your_wati_api_key
   WATI_API_URL=https://live-mt-server.wati.io/your_account_id/api/v1
   WATI_WEBHOOK_VERIFY_TOKEN=your_webhook_verification_token
   ```

3. Run the application:
   ```bash
   python app.py
   ```

## API Endpoints

- **GET /webhook**: Verification endpoint for WhatsApp webhook
- **POST /webhook**: Receive messages from WhatsApp
- **POST /send-message**: Send a message to a user
- **GET /health**: Check API health
- **POST /knowledge/add**: Add a question-answer pair to the knowledge base
- **GET /knowledge/search**: Search the knowledge base
- **POST /knowledge/populate**: Populate the knowledge base with default data
- **POST /user/update-conclusion**: Update user information and conclusions

## Database Schema

- **users**: Store user information (phone number, name, conclusion)
- **user_messages**: Store messages from users
- **bot_replies**: Store responses sent to users

## Knowledge Base

The knowledge base stores Q&A pairs about the Abar app, including:
- General app information
- Ordering process
- Delivery details
- Payment options
- Customer support

## Usage Example

1. Set up WhatsApp webhook to point to your `/webhook` endpoint
2. Populate the knowledge base: `POST /knowledge/populate`
3. Start receiving and responding to messages automatically

## Development

To expand the knowledge base, use the `/knowledge/add` endpoint:

```bash
curl -X POST "http://localhost:8000/knowledge/add" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "هل تتوفر عروض للطلبات المتكررة؟",
    "answer": "أكيد، عندنا برنامج مكافآت للعملاء المميزين، وتقدر تشوف العروض المتاحة لك مباشرة في التطبيق!",
    "metadata": {"source": "marketing", "category": "promotions"}
  }'
``` 