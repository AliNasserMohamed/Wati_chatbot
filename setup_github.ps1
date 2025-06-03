# GitHub Setup Script for Wati ChatBot
# Run this script after creating your GitHub repository

param(
    [Parameter(Mandatory=$true)]
    [string]$GitHubUrl,  # e.g., https://github.com/YOUR_USERNAME/Wati_chatbot.git
    
    [string]$BranchName = "main"
)

Write-Host "🚀 Setting up GitHub connection for Wati ChatBot..." -ForegroundColor Blue

try {
    # Check if we're in a git repository
    if (-not (Test-Path ".git")) {
        Write-Host "❌ Error: Not in a git repository!" -ForegroundColor Red
        exit 1
    }

    # Add remote origin
    Write-Host "📡 Adding GitHub remote origin..." -ForegroundColor Cyan
    git remote add origin $GitHubUrl
    Write-Host "✅ Remote origin added successfully" -ForegroundColor Green

    # Push to GitHub
    Write-Host "⬆️ Pushing code to GitHub..." -ForegroundColor Cyan
    git push -u origin $BranchName
    Write-Host "✅ Code pushed successfully to GitHub!" -ForegroundColor Green

    # Show repository info
    Write-Host "`n📊 Repository Information:" -ForegroundColor Blue
    Write-Host "Remote URL: $GitHubUrl" -ForegroundColor White
    Write-Host "Branch: $BranchName" -ForegroundColor White
    
    $CommitCount = git rev-list --count HEAD
    Write-Host "Total commits: $CommitCount" -ForegroundColor White
    
    Write-Host "`n🎉 GitHub setup completed successfully!" -ForegroundColor Green
    Write-Host "Your Wati ChatBot is now available at: $GitHubUrl" -ForegroundColor Yellow

} catch {
    Write-Host "❌ GitHub setup failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Instructions for server deployment
Write-Host "`n📋 Next Steps for Server Deployment:" -ForegroundColor Blue
Write-Host "1. On your server, clone the repository:" -ForegroundColor White
Write-Host "   git clone $GitHubUrl" -ForegroundColor Gray
Write-Host "2. Set up virtual environment:" -ForegroundColor White
Write-Host "   cd Wati_chatbot && python -m venv venv" -ForegroundColor Gray
Write-Host "3. Install dependencies:" -ForegroundColor White
Write-Host "   source venv/bin/activate && pip install -r requirements.txt" -ForegroundColor Gray
Write-Host "4. Run database migration:" -ForegroundColor White
Write-Host "   python database/migrate_add_columns.py" -ForegroundColor Gray
Write-Host "5. Configure environment variables in .env file" -ForegroundColor White
Write-Host "6. Use deploy_update.sh (Linux) or deploy_update.ps1 (Windows) for future updates" -ForegroundColor White 