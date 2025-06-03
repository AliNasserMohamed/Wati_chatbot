#!/bin/bash
# Setup script for Ubuntu server environment

echo "======================================="
echo "Abar Chatbot - Ubuntu Server Setup Tool"
echo "======================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run this script as root (using sudo)."
  exit 1
fi

# Set working directory to the script location
cd "$(dirname "$0")"
SCRIPT_DIR="$(pwd)"
echo "Working directory: $SCRIPT_DIR"

# Check for .env file
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo "Creating .env file..."
    echo "Enter your OpenAI API Key (starts with 'sk-'):"
    read OPENAI_API_KEY
    
    echo "Enter your Wati API Key:"
    read WATI_API_KEY
    
    echo "Enter your Wati API URL (press Enter for default):"
    read WATI_API_URL
    WATI_API_URL=${WATI_API_URL:-"https://live-mt-server.wati.io/301269/api/v1"}
    
    # Clean inputs to prevent whitespace or newline issues
    OPENAI_API_KEY=$(echo "$OPENAI_API_KEY" | tr -d '\r\n\t ')
    WATI_API_KEY=$(echo "$WATI_API_KEY" | tr -d '\r\n\t ')
    WATI_API_URL=$(echo "$WATI_API_URL" | tr -d '\r\n\t ')
    
    echo "Creating .env file..."
    cat > "$SCRIPT_DIR/.env" << EOL
OPENAI_API_KEY=$OPENAI_API_KEY
WATI_API_KEY=$WATI_API_KEY
WATI_API_URL=$WATI_API_URL
WATI_WEBHOOK_VERIFY_TOKEN=your_verification_token
EOL
    
    # Convert Windows line endings (CRLF) to Unix (LF) if needed
    dos2unix "$SCRIPT_DIR/.env" 2>/dev/null || true
    
    echo ".env file created."
else
    echo ".env file already exists."
    
    # Fix any line ending issues in existing .env file
    dos2unix "$SCRIPT_DIR/.env" 2>/dev/null || true
    echo "Fixed any potential line ending issues in .env file."
fi

# Set permissions
echo "Setting proper permissions..."
chmod 644 "$SCRIPT_DIR/.env"
chmod +x "$SCRIPT_DIR/check_env.py"
chmod +x "$SCRIPT_DIR/app.py"

# Install dos2unix if needed
if ! command -v dos2unix &> /dev/null; then
    echo "Installing dos2unix utility..."
    apt-get update -qq && apt-get install -qq -y dos2unix
fi

# Clean any existing API keys in the .env file
echo "Cleaning environment variables in .env file..."
sed -i 's/\r//g' "$SCRIPT_DIR/.env"

# Verify environment variables
echo "Checking environment variables..."
python3 "$SCRIPT_DIR/check_env.py"

echo "======================================="
echo "Setup completed!"
echo "You can now run the application with:"
echo "python app.py"
echo "=======================================" 