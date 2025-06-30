# Mail-Rulez - Intelligent Email Management System
# Copyright (c) 2024 Real Project Management Solutions
# Dual-licensed: AGPL v3 / Commercial. See LICENSE-DUAL

FROM python:3.9-slim AS base

# Build arguments
ARG VERSION=1.0.0
ARG BUILD_DATE
ARG VCS_REF

# Labels as per OCI image spec
LABEL org.opencontainers.image.title="Mail-Rulez"
LABEL org.opencontainers.image.description="Intelligent Email Management System - Automate email processing with rules-based filtering"
LABEL org.opencontainers.image.version=$VERSION
LABEL org.opencontainers.image.created=$BUILD_DATE
LABEL org.opencontainers.image.authors="Real Project Management Solutions <support@mail-rulez.com>"
LABEL org.opencontainers.image.url="https://mail-rulez.com"
LABEL org.opencontainers.image.documentation="https://github.com/Real-PM/mail-rulez-public/wiki"
LABEL org.opencontainers.image.source="https://github.com/Real-PM/mail-rulez-public"
LABEL org.opencontainers.image.revision=$VCS_REF
LABEL org.opencontainers.image.vendor="Real Project Management Solutions"
LABEL org.opencontainers.image.licenses="AGPL-3.0 OR Commercial"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -g 1000 mailrulez && \
    useradd -r -u 1000 -g mailrulez -s /bin/bash -m mailrulez

# Set working directory
WORKDIR /app

# Copy requirements first (better layer caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code with proper ownership
COPY --chown=mailrulez:mailrulez src/ ./
COPY --chown=mailrulez:mailrulez web/ ./web/
COPY --chown=mailrulez:mailrulez services/ ./services/
COPY --chown=mailrulez:mailrulez retention/ ./retention/
COPY --chown=mailrulez:mailrulez docker/entrypoint.sh ./
COPY --chown=mailrulez:mailrulez docker/healthcheck.sh ./
COPY --chown=mailrulez:mailrulez LICENSE* ./

# Create necessary directories with proper permissions
RUN mkdir -p /app/config /app/data /app/lists /app/logs && \
    chown -R mailrulez:mailrulez /app && \
    chmod -R 755 /app && \
    chmod +x entrypoint.sh healthcheck.sh

# Create version file
RUN echo $VERSION > /app/VERSION

# Switch to non-root user
USER mailrulez

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MAIL_RULEZ_VERSION=$VERSION \
    PORT=5001 \
    LOG_LEVEL=INFO \
    TZ=UTC

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD ./healthcheck.sh || exit 1

# Expose port
EXPOSE 5001

# Volume mount points
VOLUME ["/app/config", "/app/data", "/app/lists", "/app/logs"]

# Entrypoint and command
ENTRYPOINT ["./entrypoint.sh"]
CMD ["python", "web/app.py"]