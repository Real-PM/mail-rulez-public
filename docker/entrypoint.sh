#!/bin/bash
#
# Mail-Rulez - Intelligent Email Management System
# Copyright (c) 2024 Real Project Management Solutions
#
# This software is dual-licensed. See LICENSE-DUAL for details.
# Commercial licensing: license@mail-rulez.com
#


# Mail-Rulez Container Entrypoint Script
# Handles initialization, log setup, and graceful shutdown

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1" | tee -a /app/logs/container.log
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1" | tee -a /app/logs/container.log
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a /app/logs/container.log
}

log_debug() {
    if [ "${MAIL_RULEZ_LOG_LEVEL:-INFO}" = "DEBUG" ]; then
        echo -e "${BLUE}[DEBUG]${NC} $1" | tee -a /app/logs/container.log
    fi
}

# Trap signals for graceful shutdown
cleanup() {
    log_info "Received shutdown signal, stopping services..."
    
    # Stop any running email processing services
    if [ -f /app/web/app.py ]; then
        log_info "Stopping Mail-Rulez services..."
        # Add service cleanup here if needed
    fi
    
    # Final log rotation
    if command -v logrotate &> /dev/null; then
        log_info "Performing final log rotation..."
        logrotate -f /etc/logrotate.d/mailrulez 2>/dev/null || true
    fi
    
    log_info "Shutdown complete"
    exit 0
}

trap cleanup SIGTERM SIGINT SIGQUIT

# Container startup
log_info "=== Mail-Rulez Container Starting ==="
log_info "Container ID: $(hostname)"
log_info "Start time: $(date)"
log_info "Environment: ${FLASK_ENV:-production}"

# Step 1: Generate secure environment if needed
log_info "Ensuring secure environment setup..."
if [ -f "/app/docker/scripts/generate_environment.py" ]; then
    python3 /app/docker/scripts/generate_environment.py || {
        log_error "Environment generation failed"
        if [ "${MAIL_RULEZ_STRICT_VALIDATION:-false}" = "true" ]; then
            log_error "Exiting due to environment generation failure"
            exit 1
        else
            log_warn "Continuing despite environment generation failure"
        fi
    }
else
    log_warn "Environment generation script not found - using existing environment"
fi

# Environment validation
log_info "Validating environment..."

# Check Python version
PYTHON_VERSION=$(python --version 2>&1)
log_info "Python version: $PYTHON_VERSION"

# Check required directories using environment variables
REQUIRED_DIRS=(
    "${MAIL_RULEZ_LOG_DIR:-/app/logs}"
    "${MAIL_RULEZ_DATA_DIR:-/app/data}"
    "${MAIL_RULEZ_LISTS_DIR:-/app/lists}"
    "${MAIL_RULEZ_BACKUPS_DIR:-/app/backups}"
    "${MAIL_RULEZ_CONFIG_DIR:-/app/config}"
)

# Volume mount validation
validate_volume_mounts() {
    local validation_errors=0
    
    for dir in "${REQUIRED_DIRS[@]}"; do
        if [ ! -d "$dir" ]; then
            log_info "Creating directory: $dir"
            mkdir -p "$dir" || {
                log_error "Failed to create directory: $dir"
                validation_errors=$((validation_errors + 1))
                continue
            }
        fi
        
        # Test write permissions
        if ! touch "$dir/.write_test" 2>/dev/null; then
            log_error "No write permission for directory: $dir"
            validation_errors=$((validation_errors + 1))
        else
            rm -f "$dir/.write_test"
            log_debug "Write permission confirmed for: $dir"
        fi
        
        # Ensure proper ownership if possible
        if [ "$(stat -c %U "$dir" 2>/dev/null)" != "mailrulez" ] && [ "$(id -u)" = "0" ]; then
            log_warn "Fixing ownership for $dir"
            chown mailrulez:mailrulez "$dir" 2>/dev/null || {
                log_warn "Could not change ownership for $dir - may affect functionality"
            }
        fi
    done
    
    if [ $validation_errors -gt 0 ]; then
        log_error "Volume mount validation failed with $validation_errors errors"
        log_error "Please check volume mounts and permissions"
        return 1
    fi
    
    log_info "Volume mount validation completed successfully"
    return 0
}

