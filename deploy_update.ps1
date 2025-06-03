# Auto-update script for Wati ChatBot server deployment (Windows PowerShell)
# This script pulls the latest code from GitHub and restarts the service

param(
    [string]$ProjectDir = "C:\path\to\Wati_chatbot",  # Update this to your actual server path
    [string]$ServiceName = "wati-chatbot",            # Update this to your Windows service name
    [string]$PythonEnv = "venv"                       # Virtual environment directory name
)

# Set error action preference
$ErrorActionPreference = "Stop"

Write-Host "🚀 Starting Wati ChatBot deployment update..." -ForegroundColor Blue

# Function to print colored output
function Write-Status {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

try {
    # Check if project directory exists
    if (-not (Test-Path $ProjectDir)) {
        Write-Error "Project directory $ProjectDir not found!"
        exit 1
    }

    # Change to project directory
    Set-Location $ProjectDir
    Write-Status "Changed to project directory: $ProjectDir"

    # Check if we're in a git repository
    if (-not (Test-Path ".git")) {
        Write-Error "Not a git repository! Please clone the repository first."
        exit 1
    }

    # Backup current deployment (optional)
    Write-Status "Creating backup of current deployment..."
    $BackupDir = "C:\temp\wati_chatbot_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
    Copy-Item -Path "." -Destination $BackupDir -Recurse -Force
    Write-Success "Backup created at: $BackupDir"

    # Pull latest changes from GitHub
    Write-Status "Pulling latest changes from GitHub..."
    git fetch origin
    git reset --hard origin/main  # Force update to match remote
    Write-Success "Code updated successfully"

    # Activate virtual environment if it exists
    $VenvPath = Join-Path $ProjectDir $PythonEnv
    if (Test-Path $VenvPath) {
        Write-Status "Activating virtual environment..."
        $ActivateScript = Join-Path $VenvPath "Scripts\Activate.ps1"
        if (Test-Path $ActivateScript) {
            & $ActivateScript
            Write-Success "Virtual environment activated"
        } else {
            Write-Warning "Virtual environment activation script not found."
        }
    } else {
        Write-Warning "Virtual environment not found. Make sure to install dependencies manually."
    }

    # Install/update dependencies
    Write-Status "Installing/updating Python dependencies..."
    python -m pip install -r requirements.txt
    Write-Success "Dependencies updated"

    # Run database migrations
    Write-Status "Running database migrations..."
    python database/migrate_add_columns.py
    Write-Success "Database migrations completed"

    # Check if Windows service exists and restart it
    $Service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($Service) {
        Write-Status "Restarting $ServiceName service..."
        Restart-Service -Name $ServiceName -Force
        Write-Success "Service restarted successfully"
        
        # Check service status
        $ServiceStatus = Get-Service -Name $ServiceName
        if ($ServiceStatus.Status -eq "Running") {
            Write-Success "Service is running properly"
        } else {
            Write-Error "Service failed to start! Check Windows Event Logs for details."
            exit 1
        }
    } else {
        Write-Warning "Service $ServiceName not found."
        Write-Warning "You may need to start the application manually:"
        Write-Warning "python app.py"
    }

    # Show latest commit info
    Write-Status "Current deployment info:"
    $CommitInfo = git log -1 --format='%h - %s (%ci)'
    $Branch = git branch --show-current
    Write-Host "Git commit: $CommitInfo"
    Write-Host "Git branch: $Branch"

    Write-Success "🎉 Deployment update completed successfully!"
    Write-Status "Your Wati ChatBot is now running the latest code."

    # Optional: Show service logs (if applicable)
    $ViewLogs = Read-Host "Do you want to view recent Windows Event Logs? (y/n)"
    if ($ViewLogs -eq "y" -or $ViewLogs -eq "Y") {
        Write-Status "Opening Windows Event Viewer..."
        eventvwr.exe
    }

} catch {
    Write-Error "Deployment failed: $($_.Exception.Message)"
    Write-Error "Stack trace: $($_.Exception.StackTrace)"
    exit 1
} 