#!/bin/bash
# Docker entrypoint script to handle environment setup

# Ensure required directories exist
mkdir -p /app/data /app/reports

# If .env doesn't exist, exit with error
if [ ! -f /app/.env ]; then
    echo "Error: .env file not found. Please create .env file with your credentials."
    exit 1
fi

# Execute the command passed to the container
exec "$@"