# Run validation
validate_volume_mounts || {
    log_error "Critical: Volume mount validation failed"
    if [ "${MAIL_RULEZ_STRICT_VALIDATION:-true}" = "true" ]; then
        log_error "Exiting due to validation failures (set MAIL_RULEZ_STRICT_VALIDATION=false to continue)"
        exit 1
    else
        log_warn "Continuing despite validation failures"
    fi
}

# Log configuration
log_info "Setting up logging configuration..."
log_info "Log directory: ${MAIL_RULEZ_LOG_DIR:-/app/logs}"
log_info "Log level: ${MAIL_RULEZ_LOG_LEVEL:-INFO}"
log_info "JSON logging: ${MAIL_RULEZ_JSON_LOGS:-true}"
log_info "Retention days: ${MAIL_RULEZ_LOG_RETENTION_DAYS:-30}"

# Create initial log files with proper permissions
LOG_DIR="${MAIL_RULEZ_LOG_DIR:-/app/logs}"
LOG_FILES=("mail_rulez.log" "email_processing.log" "security.log" "errors.log" "container.log")
for log_file in "${LOG_FILES[@]}"; do
    touch "$LOG_DIR/$log_file"
    chmod 644 "$LOG_DIR/$log_file" 2>/dev/null || log_warn "Could not set permissions for $LOG_DIR/$log_file"
done

# Setup log rotation (optional feature with graceful degradation)
if [ "${MAIL_RULEZ_ENABLE_LOG_ROTATION:-true}" = "true" ]; then
    if command -v logrotate &> /dev/null; then
        log_info "Setting up log rotation..."
        
        # Update retention in logrotate config based on environment variable
        RETENTION_DAYS=${MAIL_RULEZ_LOG_RETENTION_DAYS:-30}
        if [ -f /etc/logrotate.d/mailrulez ]; then
            sed -i "s/rotate 30/rotate $RETENTION_DAYS/g" /etc/logrotate.d/mailrulez 2>/dev/null || {
                log_warn "Could not update log rotation config - using defaults"
            }
            
            # Test logrotate configuration
            if logrotate -d /etc/logrotate.d/mailrulez &>/dev/null; then
                log_info "Log rotation configured successfully (${RETENTION_DAYS} days retention)"
            else
                log_warn "Log rotation configuration test failed - logs will not be rotated automatically"
            fi
        else
            log_warn "Log rotation config file not found - logs will not be rotated automatically"
        fi
    else
        log_warn "logrotate not available - manual log management required"
        log_warn "Set MAIL_RULEZ_ENABLE_LOG_ROTATION=false to disable this warning"
    fi
else
    log_info "Log rotation disabled via configuration"
fi

# Database/configuration setup
log_info "Checking application configuration..."

# Check if configuration files exist using environment variables
CONFIG_DIR="${MAIL_RULEZ_CONFIG_DIR:-/app}"
MASTER_KEY_FILE="$CONFIG_DIR/.master_key"
SECURE_CONFIG_FILE="$CONFIG_DIR/secure_config.json"

if [ ! -f "$MASTER_KEY_FILE" ] && [ -z "$MAIL_RULEZ_MASTER_KEY" ] && [ -z "$MASTER_KEY" ]; then
    log_warn "No master key found - should have been generated during environment setup"
elif [ -n "$MASTER_KEY" ]; then
    log_info "Master key configured via environment variable"
fi

if [ ! -f "$SECURE_CONFIG_FILE" ]; then
    log_info "No configuration found - initial setup required"
fi

# Log configuration paths
log_debug "Master key file: $MASTER_KEY_FILE"
log_debug "Secure config file: $SECURE_CONFIG_FILE"

# Network connectivity check (optional, with graceful degradation)
if [ "${MAIL_RULEZ_SKIP_NETWORK_CHECK:-false}" != "true" ]; then
    log_info "Checking network connectivity..."
    if timeout 5 ping -c 1 8.8.8.8 &> /dev/null; then
        log_info "Network connectivity verified"
    else
        log_warn "Limited network connectivity detected - some features may be unavailable"
        log_warn "Set MAIL_RULEZ_SKIP_NETWORK_CHECK=true to disable this check"
    fi
