#!/bin/bash

# Papla Voice Generator Startup Script

echo "Starting Papla Voice Generator..."
echo "The application will be available at: http://localhost:5003"
echo "Press Ctrl+C to stop the server"
echo ""

# Check if virtual environment exists
if [ -d ".venv" ]; then
    echo "Activating virtual environment..."
    source .venv/bin/activate
else
    echo "No virtual environment found. Using system Python..."
fi

# Run the application
python3 papla_voice_web.py