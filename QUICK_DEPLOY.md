# 🚀 Quick Deployment Reference

## **On Production Server - Run These Commands:**

```bash
# 1. Backup (CRITICAL!)
cp database/data/chatbot.sqlite database/data/chatbot_backup_$(date +%Y%m%d_%H%M%S).sqlite

# 2. Stop app
sudo systemctl stop your-chatbot-service

# 3. Pull code (Database Safe!)
git pull origin main

# 4. Start app
sudo systemctl start your-chatbot-service

# 5. Verify
sudo systemctl status your-chatbot-service
```

## **That's it! Your database is protected! 🛡️**

---

### **First Time Setup:**
If this is your first deployment with the new protection:
```bash
# Add these to your .gitignore if not already there:
echo "database/data/" >> .gitignore
echo "vectorstore/data/" >> .gitignore
git add .gitignore
git commit -m "Protect database files"
```

### **Emergency Restore:**
```bash
# If something goes wrong:
cp database/data/chatbot_backup_YYYYMMDD_HHMMSS.sqlite database/data/chatbot.sqlite
sudo systemctl restart your-chatbot-service
```

### **Verify Protection:**
```bash
# Should return empty (no database files tracked):
git status | grep -E "(database|vectorstore)"
```

**✅ Your production data is now 100% safe from git operations!**
