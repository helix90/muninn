#!/bin/sh
set -e

echo "Running database migrations..."
flask db upgrade

echo "Starting Muninn..."
exec "$@"
