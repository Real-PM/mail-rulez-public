#!/usr/bin/env python3
"""
Mail-Rulez - Intelligent Email Management System
Copyright (c) 2024 Real Project Management Solutions

This software is dual-licensed:
1. AGPL v3 for open source/self-hosted use
2. Commercial license for hosted services and enterprise use

For commercial licensing, contact: license@mail-rulez.com
See LICENSE-DUAL for complete licensing information.
"""


"""
Runtime Environment Generation for Mail-Rulez
Generates secure environment variables if not provided during container startup.
"""

import os
import sys
import json
import base64
import secrets
import logging
from datetime import datetime
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s'
)

def generate_secure_key(length=32):
    """Generate a cryptographically secure random key."""
    return base64.b64encode(secrets.token_bytes(length)).decode('utf-8')

def generate_flask_secret_key(length=32):
    """Generate a Flask secret key using secure random bytes."""
    return secrets.token_hex(length)

def load_existing_keys(key_file_path):
    """Load existing generated keys from persistent storage."""
    if not os.path.exists(key_file_path):
        return {}
    
    try:
        with open(key_file_path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logging.warning(f"Could not load existing keys: {e}")
        return {}

def save_generated_keys(key_file_path, keys):
    """Save generated keys to persistent storage."""
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(key_file_path), exist_ok=True)
        
        with open(key_file_path, 'w') as f:
            json.dump(keys, f, indent=2)
        
        # Set secure permissions (owner read/write only)
        os.chmod(key_file_path, 0o600)
        
        # Set ownership to mailrulez user (UID 999, GID 999) if running as root
        try:
            if os.getuid() == 0:  # Running as root
                os.chown(key_file_path, 999, 999)  # mailrulez:mailrulez
                logging.info(f"Set ownership of {key_file_path} to mailrulez:mailrulez")
        except (OSError, AttributeError):
            # AttributeError if os.getuid() not available on some systems
            # OSError if permission denied or user doesn't exist
            pass
            
        logging.info(f"Generated keys saved to {key_file_path}")
        
    except IOError as e:
        logging.error(f"Could not save generated keys: {e}")
        return False
    return True

def ensure_environment_variable(var_name, generator_func, existing_keys, force_regenerate=False):
    """Ensure an environment variable exists, generating if needed."""
    
    # Always prefer saved keys over environment variables for security
    if not force_regenerate and var_name in existing_keys:
        key_value = existing_keys[var_name]
        os.environ[var_name] = key_value
        logging.info(f"{var_name} loaded from persistent storage")
        return key_value
    
    # Check if already set in environment (only if no saved key)
    if not force_regenerate and os.getenv(var_name):
        logging.info(f"{var_name} already set in environment")
        return os.getenv(var_name)
    
    # Generate new key
    key_value = generator_func()
    os.environ[var_name] = key_value
    logging.info(f"{var_name} generated at runtime")
    
    return key_value

def main():
    """Main function to ensure secure environment setup."""
    
    logging.info("=== Mail-Rulez Runtime Environment Generation ===")
    
    # Configuration
    config_dir = os.getenv('MAIL_RULEZ_CONFIG_DIR', '/app/config')
    key_file_path = os.path.join(config_dir, 'generated-keys.json')
    
    # Load existing keys
    existing_keys = load_existing_keys(key_file_path)
    
    # Track newly generated keys
    generated_keys = {}
    keys_updated = False
    
    # Ensure MASTER_KEY
    master_key = ensure_environment_variable(
        'MASTER_KEY', 
        lambda: generate_secure_key(32),
        existing_keys
    )
    if 'MASTER_KEY' not in existing_keys or existing_keys.get('MASTER_KEY') != master_key:
        generated_keys['MASTER_KEY'] = master_key
        keys_updated = True
    
    # Ensure FLASK_SECRET_KEY
    flask_secret = ensure_environment_variable(
        'FLASK_SECRET_KEY',
        lambda: generate_flask_secret_key(32),
        existing_keys
    )
    if 'FLASK_SECRET_KEY' not in existing_keys or existing_keys.get('FLASK_SECRET_KEY') != flask_secret:
        generated_keys['FLASK_SECRET_KEY'] = flask_secret
        keys_updated = True
    
    # Save keys if any were generated or updated
    if keys_updated:
        # Merge with existing keys
        all_keys = {**existing_keys, **generated_keys}
        all_keys['generated_at'] = datetime.now().isoformat()
        all_keys['container_startup'] = True
        
        if save_generated_keys(key_file_path, all_keys):
            logging.info(f"Updated {len(generated_keys)} environment variables")
        else:
            logging.warning("Could not persist generated keys - they will be regenerated on restart")
    
    # Environment summary
    logging.info("Environment variables ready:")
    logging.info(f"  MASTER_KEY: {'✓ Set' if os.getenv('MASTER_KEY') else '✗ Missing'}")
    logging.info(f"  FLASK_SECRET_KEY: {'✓ Set' if os.getenv('FLASK_SECRET_KEY') else '✗ Missing'}")
    
    # Optional: Set additional default environment variables
    default_vars = {
        'MAIL_RULEZ_STRICT_VALIDATION': 'false',  # Graceful startup
        'MAIL_RULEZ_LOG_LEVEL': 'INFO',
        'FLASK_ENV': 'production',
        'PORT': '5001'
    }
    
    for var_name, default_value in default_vars.items():
        if not os.getenv(var_name):
            os.environ[var_name] = default_value
            logging.info(f"{var_name} set to default: {default_value}")
    
    logging.info("=== Environment Generation Complete ===")
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        logging.error(f"Environment generation failed: {e}")
        sys.exit(1)
