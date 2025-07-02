#!/bin/bash
#
# Mail-Rulez - Intelligent Email Management System
# Copyright (c) 2024 Real Project Management Solutions
#
# This software is dual-licensed. See LICENSE-DUAL for details.
# Commercial licensing: license@mail-rulez.com
#


# Mail-Rulez Container Health Check Script
# Minimal health monitoring - web server response only

# Configuration
FLASK_PORT=${FLASK_PORT:-5001}
HEALTH_ENDPOINT="http://localhost:${FLASK_PORT}/auth/session/status"

# Simple web server health check
if command -v curl &> /dev/null; then
    response=$(curl -s -w "%{http_code}" -o /dev/null --connect-timeout 5 --max-time 10 "$HEALTH_ENDPOINT" 2>/dev/null || echo "000")
else
    # Fallback to wget if curl is not available
    response=$(wget -q -O /dev/null -T 10 --server-response "$HEALTH_ENDPOINT" 2>&1 | grep "HTTP/" | tail -1 | awk '{print $2}' 2>/dev/null || echo "000")
fi

# Check if we got a valid HTTP response
case "$response" in
    200|401|403)  # 200=OK, 401/403=Auth required but server is running
        exit 0
        ;;
    *)
        exit 1
        ;;
esac