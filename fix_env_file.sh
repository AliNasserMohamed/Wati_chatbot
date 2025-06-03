#!/bin/bash
# Quick fix for .env file issues with line endings and whitespace

echo "Fixing .env file issues..."

# Check if .env exists
if [ ! -f ".env" ]; then
  echo "ERROR: .env file not found! Run this script from your project root directory."
  exit 1
fi

# Make backup
cp .env .env.bak
echo "Backup created: .env.bak"

# Remove carriage returns and clean whitespace
echo "Removing invalid characters from .env file..."
sed -i 's/\r//g' .env

# Clean values specifically
echo "Cleaning API key values..."
# Read each line, clean it, and write back
while IFS= read -r line || [ -n "$line" ]; do
  if [[ $line == OPENAI_API_KEY=* || $line == WATI_API_KEY=* || $line == WATI_API_URL=* ]]; then
    # Get the key and value
    key="${line%%=*}"
    value="${line#*=}"
    # Trim the value
    clean_value=$(echo "$value" | tr -d ' \t\r\n')
    # Replace the line in the file
    sed -i "s|$key=.*|$key=$clean_value|" .env
  fi
done < .env

echo "Fixed .env file. Original saved as .env.bak."
echo "Run 'cat .env' to verify the contents." 