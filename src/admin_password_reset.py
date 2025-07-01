#!/usr/bin/env python3
"""
CLI tool for resetting admin password
For emergency password recovery when web interface is not accessible
"""

import os
import sys
import getpass
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from security import SecurityManager, SecureConfig
from config import get_config
import bcrypt


def main():
    """Main CLI function for password reset"""
    print("=" * 60)
    print("Mail-Rulez Admin Password Reset Tool")
    print("=" * 60)
    print()
    
    # Get config and check if admin user exists
    config = get_config()
    admin_file = config.config_dir / '.admin_user'
    if not admin_file.exists():
        print("❌ Error: No admin user found.")
        print(f"   Expected at: {admin_file}")
        print("   Run initial setup first to create an admin account.")
        return 1
    
    try:
        # Read current admin data
        admin_data = admin_file.read_text().strip()
        current_username, _ = admin_data.split(':', 1)
        
        print(f"📋 Current admin username: {current_username}")
        print()
        
        # Confirm reset action
        print("⚠️  WARNING: This will reset the admin password!")
        confirm = input("   Continue? (type 'yes' to confirm): ").strip().lower()
        
        if confirm != 'yes':
            print("❌ Password reset cancelled.")
            return 0
        
        print()
        
        # Get new password
        while True:
            new_password = getpass.getpass("🔐 Enter new admin password: ")
            if len(new_password) < 8:
                print("❌ Password must be at least 8 characters long.")
                continue
            
            confirm_password = getpass.getpass("🔐 Confirm new password: ")
            if new_password != confirm_password:
                print("❌ Passwords do not match. Please try again.")
                continue
            
            break
        
        print()
        print("🔄 Resetting password...")
        
        # Initialize security manager
        security_manager = SecurityManager(SecureConfig())
        
        # Hash the new password
        hashed_password = security_manager.hash_user_password(new_password)
        
        # Update admin file
        new_admin_data = f"{current_username}:{hashed_password}"
        admin_file.write_text(new_admin_data)
        admin_file.chmod(0o600)
        
        print("✅ Password reset successfully!")
        print(f"   Username: {current_username}")
        print("   You can now log in with your new password.")
        print()
        
        # Clean up any reset tokens
        cleanup_reset_tokens(config)
        
        return 0
        
    except Exception as e:
        print(f"❌ Error resetting password: {e}")
        return 1


def cleanup_reset_tokens(config):
    """Clean up any existing reset tokens"""
    try:
        token_files = list(config.config_dir.glob('.reset_token_*'))
        if token_files:
            print("🧹 Cleaning up old reset tokens...")
            for token_file in token_files:
                token_file.unlink()
            print(f"   Removed {len(token_files)} old token(s).")
    except Exception as e:
        print(f"⚠️  Warning: Could not clean up reset tokens: {e}")


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n❌ Operation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)