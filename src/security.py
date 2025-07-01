"""
Security module for Mail-Rulez

Provides secure storage and handling of sensitive data including:
- Password encryption/decryption for email accounts
- Session management for web interface
- User authentication and authorization
- Secure configuration handling
"""

import os
import base64
import secrets
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import bcrypt
from dataclasses import dataclass
from datetime import datetime, timedelta
import json


@dataclass
class SecureConfig:
    """Secure configuration settings"""
    master_key_env_var: str = "MAIL_RULEZ_MASTER_KEY"
    master_key_file: str = ".master_key"
    session_secret_env_var: str = "MAIL_RULEZ_SESSION_SECRET"
    password_salt_rounds: int = 12
    session_timeout_hours: int = 24
    max_login_attempts: int = 5
    lockout_duration_minutes: int = 15


class SecurityManager:
    """Handles all security operations for Mail-Rulez"""
    
    def __init__(self, config: SecureConfig = None):
        self.config = config or SecureConfig()
        self._fernet = None
        self._session_secret = None
        self._failed_attempts: Dict[str, Dict] = {}
    
    def _get_or_create_master_key(self) -> bytes:
        """Get master key from environment, file, or generate new one"""
        # First try environment variable
        key_b64 = os.getenv(self.config.master_key_env_var)
        
        if key_b64:
            try:
                return base64.urlsafe_b64decode(key_b64)
            except Exception:
                print(f"Warning: Invalid master key in {self.config.master_key_env_var}")
        
        # Next try master key file
        try:
            if os.path.exists(self.config.master_key_file):
                with open(self.config.master_key_file, 'r') as f:
                    key_b64 = f.read().strip()
                return base64.urlsafe_b64decode(key_b64)
        except Exception as e:
            print(f"Warning: Could not read master key file: {e}")
        
        # Also try generated-keys.json file (used by environment generation script)
        try:
            import json
            config_dir = os.getenv('MAIL_RULEZ_CONFIG_DIR', '/app/config')
            generated_keys_file = os.path.join(config_dir, 'generated-keys.json')
            if os.path.exists(generated_keys_file):
                with open(generated_keys_file, 'r') as f:
                    keys_data = json.load(f)
                    key_b64 = keys_data.get('MASTER_KEY')
                    if key_b64:
                        # Return the base64-encoded key directly (Fernet expects base64-encoded bytes)
                        return key_b64.encode('utf-8')
        except Exception as e:
            print(f"Warning: Could not read generated keys file: {e}")
        
        # Generate new key and save to file
        key = Fernet.generate_key()
        key_b64 = base64.urlsafe_b64encode(key).decode()
        
        try:
            # Save to file with secure permissions
            with open(self.config.master_key_file, 'w') as f:
                f.write(key_b64)
            
            # Set restrictive permissions (owner read/write only)
            os.chmod(self.config.master_key_file, 0o600)
            
            print(f"Generated new master key and saved to {self.config.master_key_file}")
            print(f"Alternatively, set this environment variable:")
            print(f"export {self.config.master_key_env_var}={key_b64}")
            
        except Exception as e:
            print(f"Warning: Could not save master key to file: {e}")
            print(f"Please set this environment variable:")
            print(f"export {self.config.master_key_env_var}={key_b64}")
        
        return key
    
    def _get_fernet(self) -> Fernet:
        """Get or create Fernet encryption instance"""
        if self._fernet is None:
            key = self._get_or_create_master_key()
            self._fernet = Fernet(key)
        return self._fernet
    
    def encrypt_password(self, password: str) -> str:
        """Encrypt a password for secure storage"""
        fernet = self._get_fernet()
        encrypted_bytes = fernet.encrypt(password.encode())
        return base64.urlsafe_b64encode(encrypted_bytes).decode()
    
    def decrypt_password(self, encrypted_password: str) -> str:
        """Decrypt a password from secure storage"""
        fernet = self._get_fernet()
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_password.encode())
        decrypted_bytes = fernet.decrypt(encrypted_bytes)
        return decrypted_bytes.decode()
    
    def encrypt_data(self, data: str) -> str:
        """Encrypt arbitrary data for secure storage"""
        fernet = self._get_fernet()
        encrypted_bytes = fernet.encrypt(data.encode())
        return base64.urlsafe_b64encode(encrypted_bytes).decode()
    
    def decrypt_data(self, encrypted_data: str) -> str:
        """Decrypt arbitrary data from secure storage"""
        fernet = self._get_fernet()
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
        decrypted_bytes = fernet.decrypt(encrypted_bytes)
        return decrypted_bytes.decode()
    
    def hash_user_password(self, password: str) -> str:
        """Hash a user password for authentication storage"""
        salt = bcrypt.gensalt(rounds=self.config.password_salt_rounds)
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    def verify_user_password(self, password: str, hashed_password: str) -> bool:
        """Verify a user password against stored hash"""
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    
    def generate_session_token(self) -> str:
        """Generate a secure session token"""
        return secrets.token_urlsafe(32)
    
    def get_session_secret(self) -> str:
        """Get or generate session secret for signing"""
        if self._session_secret is None:
            secret = os.getenv(self.config.session_secret_env_var)
            if not secret:
                secret = secrets.token_urlsafe(32)
                print(f"Generated new session secret. Set this environment variable:")
                print(f"export {self.config.session_secret_env_var}={secret}")
            self._session_secret = secret
        return self._session_secret
    
    def is_account_locked(self, username: str) -> bool:
        """Check if account is locked due to failed login attempts"""
        if username not in self._failed_attempts:
            return False
        
        attempts = self._failed_attempts[username]
        if attempts['count'] < self.config.max_login_attempts:
            return False
        
        # Check if lockout period has expired
        lockout_end = attempts['locked_until']
        if datetime.now() > lockout_end:
            # Reset failed attempts
            del self._failed_attempts[username]
            return False
        
        return True
    
    def record_failed_login(self, username: str):
        """Record a failed login attempt"""
        now = datetime.now()
        
        if username not in self._failed_attempts:
            self._failed_attempts[username] = {'count': 0, 'last_attempt': now}
        
        attempts = self._failed_attempts[username]
        attempts['count'] += 1
        attempts['last_attempt'] = now
        
        if attempts['count'] >= self.config.max_login_attempts:
            attempts['locked_until'] = now + timedelta(minutes=self.config.lockout_duration_minutes)
    
    def clear_failed_attempts(self, username: str):
        """Clear failed login attempts for successful login"""
        if username in self._failed_attempts:
            del self._failed_attempts[username]
    
    def create_derived_key(self, password: str, salt: bytes) -> bytes:
        """Create a derived key from password and salt using PBKDF2"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        return kdf.derive(password.encode())
    
    def secure_compare(self, a: str, b: str) -> bool:
        """Timing-safe string comparison"""
        return secrets.compare_digest(a, b)


class SessionManager:
    """Manages user sessions for web interface"""
    
    def __init__(self, security_manager: SecurityManager):
        self.security = security_manager
        self.sessions: Dict[str, Dict[str, Any]] = {}
    
    def create_session(self, username: str, user_data: Dict = None) -> str:
        """Create a new session and return session token"""
        session_token = self.security.generate_session_token()
        
        self.sessions[session_token] = {
            'username': username,
            'created_at': datetime.now(),
            'last_accessed': datetime.now(),
            'user_data': user_data or {}
        }
        
        return session_token
    
    def get_session(self, session_token: str) -> Optional[Dict[str, Any]]:
        """Get session data if valid"""
        if not session_token or session_token not in self.sessions:
            return None
        
        session = self.sessions[session_token]
        
        # Check if session has expired
        max_age = timedelta(hours=self.security.config.session_timeout_hours)
        if datetime.now() - session['created_at'] > max_age:
            self.destroy_session(session_token)
            return None
        
        # Update last accessed time
        session['last_accessed'] = datetime.now()
        return session
    
    def destroy_session(self, session_token: str):
        """Destroy a session"""
        if session_token in self.sessions:
            del self.sessions[session_token]
    
    def cleanup_expired_sessions(self):
        """Remove expired sessions"""
        now = datetime.now()
        max_age = timedelta(hours=self.security.config.session_timeout_hours)
        
        expired_tokens = [
            token for token, session in self.sessions.items()
            if now - session['created_at'] > max_age
        ]
        
        for token in expired_tokens:
            del self.sessions[token]


class SecureAccountConfig:
    """Wrapper for AccountConfig with encrypted password storage"""
    
    def __init__(self, security_manager: SecurityManager):
        self.security = security_manager
    
    def encrypt_account_config(self, account_config) -> Dict[str, str]:
        """Convert AccountConfig to encrypted storage format"""
        return {
            'name': account_config.name,
            'server': account_config.server,
            'email': account_config.email,
            'password_encrypted': self.security.encrypt_password(account_config.password),
            'folders': json.dumps(account_config.folders) if account_config.folders else None
        }
    
    def decrypt_account_config(self, encrypted_data: Dict[str, str]):
        """Convert encrypted storage format back to AccountConfig"""
        from config import AccountConfig
        
        folders = None
        if encrypted_data.get('folders'):
            folders = json.loads(encrypted_data['folders'])
        
        try:
            # Decrypt the password
            password = self.security.decrypt_password(encrypted_data['password_encrypted'])
        except Exception as e:
            # If decryption fails, it's likely due to master key mismatch
            account_name = encrypted_data.get('name', 'unknown')
            raise Exception(f"Failed to decrypt password for account '{account_name}': {e}. This may be due to a master key change.")
        
        return AccountConfig(
            name=encrypted_data['name'],
            server=encrypted_data['server'],
            email=encrypted_data['email'],
            password=password,
            folders=folders
        )


# Global security manager instance
_security_manager = None

def get_security_manager(config: SecureConfig = None) -> SecurityManager:
    """Get the global security manager instance"""
    global _security_manager
    if _security_manager is None:
        _security_manager = SecurityManager(config)
    return _security_manager

def set_security_manager(manager: SecurityManager):
    """Set the global security manager instance (useful for testing)"""
    global _security_manager
    _security_manager = manager