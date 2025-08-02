# Abar WhatsApp Chatbot

A webhook-based WhatsApp chatbot for the Abar water delivery app using FastAPI, SQLite, and Chroma vector database.

## Features

- **WhatsApp Integration**: Receive and reply to customer messages through WhatsApp (using Wati API)
- **Multi-language Support**: Automatic language detection (Arabic/English) and response translation
- **Message Classification**: AI-powered classification of messages (Service Request, Inquiry, Complaint, etc.)
- **SQLite Database**: Store user information, messages, and replies with full conversation history
- **Vector Search**: Use Chroma to find relevant answers to user queries
- **Knowledge Base**: API endpoints to manage Q&A data
- **Saudi Arabic Dialect**: AI responses in Saudi dialect
- **Audio Support**: Convert voice messages to text using Gemini AI

## Recent Updates

- ✅ **Database Migration**: Fixed SQLite schema to include `message_type` and `language` columns
- ✅ **Message Classification**: Added AI-powered message type detection
- ✅ **Language Detection**: Automatic language detection and response translation
- ✅ **Audio Processing**: Voice message transcription support

## Project Structure

```
├── app.py                      # Main application entry point
├── agents/                     # AI agent modules
│   ├── __init__.py
│   ├── whatsapp_agent.py       # WhatsApp interaction agent
│   ├── message_classifier.py   # Message classification and language detection
│   ├── query_agent.py          # Query handling agent
│   └── service_request.py      # Service request handler
├── database/                   # Database modules
│   ├── __init__.py
│   ├── db_models.py            # SQLAlchemy models
│   ├── db_utils.py             # Database utilities
│   ├── migrate_add_columns.py  # Database migration script
│   └── data/                   # SQLite database files
├── services/                   # External service integrations
│   ├── __init__.py
│   ├── data_api.py            # External API integration
│   ├── data_scraper.py        # Data scraping utilities
│   └── scheduler.py           # Background task scheduler
├── vectorstore/               # Vector database modules
│   ├── __init__.py
│   └── data/                  # Persisted vector data
├── utils/                     # Utility modules
│   ├── __init__.py
│   ├── knowledge_manager.py   # Knowledge base management
│   └── language_utils.py      # Language processing utilities
├── knowledge_base/            # Knowledge base data
└── requirements.txt           # Dependencies
```

## Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/YOUR_USERNAME/Wati_chatbot.git
   cd Wati_chatbot
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run database migration (if needed):**
   ```bash
   python database/migrate_add_columns.py
   ```

4. **Create a `.env` file with the following variables:**
   ```
   OPENAI_API_KEY=your_openai_api_key
   GEMINI_API_KEY=your_gemini_api_key
   WATI_API_KEY=your_wati_api_key
   WATI_API_URL=https://live-mt-server.wati.io/your_account_id/api/v1
   WATI_WEBHOOK_VERIFY_TOKEN=your_webhook_verification_token
   ```

5. **Run the application:**
   ```bash
   python app.py
   ```

## Deployment

### Server Deployment with Git Auto-Update

1. **Clone on your server:**
   ```bash
   git clone https://github.com/YOUR_USERNAME/Wati_chatbot.git
   cd Wati_chatbot
   ```

2. **Set up virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your actual API keys
   ```

4. **Run migrations:**
   ```bash
   python database/migrate_add_columns.py
   ```

5. **Auto-update script for server:**
   ```bash
   #!/bin/bash
   cd /path/to/Wati_chatbot
   git pull origin main
   source venv/bin/activate
   pip install -r requirements.txt
   python database/migrate_add_columns.py
   # Restart your application service
   sudo systemctl restart wati-chatbot
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
- **user_messages**: Store messages from users with classification and language
- **bot_replies**: Store responses sent to users
- **complaints**: Store complaint records
- **suggestions**: Store suggestion records
- **user_sessions**: Store user session data

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

## Troubleshooting

### Database Issues
If you encounter database column errors, run the migration script:
```bash
python database/migrate_add_columns.py
```

### Common Fixes
- **SQLite column missing**: Run database migration
- **WhatsApp webhook not working**: Check WATI_WEBHOOK_VERIFY_TOKEN
- **API key errors**: Verify all API keys in .env file

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Commit your changes: `git commit -m 'Add feature'`
4. Push to the branch: `git push origin feature-name`
5. Submit a pull request 

## OpenAI Rate Limiting Configuration

### Understanding 429 Errors
If you see "HTTP/1.1 429 Too Many Requests" errors, you've hit OpenAI's rate limits. This system makes multiple API calls per user message:
- Message relevance classification
- Main query processing with function calls
- Final response generation

### Configure Rate Limits by Plan

**Free Tier (3 RPM):**
```env
OPENAI_MIN_REQUEST_INTERVAL=20    # 20 seconds between requests
OPENAI_MAX_RETRIES=5              # More retries with longer delays
OPENAI_BASE_DELAY=2               # Longer initial delay
```

**Paid Tier ($5+ spent):**
```env
OPENAI_MIN_REQUEST_INTERVAL=0.5   # 0.5 seconds between requests (120 RPM)
OPENAI_MAX_RETRIES=3              # Standard retries
OPENAI_BASE_DELAY=1               # Standard delay
```

**High Volume Usage:**
```env
OPENAI_MIN_REQUEST_INTERVAL=0.1   # Very fast requests
OPENAI_MAX_RETRIES=3
OPENAI_BASE_DELAY=0.5
```

### Additional Optimizations

1. **Caching**: The system now caches classification results to reduce duplicate API calls
2. **Exponential Backoff**: Automatic retry with increasing delays
3. **Smart Rate Limiting**: Enforces minimum time between requests

### Monitoring Usage
- Check your OpenAI usage dashboard: https://platform.openai.com/usage
- Monitor logs for rate limit warnings
- Adjust settings based on your actual usage patterns 