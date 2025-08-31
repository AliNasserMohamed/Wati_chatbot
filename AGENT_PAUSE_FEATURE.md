# Agent Conversation Pause Feature

## Overview

This feature automatically pauses the chatbot's message processing for 10 hours when a customer service agent enters a WhatsApp conversation. This prevents the bot from interfering while an agent is actively helping the customer.

## How It Works

### 1. Agent Detection

When the webhook receives a message, it checks for:
- `eventType`: "sessionMessageSent" 
- `owner`: True (indicates message from agent/operator)
- `operatorEmail`: Must be "contracts@abar.app" (configured in `PAUSE_TRIGGER_AGENT_EMAILS`)
- Valid `conversationId`

### 2. Conversation Pause Creation

When an agent is detected:
- Creates/updates a record in the `conversation_pauses` table
- Sets expiry time to 10 hours from the current moment
- Stores agent information (name, email, assignee ID)
- Links to the conversation ID and phone number

### 3. Message Processing Check

Before processing any user message:
- Checks if the conversation is paused
- If paused and not expired, skips all message processing
- Logs the pause status in the message journey
- Automatically cleans up expired pauses

## Database Schema

### New Table: `conversation_pauses`

```sql
CREATE TABLE conversation_pauses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id VARCHAR(255) UNIQUE NOT NULL,
    phone_number VARCHAR(20) NOT NULL,
    agent_assignee_id VARCHAR(255),
    agent_email VARCHAR(255),
    agent_name VARCHAR(100),
    paused_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## API Methods Added

### DatabaseManager Methods

- `create_conversation_pause()` - Creates or updates a conversation pause
- `is_conversation_paused()` - Checks if a conversation is currently paused  
- `get_conversation_pause_info()` - Gets detailed pause information
- `remove_conversation_pause()` - Manually removes a pause
- `cleanup_expired_pauses()` - Cleans up expired pauses (for maintenance)

## Example Usage

### Agent Message Data Structure
```json
{
    "eventType": "sessionMessageSent",
    "id": "68b3fd6bcf4f6635df89d3fe",
    "conversationId": "68b3fa21e5a7b16373de06f6",
    "text": "للاسف لا يمكن",
    "owner": true,
    "assigneeId": "656d7ed0da548ff8371d50aa",
    "operatorEmail": "contracts@abar.app",
    "operatorName": "M. Ibramim",
    "waId": "966509491382"
}
```

### Flow

1. **Agent enters conversation** → Webhook receives message with `owner: true`
2. **Pause created** → Bot pauses for 10 hours for this `conversationId`
3. **User messages arrive** → Bot checks pause status and skips processing
4. **10 hours later** → Pause expires automatically, bot resumes normal operation

## Key Features

- **Automatic Detection**: No manual configuration needed
- **10 Hour Duration**: Configurable in the code (currently set to 10 hours)
- **Per-Conversation**: Each conversation is tracked independently
- **Agent Information**: Stores which agent caused the pause
- **Auto-Expiry**: Pauses automatically expire without manual intervention
- **Error Handling**: Gracefully handles database errors
- **Logging**: Full message journey logging for debugging

## Message Journey Logs

The system logs detailed information including:
- Agent detection events
- Pause creation/updates
- Message skipping due to pauses
- Pause expiry cleanup

## Error Handling

- Database errors during pause creation don't stop message processing
- Expired pauses are automatically cleaned up
- Failed pause checks default to allowing message processing
- All errors are logged for debugging

## Deployment

### Database Migration

Run the migration script to create the required table:
```bash
python database/migrate_add_conversation_pause.py
```

The feature is automatically active once deployed. The specific agent email that triggers pauses is configured in `app.py` in the `PAUSE_TRIGGER_AGENT_EMAILS` list.

## Monitoring

Check the message journey logs for entries with:
- `step_type: "contracts_agent_detection"` - contracts@abar.app agent entered conversation
- `step_type: "conversation_pause_check"` - Message skipped due to pause
- `status: "paused_by_agent"` - Conversation currently paused
- `status: "conversation_paused"` - New pause created

## Configuration

To add more agent emails that trigger pauses, update the `PAUSE_TRIGGER_AGENT_EMAILS` list in `app.py`:

```python
# Agent pause configuration - emails that trigger bot pause
PAUSE_TRIGGER_AGENT_EMAILS = ["contracts@abar.app", "support@abar.app"]
```
