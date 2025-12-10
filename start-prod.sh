#!/bin/bash
#
# Muninn Application Startup Script - Production Mode
# This script starts the application using production settings
#

# Check if .env file exists
if [ ! -f .env ]; then
    echo "Error: .env file not found!"
    echo "Please copy env.example to .env and configure it:"
    echo "  cp env.example .env"
    echo "  nano .env"
    exit 1
fi

# Load environment variables from .env file
set -a
source .env
set +a

# Override to ensure production settings
export FLASK_ENV=production
export FLASK_DEBUG=False

# Validate required variables
if [ -z "$SECRET_KEY" ] || [ "$SECRET_KEY" = "your-super-secret-key-change-this-in-production" ]; then
    echo "Error: SECRET_KEY must be set to a secure random value in .env"
    echo "Generate one with: python -c 'import secrets; print(secrets.token_hex(32))'"
    exit 1
fi

if [ -z "$DATABASE_URL" ]; then
    echo "Error: DATABASE_URL must be set in .env"
    exit 1
fi

# Print startup information
echo "================================================"
echo "Starting Muninn Application (Production Mode)"
echo "================================================"
echo "Environment: $FLASK_ENV"
echo "Debug Mode: $FLASK_DEBUG"
echo "Host: $FLASK_HOST"
echo "Port: $FLASK_PORT"
echo "================================================"
echo ""
echo "Application will be accessible at:"
echo "  - Local: http://localhost:$FLASK_PORT"
echo "  - Network: http://$(hostname -I | awk '{print $1}'):$FLASK_PORT"
echo ""
echo "Press Ctrl+C to stop the server"
echo "================================================"
echo ""

# Run the application
python run.py
