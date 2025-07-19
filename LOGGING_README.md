# Comprehensive Message Logging System

This chatbot implements a comprehensive logging system that tracks the complete journey of every message from arrival to final response. The logging system captures every step of processing, including agent interactions, LLM calls, database operations, and WhatsApp responses.

## 📋 What Gets Logged

The system tracks the following information for every message:

### 1. **Message Journey Lifecycle**
- **Journey Start**: When a message arrives via webhook
- **Journey Completion**: When processing finishes (with final status)
- **Processing Duration**: Total time from start to finish
- **Step Count**: Number of processing steps taken

### 2. **Webhook Processing**
- Message validation and filtering
- Bot message detection (to prevent infinite loops)
- Template reply detection
- Duplicate message detection
- Message batching logic

### 3. **Agent Processing**
- **Embedding Agent**: 
  - Complete search results from knowledge base (all similar questions with similarity scores)
  - Most similar question-answer pairs that are matched
  - Complete LLM evaluation prompts sent to ChatGPT for response validation
  - Complete LLM evaluation responses from ChatGPT
  - Similarity scores and confidence values
  - Answer retrieval process and metadata
- **Message Classifier**: Classification type, detected language, confidence
- **Query Agent**: Function calling, API interactions, database lookups
- **Service Request Agent**: Service processing, order validation

### 4. **LLM Interactions**
- **Prompts**: Complete prompts sent to OpenAI/Gemini
- **Responses**: Full responses received from LLMs
- **Model Details**: Which model used (gpt-3.5-turbo, etc.)
- **Function Calls**: Any function calls made by the LLM
- **Token Usage**: Tokens consumed per request
- **Duration**: Time taken for each LLM call

### 5. **Database Operations**
- User creation and session management
- Message storage and retrieval
- Bot reply creation
- Conversation history queries
- Operation timing and success status

### 6. **WhatsApp Integration**
- Message sending attempts
- Success/failure status
- WATI API responses
- Encoding and formatting details
- Timeout handling

### 7. **Error Handling**
- Exception details with full stack traces
- Error context (which step failed)
- Recovery attempts
- Final error status

## 📁 Log File Structure

### Location
Log files are stored in the `logs/` directory with date-based naming:
```
logs/
├── message_journey_2025-07-19.log
├── message_journey_2025-07-20.log
└── ...
```

### Format
Each log entry follows this format:
```
2025-07-19 21:38:48 | INFO | message_journey | 🔄 STEP_TYPE | ID: msg_abc123 | Description | Duration: 150ms
```

### Log Entry Components
- **Timestamp**: Exact time of the event
- **Level**: Log level (INFO, ERROR, WARNING)
- **Logger**: Always `message_journey`
- **Icon**: Visual indicator of step type
- **Step Type**: Type of processing step
- **Journey ID**: Unique identifier for this message journey
- **Description**: Human-readable description
- **Additional Data**: Duration, confidence scores, etc.

## 🎯 Step Types

### Core Processing Steps
- `📥 JOURNEY_START` - Message journey begins
- `📝 MESSAGE_RECEIVED` - Message text logged
- `🆔 WATI_MESSAGE_ID` - WATI message ID recorded
- `🔄 WEBHOOK_VALIDATION` - Webhook validation passed
- `🔄 MESSAGE_FILTER` - Message filtering (bot detection, etc.)
- `🔄 DUPLICATE_CHECK` - Duplicate message checking
- `✅ JOURNEY_COMPLETE` - Journey finished successfully
- `📤 FINAL_RESPONSE` - Final response to user

### Agent Processing
- `🔄 EMBEDDING_AGENT` - Embedding agent processing
- `🔄 EMBEDDING_SEARCH_RESULTS` - Knowledge base search results with similarity scores
- `🔄 EMBEDDING_QA_MATCH` - Successful question-answer match from knowledge base
- `🔄 EMBEDDING_LLM_EVALUATION_PROMPT` - Complete prompt sent to ChatGPT for evaluation
- `🔄 EMBEDDING_LLM_EVALUATION_RESULT` - ChatGPT evaluation result and response
- `🎯 EMBEDDING_AGENT_CONFIDENCE` - Similarity confidence score
- `🔄 MESSAGE_CLASSIFICATION` - Message classification
- `🔄 QUERY_AGENT_PROCESSING` - Query agent processing
- `🔄 SERVICE_REQUEST_AGENT_PROCESSING` - Service request processing

### LLM Interactions
- `🔄 LLM_INTERACTION` - LLM API call
- `💬 LLM_INTERACTION_PROMPT` - Prompt sent to LLM
- `💬 LLM_INTERACTION_RESPONSE` - Response received from LLM

### Database Operations
- `🔄 DATABASE_OPERATION` - Any database operation
- `💾 MESSAGE_SAVED` - User message saved
- `💾 REPLY_SAVED` - Bot reply saved

### WhatsApp Integration
- `🔄 WHATSAPP_SEND` - WhatsApp message sending attempt
- `📤 MESSAGE_SENT` - Successful WhatsApp delivery
- `⏰ SEND_TIMEOUT` - WhatsApp sending timeout
- `❌ SEND_FAILED` - WhatsApp sending failed

### Error Handling
- `❌ ERROR` - Any error during processing
- `⚠️ WARNING` - Warning conditions

## 🔍 Example Log Journey

Here's what a typical successful message journey looks like in the logs:

