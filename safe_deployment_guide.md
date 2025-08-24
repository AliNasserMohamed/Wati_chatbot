# 🛡️ Safe Deployment Guide for Production

## ⚠️ NEVER DO THESE IN PRODUCTION:

1. **Don't delete database files while app is running**
2. **Don't directly edit SQLite files**
3. **Don't force-kill processes during database operations**
4. **Don't run out of disk space**

## ✅ SAFE DEPLOYMENT PROCESS:

### 1. Before ANY Changes:
```bash
# Create backup
python database_maintenance.py

# Check database health
sqlite3 database/data/chatbot.sqlite "PRAGMA integrity_check;"
```

### 2. Safe Application Restart:
```bash
# Graceful shutdown (allows DB operations to complete)
sudo systemctl stop your-chatbot-app

# Wait for processes to finish
sleep 5

# Restart
sudo systemctl start your-chatbot-app
```

### 3. Safe Database Reset (if needed):
```bash
# 1. Stop application
sudo systemctl stop your-chatbot-app

# 2. Backup current database
cp database/data/chatbot.sqlite database/data/chatbot.sqlite.backup_$(date +%Y%m%d_%H%M%S)

# 3. Remove database
rm database/data/chatbot.sqlite

# 4. Start application (will create fresh database)
sudo systemctl start your-chatbot-app

# 5. Re-populate data
python -c "
import asyncio
from database.db_utils import SessionLocal
from services.data_scraper import DataScraperService

async def repopulate():
    scraper = DataScraperService()
    db = SessionLocal()
    try:
        await scraper.full_clean_slate_sync(db)
    finally:
        db.close()

asyncio.run(repopulate())
"
```

### 4. Set up Automated Maintenance:
```bash
# Install as systemd service
sudo cp database_maintenance.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable database_maintenance
sudo systemctl start database_maintenance
```

## 🔧 Database Maintenance Service:

Create `/etc/systemd/system/database_maintenance.service`:
```ini
[Unit]
Description=Database Maintenance Service
After=network.target

[Service]
Type=simple
User=your-app-user
WorkingDirectory=/path/to/your/chatbot
ExecStart=/usr/bin/python3 database_maintenance.py schedule
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
```

## 📊 Monitoring Commands:

```bash
# Check database size
du -h database/data/chatbot.sqlite

# Check database integrity
sqlite3 database/data/chatbot.sqlite "PRAGMA integrity_check;"

# Check application logs
journalctl -u your-chatbot-app -f

# Check maintenance logs
journalctl -u database_maintenance -f
```

## 🚨 Emergency Recovery Commands:

```bash
# If database is corrupted:
python fix_corrupted_database.py

# If app won't start:
sudo systemctl status your-chatbot-app
sudo journalctl -u your-chatbot-app --since "1 hour ago"
```
