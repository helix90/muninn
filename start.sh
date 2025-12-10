#!/bin/bash
#
# Muninn Application Startup Script
# This script sets environment variables and starts the Flask application
#

# Flask Configuration
export FLASK_ENV=development
export FLASK_DEBUG=True
export FLASK_HOST=0.0.0.0
export FLASK_PORT=5050

# Application Configuration
export SECRET_KEY=dev-secret-key-change-in-production
export LOG_LEVEL=INFO

# Database Configuration
export DATABASE_URL=postgresql://muninn:muninn_pass@localhost:5432/muninn_dev
export TEST_DATABASE_URL=postgresql://muninn:muninn_pass@localhost:5432/muninn_test

# Database Connection Pooling
export DB_POOL_SIZE=10
export DB_POOL_TIMEOUT=20
export DB_POOL_RECYCLE=3600
export DB_MAX_OVERFLOW=20

# Print startup information
echo "================================================"
echo "Starting Muninn Application"
echo "================================================"
echo "Environment: $FLASK_ENV"
echo "Debug Mode: $FLASK_DEBUG"
echo "Host: $FLASK_HOST"
echo "Port: $FLASK_PORT"
echo "Database: $DATABASE_URL"
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
