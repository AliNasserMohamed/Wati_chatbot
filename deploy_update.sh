#!/bin/bash

# Auto-update script for Wati ChatBot server deployment
# This script pulls the latest code from GitHub and restarts the service

set -e  # Exit on any error

echo "🚀 Starting Wati ChatBot deployment update..."

# Configuration - Update these paths according to your server setup
PROJECT_DIR="/path/to/Wati_chatbot"  # Update this to your actual server path
SERVICE_NAME="wati-chatbot"          # Update this to your systemd service name
PYTHON_ENV="venv"                    # Virtual environment directory name

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if project directory exists
if [ ! -d "$PROJECT_DIR" ]; then
    print_error "Project directory $PROJECT_DIR not found!"
    exit 1
fi

# Change to project directory
cd "$PROJECT_DIR"
print_status "Changed to project directory: $PROJECT_DIR"

# Check if we're in a git repository
if [ ! -d ".git" ]; then
    print_error "Not a git repository! Please clone the repository first."
    exit 1
fi

# Backup current deployment (optional)
print_status "Creating backup of current deployment..."
BACKUP_DIR="/tmp/wati_chatbot_backup_$(date +%Y%m%d_%H%M%S)"
cp -r . "$BACKUP_DIR"
print_success "Backup created at: $BACKUP_DIR"

# Pull latest changes from GitHub
print_status "Pulling latest changes from GitHub..."
git fetch origin
git reset --hard origin/main  # Force update to match remote
print_success "Code updated successfully"

# Activate virtual environment if it exists
if [ -d "$PYTHON_ENV" ]; then
    print_status "Activating virtual environment..."
    source "$PYTHON_ENV/bin/activate"
    print_success "Virtual environment activated"
else
    print_warning "Virtual environment not found. Make sure to install dependencies manually."
fi

# Install/update dependencies
print_status "Installing/updating Python dependencies..."
pip install -r requirements.txt
print_success "Dependencies updated"

# Run database migrations
print_status "Running database migrations..."
python database/migrate_add_columns.py
print_success "Database migrations completed"

# Check if systemd service exists and restart it
if systemctl is-active --quiet "$SERVICE_NAME"; then
    print_status "Restarting $SERVICE_NAME service..."
    sudo systemctl restart "$SERVICE_NAME"
    print_success "Service restarted successfully"
    
    # Check service status
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        print_success "Service is running properly"
    else
        print_error "Service failed to start! Check logs with: sudo journalctl -u $SERVICE_NAME -f"
        exit 1
    fi
else
    print_warning "Service $SERVICE_NAME not found or not running."
    print_warning "You may need to start the application manually:"
    print_warning "python app.py"
fi

# Show latest commit info
print_status "Current deployment info:"
echo "Git commit: $(git log -1 --format='%h - %s (%ci)')"
echo "Git branch: $(git branch --show-current)"

print_success "🎉 Deployment update completed successfully!"
print_status "Your Wati ChatBot is now running the latest code."

# Optional: Show service logs
read -p "Do you want to view recent service logs? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_status "Showing recent service logs (press Ctrl+C to exit):"
    sudo journalctl -u "$SERVICE_NAME" -f --lines=20
fi 