# 🛡️ Database Safety Guide for Production

## ✅ Current Protection Status

Your production databases are now **FULLY PROTECTED** from git commits and pulls!

### 🔒 Protected Files & Directories:

```
database/data/           # All database files
database/backups/        # Database backups
vectorstore/data/        # ChromaDB and embeddings
vectorstore/backups/     # Vector store backups
logs/                   # Application logs
*.sqlite, *.sqlite3     # SQLite files
*.sqlite-shm, *.sqlite-wal  # SQLite auxiliary files
```

## 🚀 Safe Development Workflow

### 1. **When Pulling from GitHub:**
```bash
# Your production data is safe - these commands won't overwrite it:
git pull origin main
git merge origin/main
git rebase origin/main
```

### 2. **When Pushing Changes:**
```bash
# Database files are automatically excluded:
git add .
git commit -m "Your changes"
git push origin main
```

### 3. **Check What Will Be Committed:**
```bash
# Verify no database files are included:
git status
git diff --staged
```

## 🔧 Database Management Commands

### **Create Database Backup:**
```bash
# Create a timestamped backup
python -c "
import shutil
from datetime import datetime
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
shutil.copy2('database/data/chatbot.sqlite', f'database/data/chatbot_backup_{timestamp}.sqlite')
print(f'Backup created: chatbot_backup_{timestamp}.sqlite')
"
```

### **Check Database Status:**
```bash
# Verify database files exist
dir database\data\
dir vectorstore\data\
```

### **Verify Git Ignore is Working:**
```bash
# These should return empty (no database files):
git status --porcelain | findstr -i database
git status --porcelain | findstr -i vectorstore
```

## 🚨 Emergency Recovery

### If Database Files Accidentally Get Added to Git:

```bash
# Remove from staging (before commit):
git reset HEAD database/data/
git reset HEAD vectorstore/data/

# Remove from git tracking (after commit):
git rm --cached database/data/*.sqlite*
git rm --cached -r vectorstore/data/
git commit -m "Remove database files from tracking"
```

### If Someone Pulls and Overwrites Database:

```bash
# Restore from backup:
copy database\data\chatbot_backup_YYYYMMDD_HHMMSS.sqlite database\data\chatbot.sqlite

# Or restore from system backup/snapshot
```

## 📋 Best Practices

### ✅ **DO:**
- Regularly backup your database files
- Test git operations on a copy first
- Keep production and development databases separate
- Monitor git status before commits
- Create database snapshots before major changes

### ❌ **DON'T:**
- Manually add database files to git
- Commit backup files
- Share database files via email/chat
- Delete .gitignore database entries
- Work directly on production without backups

## 🔍 Quick Verification

Run this command to verify your protection is working:

```bash
# Should show no database files:
git check-ignore database/data/* vectorstore/data/*
```

## 📞 Troubleshooting

### Problem: "Database file appears in git status"
**Solution:** Check that .gitignore patterns are correct and files aren't already tracked.

### Problem: "Lost database after git pull"
**Solution:** Restore from backup - your .gitignore prevents this now.

### Problem: "Team member can't access database"
**Solution:** Each environment should have its own database - don't share via git.

---

## 🎯 Summary

✅ **Production database is protected**  
✅ **Git pulls won't overwrite your data**  
✅ **Git commits won't include database files**  
✅ **Full backup strategy documented**  

Your production data is now **COMPLETELY SAFE**! 🛡️