else
    log_debug "Network connectivity check skipped"
fi

# Resource monitoring setup
log_info "System resources:"
if command -v free >/dev/null 2>&1; then
    log_info "  Memory: $(free -h | awk '/^Mem:/ {print $2}') total, $(free -h | awk '/^Mem:/ {print $7}') available"
else
    log_info "  Memory: not available (free command not installed)"
fi
log_info "  Disk: $(df -h /app | awk 'NR==2 {print $4}') free space"
log_info "  CPU cores: $(nproc)"

# Start background log rotation (optional with graceful degradation)
if [ "${FLASK_ENV:-production}" = "production" ] && [ "${MAIL_RULEZ_ENABLE_LOG_ROTATION:-true}" = "true" ]; then
    if [ -f /etc/logrotate.d/mailrulez ] && command -v logrotate &> /dev/null; then
        log_info "Starting background log rotation cron job..."
        (
            while true; do
                sleep 3600  # Run every hour
                if [ -f /etc/logrotate.d/mailrulez ]; then
                    logrotate /etc/logrotate.d/mailrulez 2>/dev/null || {
                        log_warn "Log rotation failed - continuing operation"
                    }
                fi
            done
        ) &
        LOG_ROTATION_PID=$!
        log_debug "Log rotation process PID: $LOG_ROTATION_PID"
    else
        log_warn "Background log rotation not available - logs will accumulate"
    fi
fi

# Application-specific setup
log_info "Initializing Mail-Rulez application..."

# Generate version information if script exists
if [ -f "/app/scripts/generate_version.py" ]; then
    log_info "Generating version information..."
    cd /app
    
    # Check if build-time version file exists (created during Docker build)
    if [ -f "/app/.build_version" ]; then
        log_info "Using build-time version information from .build_version"
        source /app/.build_version
        
        # Create version file using build-time information
        python3 -c "
import sys
sys.path.append('/app')
from scripts.generate_version import generate_version_info, write_version_py

# Override the git commit hash detection with build-time value
def get_git_commit_hash():
    return '${BUILD_COMMIT_HASH:-unknown}'

# Monkey patch the function
import scripts.generate_version
scripts.generate_version.get_git_commit_hash = get_git_commit_hash

# Generate version with build-time commit hash
version_info = generate_version_info()
write_version_py(version_info)
print('Version file written to: /app/version.py')
"
    else
        # Use build-time commit hash if provided, otherwise detect from git
        if [ -n "${BUILD_COMMIT_HASH}" ]; then
            log_info "Using build-time commit hash: ${BUILD_COMMIT_HASH}"
            # Create a modified version script that uses the build-time hash
            python3 -c "
import sys
sys.path.append('/app')
from scripts.generate_version import generate_version_info, write_version_py

# Override the git commit hash detection
def get_git_commit_hash():
    return '${BUILD_COMMIT_HASH}'

# Monkey patch the function
import scripts.generate_version
scripts.generate_version.get_git_commit_hash = get_git_commit_hash

# Generate version with build-time commit hash
version_info = generate_version_info()
write_version_py(version_info)
print('Version file written to: /app/version.py')
"
        else
            python3 scripts/generate_version.py 2>/dev/null || {
                log_warn "Could not generate version information - using defaults"
            }
        fi
    fi
fi

# Set default Flask configuration if not provided
export FLASK_PORT=${FLASK_PORT:-5001}
export FLASK_HOST=${FLASK_HOST:-0.0.0.0}

# Load any custom initialization scripts
if [ -d "/app/docker/init.d" ]; then
    for script in /app/docker/init.d/*.sh; do
        if [ -f "$script" ] && [ -x "$script" ]; then
            log_info "Running initialization script: $(basename "$script")"
            "$script" || log_warn "Initialization script failed: $(basename "$script")"
        fi
    done
fi

log_info "=== Container initialization complete ==="
log_info "Starting application with command: $*"

# Execute the main command
exec "$@"