```
2025-07-19 14:30:15 | INFO | message_journey | 📥 JOURNEY_START | ID: msg_abc123 | Phone: +966501234567 | Type: text
2025-07-19 14:30:15 | INFO | message_journey | 📝 MESSAGE_RECEIVED | ID: msg_abc123 | Text: 'I need water delivery in Riyadh'
2025-07-19 14:30:15 | INFO | message_journey | 🆔 WATI_MESSAGE_ID | ID: msg_abc123 | Wati ID: wati_xyz789
2025-07-19 14:30:15 | INFO | message_journey | 🔄 WEBHOOK_VALIDATION | ID: msg_abc123 | Message passed webhook validation | Duration: 45ms
2025-07-19 14:30:15 | INFO | message_journey | 🔄 DATABASE_OPERATION | ID: msg_abc123 | Database get_or_create_session on user_sessions | Duration: 25ms
2025-07-19 14:30:15 | INFO | message_journey | 🔄 DATABASE_OPERATION | ID: msg_abc123 | Database get_message_history on user_messages | Duration: 15ms
2025-07-19 14:30:15 | INFO | message_journey | 🔄 DATABASE_OPERATION | ID: msg_abc123 | Database create_message on user_messages | Duration: 20ms
2025-07-19 14:30:15 | INFO | message_journey | 🔄 EMBEDDING_AGENT | ID: msg_abc123 | Embedding agent processing - Action: continue_to_classification | Duration: 120ms
2025-07-19 14:30:15 | INFO | message_journey | 🎯 EMBEDDING_AGENT_CONFIDENCE | ID: msg_abc123 | Score: 0.423
2025-07-19 14:30:15 | INFO | message_journey | 🔄 MESSAGE_CLASSIFICATION | ID: msg_abc123 | Classified as INQUIRY in ar | Duration: 85ms
2025-07-19 14:30:16 | INFO | message_journey | 🔄 QUERY_AGENT_PROCESSING | ID: msg_abc123 | query_agent - process_inquiry | Duration: 1250ms
2025-07-19 14:30:16 | INFO | message_journey | 🔄 LLM_INTERACTION | ID: msg_abc123 | LLM call to openai (gpt-3.5-turbo) | Duration: 1100ms
2025-07-19 14:30:16 | INFO | message_journey | 💬 LLM_INTERACTION_PROMPT | ID: msg_abc123 | Content: 'أنت موظف خدمة عملاء في شركة أبار...'
2025-07-19 14:30:16 | INFO | message_journey | 💬 LLM_INTERACTION_RESPONSE | ID: msg_abc123 | Content: 'مرحباً! يسعدني مساعدتك في توصيل المياه...'
2025-07-19 14:30:16 | INFO | message_journey | 🔄 RESPONSE_PREPARATION | ID: msg_abc123 | Prepared final response for MessageType.INQUIRY
2025-07-19 14:30:16 | INFO | message_journey | 🔄 DATABASE_OPERATION | ID: msg_abc123 | Database create_bot_reply on bot_replies | Duration: 30ms
2025-07-19 14:30:16 | INFO | message_journey | 🔄 WHATSAPP_SEND | ID: msg_abc123 | Send message to +966501234567 - Status: success | Duration: 850ms
2025-07-19 14:30:16 | INFO | message_journey | ✅ JOURNEY_COMPLETE | ID: msg_abc123 | Status: completed | Duration: 1580ms | Steps: 12
2025-07-19 14:30:16 | INFO | message_journey | 📤 FINAL_RESPONSE | ID: msg_abc123 | Response: 'مرحباً! يسعدني مساعدتك في توصيل المياه...'
```

## 🛠️ Usage

### Accessing Journey Information
```python
from utils.message_logger import message_journey_logger

# Get summary of a specific journey
summary = message_journey_logger.get_journey_summary("msg_abc123")
print(f"Journey had {summary['total_steps']} steps")
print(f"Total duration: {summary['total_duration_ms']}ms")
```

### Testing the System
Run the comprehensive test suite:
```bash
python test_message_logging.py
```

### Log Analysis
The logs can be analyzed using standard text processing tools or log analysis software:
```bash
# Count successful journeys today
grep "JOURNEY_COMPLETE.*completed" logs/message_journey_$(date +%Y-%m-%d).log | wc -l

# Find long-running operations
grep "Duration:.*ms" logs/message_journey_$(date +%Y-%m-%d).log | sort -k6 -nr | head -10

# Check error rate
grep "❌" logs/message_journey_$(date +%Y-%m-%d).log
```

## 📊 Journey Status Types

- `completed` - Successfully processed and responded
- `completed_no_reply` - Processed but no reply needed
- `completed_restricted` - User not allowed to access full features
- `completed_with_timeout` - Completed but WhatsApp sending timed out
- `completed_with_error` - Completed but WhatsApp sending failed
- `skipped_bot_message` - Skipped because it was from the bot
- `skipped_template_reply` - Skipped because it was a template reply
- `skipped_duplicate` - Skipped because it was a duplicate message
- `failed` - Processing failed with an error

## 🔧 Configuration

### Log Cleanup
The system automatically cleans up old journey data from memory (not log files) to prevent memory leaks:
- Runs cleanup 1% of the time (random sampling)
- Removes journeys older than 24 hours by default
- Log files are preserved and managed separately

### Performance
- Average logging overhead: ~5ms per journey
- Memory usage: ~2KB per active journey
- Log file rotation: Daily (automatic)

## 🎯 Benefits

1. **Complete Visibility**: See exactly how every message is processed
2. **Performance Monitoring**: Identify bottlenecks and slow operations
3. **Error Debugging**: Full context for troubleshooting issues
4. **User Experience**: Track user interactions and response quality
5. **System Health**: Monitor overall chatbot performance
6. **Compliance**: Full audit trail for all interactions

## 🚀 Future Enhancements

Potential improvements to the logging system:
- Integration with log analysis tools (ELK stack, Grafana)
- Real-time monitoring dashboard
- Automated alerting for errors or performance issues
- Log aggregation across multiple bot instances
- Advanced analytics and reporting capabilities 