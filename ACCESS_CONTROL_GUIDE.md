# Access Control System

## Overview
The access control system allows you to toggle between:
- **Open Access**: All users can access all chatbot agents
- **Restricted Access**: Only allowed phone numbers get full access, others get limited responses

## How It Works

### Configuration File
- Configuration is stored in `access_control_config.json`
- This file is automatically created with default settings
- The file is in `.gitignore` to avoid committing user-specific settings

### Dynamic Toggle
- Changes take effect **immediately** without server restart
- No source code modification required
- Configuration is checked at runtime for each message

### Web Interface
Access the control panel at: `/admin/user-access-control`

**Features:**
- Real-time status display
- Toggle switch for instant changes
- Display of allowed phone numbers
- Navigation to other admin pages

### API Endpoints

#### Get Status
```
GET /api/access-control/status
```
Returns current configuration state.

#### Toggle Access
```
POST /api/access-control/toggle
Content-Type: application/json

{
  "restricted_access": true/false
}
```

#### Get Allowed Numbers
```
GET /api/access-control/allowed-numbers
```
Returns list of phone numbers with full access.

### Allowed Phone Numbers
Currently configured numbers (in `app.py`):
- 201142765209
- 966138686475  
- 966505281144
- 966541794866
- 201003754330

### Behavior

**When Restricted Access is ON:**
- Allowed numbers: Full access to all agents
- Other numbers: Only embedding agent responses (knowledge base)

**When Restricted Access is OFF:**
- All numbers: Full access to all agents

## Technical Implementation

### Configuration Functions
- `load_access_control_config()`: Read current setting
- `save_access_control_config(bool)`: Save new setting  
- `is_access_restricted()`: Quick status check

### Runtime Check
```python
if is_access_restricted() and not is_allowed_user:
    return ""  # Block access
```

This approach is much better than the previous comment/uncomment system because:
- ✅ No server restart required
- ✅ No source code modification
- ✅ Instant changes
- ✅ Persistent settings
- ✅ Clean and maintainable
