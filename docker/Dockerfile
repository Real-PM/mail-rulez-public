# Mail-Rulez - Intelligent Email Management System
# Copyright (c) 2024 Real Project Management Solutions
# Dual-licensed: AGPL v3 / Commercial. See LICENSE-DUAL

# Multi-stage Dockerfile for Mail-Rulez containerization
# Optimized for production deployment with comprehensive logging

FROM python:3.10-slim AS base

# Build arguments for version information
ARG BUILD_COMMIT_HASH
ARG BUILD_DATE

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    BUILD_COMMIT_HASH=${BUILD_COMMIT_HASH} \
    BUILD_DATE=${BUILD_DATE}

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create app user for security
RUN groupadd -r mailrulez && useradd -r -g mailrulez mailrulez

# Development stage
FROM base AS development

WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application code
COPY . .

# Set configurable paths for development
ENV MAIL_RULEZ_APP_DIR=/app \
    MAIL_RULEZ_LOG_DIR=/app/logs \
    MAIL_RULEZ_DATA_DIR=/app/data \
    MAIL_RULEZ_LISTS_DIR=/app/lists \
    MAIL_RULEZ_CONFIG_DIR=/app/config

# Create directories with proper permissions
RUN mkdir -p ${MAIL_RULEZ_LOG_DIR} ${MAIL_RULEZ_LISTS_DIR} ${MAIL_RULEZ_DATA_DIR} ${MAIL_RULEZ_CONFIG_DIR} && \
    chown -R mailrulez:mailrulez /app

# Set environment for development
ENV FLASK_ENV=development \
    MAIL_RULEZ_LOG_LEVEL=DEBUG \
    MAIL_RULEZ_JSON_LOGS=false

USER mailrulez

EXPOSE 5001

CMD ["python", "web/app.py"]

# Production stage
FROM base AS production

WORKDIR /app

# Copy requirements and install production dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt && \
    pip install gunicorn

# Copy application code
COPY . .

# Create build-time version file
RUN echo "BUILD_COMMIT_HASH=\"${BUILD_COMMIT_HASH:-unknown}\"" > /app/.build_version && \
    echo "BUILD_DATE=\"${BUILD_DATE:-unknown}\"" >> /app/.build_version

# Set configurable paths for production
ENV MAIL_RULEZ_APP_DIR=/app \
    MAIL_RULEZ_LOG_DIR=/app/logs \
    MAIL_RULEZ_DATA_DIR=/app/data \
    MAIL_RULEZ_LISTS_DIR=/app/lists \
    MAIL_RULEZ_BACKUPS_DIR=/app/backups \
    MAIL_RULEZ_CONFIG_DIR=/app/config

# Create directories and set permissions
RUN mkdir -p ${MAIL_RULEZ_LOG_DIR} ${MAIL_RULEZ_LISTS_DIR} ${MAIL_RULEZ_DATA_DIR} ${MAIL_RULEZ_BACKUPS_DIR} ${MAIL_RULEZ_CONFIG_DIR} && \
    chown -R mailrulez:mailrulez /app

# Set production environment variables
ENV FLASK_ENV=production \
    CONTAINER_ENV=true \
    MAIL_RULEZ_LOG_LEVEL=INFO \
    MAIL_RULEZ_JSON_LOGS=true \
    MAIL_RULEZ_LOG_RETENTION_DAYS=30

# Install log rotation utility
RUN apt-get update && apt-get install -y logrotate && \
    rm -rf /var/lib/apt/lists/*

# Copy log rotation configuration
COPY docker/logrotate.conf /etc/logrotate.d/mailrulez

# Copy startup scripts
COPY docker/entrypoint.sh /entrypoint.sh
COPY docker/healthcheck.sh /healthcheck.sh
COPY docker/scripts/ /app/docker/scripts/
RUN chmod +x /entrypoint.sh /healthcheck.sh /app/docker/scripts/*.py

USER mailrulez

EXPOSE 5001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD /healthcheck.sh

# Volume mounts for persistent data (using environment variables)
VOLUME ["${MAIL_RULEZ_LOG_DIR}", "${MAIL_RULEZ_DATA_DIR}", "${MAIL_RULEZ_LISTS_DIR}", "${MAIL_RULEZ_BACKUPS_DIR}"]

ENTRYPOINT ["/entrypoint.sh"]
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:5001 --workers 2 --worker-class gthread --threads 4 --access-logfile ${MAIL_RULEZ_LOG_DIR}/access.log --error-logfile ${MAIL_RULEZ_LOG_DIR}/error.log web.app:application"]