#!/bin/sh
set -e

# ===========================================
# Docker Entrypoint Script
# Replaces environment variables in nginx config
# ===========================================

# Default values
BACKEND_HOST=${BACKEND_HOST:-backend}
BACKEND_PORT=${BACKEND_PORT:-8000}
CLIENT_MAX_BODY_SIZE=${CLIENT_MAX_BODY_SIZE:-20m}

# Export variables for envsubst
export BACKEND_HOST
export BACKEND_PORT
export CLIENT_MAX_BODY_SIZE

# Generate nginx config from template
envsubst '${BACKEND_HOST} ${BACKEND_PORT} ${CLIENT_MAX_BODY_SIZE}' \
    < /etc/nginx/templates/default.conf.template \
    > /etc/nginx/conf.d/default.conf

echo "Nginx configuration generated:"
echo "  Backend: ${BACKEND_HOST}:${BACKEND_PORT}"
echo "  Max Upload Size: ${CLIENT_MAX_BODY_SIZE}"

# Execute the main command
exec "$@"
