#!/bin/bash

# Run Flask Calendar App for Local Network Access
# This script starts the Flask app so it can be accessed from other devices on your local network

echo "========================================"
echo "Flask Calendar - Local Network Access"
echo "========================================"
echo ""

# Check if .env file exists
if [ ! -f .env ]; then
    echo "Error: .env file not found!"
    echo "Copying .env.example to .env..."
    cp .env.example .env
    echo "Please edit .env and set a secure SECRET_KEY, then run this script again."
    exit 1
fi

# Load environment variables
source .env

# Get the local IP address
echo "Finding your local IP address..."
LOCAL_IP=$(ifconfig | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | head -n 1)

if [ -z "$LOCAL_IP" ]; then
    echo "Warning: Could not detect local IP address"
    echo "You may need to find it manually with: ifconfig"
else
    echo "Your local IP address: $LOCAL_IP"
fi

echo ""
echo "Starting Flask app on port ${PORT:-5002}..."
echo ""
echo "Access the app from:"
echo "  - This computer: http://localhost:${PORT:-5002}"
if [ -n "$LOCAL_IP" ]; then
    echo "  - Other devices on your network: http://$LOCAL_IP:${PORT:-5002}"
fi
echo ""
echo "Press Ctrl+C to stop the server"
echo "========================================"
echo ""

# Run with Python directly for development
# For production, use: gunicorn app:app --bind 0.0.0.0:${PORT:-5002}
python3 app.py
