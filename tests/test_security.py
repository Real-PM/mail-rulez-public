import pytest
import os
import tempfile
from unittest.mock import patch
from datetime import datetime, timedelta
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from security import (
    SecurityManager, SessionManager, SecureAccountConfig, 
    SecureConfig, get_security_manager, set_security_manager
)
from config import AccountConfig


class TestSecurityManager:
    def test_password_encryption_decryption(self):
        security = SecurityManager()
        
        password = "test_password_123"
        encrypted = security.encrypt_password(password)
        
        # Encrypted should be different from original
        assert encrypted != password
        
        # Should be able to decrypt back to original
        decrypted = security.decrypt_password(encrypted)
        assert decrypted == password
    
    def test_different_passwords_encrypt_differently(self):
        security = SecurityManager()
        
        password1 = "password1"
        password2 = "password2"
        
        encrypted1 = security.encrypt_password(password1)
        encrypted2 = security.encrypt_password(password2)
        
        assert encrypted1 != encrypted2
    
    def test_user_password_hashing(self):
        security = SecurityManager()
        
        password = "user_password_123"
        hashed = security.hash_user_password(password)
        
        # Hash should be different from original
        assert hashed != password
        
        # Should verify correctly
        assert security.verify_user_password(password, hashed)
        
        # Wrong password should not verify
        assert not security.verify_user_password("wrong_password", hashed)
    
    def test_session_token_generation(self):
        security = SecurityManager()
        
        token1 = security.generate_session_token()
        token2 = security.generate_session_token()
        
        # Tokens should be different
        assert token1 != token2
        
        # Tokens should be reasonable length
        assert len(token1) > 20
        assert len(token2) > 20
    
    def test_account_lockout(self):
        config = SecureConfig(max_login_attempts=3, lockout_duration_minutes=5)
        security = SecurityManager(config)
        
        username = "test_user"
        
        # Initially not locked
        assert not security.is_account_locked(username)
        
        # Record failed attempts
        for i in range(2):
            security.record_failed_login(username)
            assert not security.is_account_locked(username)
        
        # Third attempt should lock the account
        security.record_failed_login(username)
        assert security.is_account_locked(username)
        
        # Clear attempts should unlock
        security.clear_failed_attempts(username)
        assert not security.is_account_locked(username)
    
    def test_secure_compare(self):
        security = SecurityManager()
        
        # Same strings should compare equal
        assert security.secure_compare("test", "test")
        
        # Different strings should not compare equal
        assert not security.secure_compare("test", "different")
        
        # Should handle empty strings
        assert security.secure_compare("", "")
        assert not security.secure_compare("", "test")
    
    @patch.dict(os.environ, {'MAIL_RULEZ_MASTER_KEY': 'MFZ0Wi1DdmNLdG5ncTVlOGpLSmlEV205TmRLRFB0VFdnTDcxN3h4bXdhdz0='})
    def test_master_key_from_environment(self):
        security = SecurityManager()
        
        # Should use key from environment
        password = "test_password"
        encrypted = security.encrypt_password(password)
        decrypted = security.decrypt_password(encrypted)
        
        assert decrypted == password


class TestSessionManager:
    def test_session_creation_and_retrieval(self):
        security = SecurityManager()
        session_manager = SessionManager(security)
        
        username = "test_user"
        user_data = {"role": "admin", "email": "test@example.com"}
        
        # Create session
        token = session_manager.create_session(username, user_data)
        assert token is not None
        assert len(token) > 20
        
        # Retrieve session
        session = session_manager.get_session(token)
        assert session is not None
        assert session['username'] == username
        assert session['user_data'] == user_data
        assert 'created_at' in session
        assert 'last_accessed' in session
    
    def test_invalid_session_token(self):
        security = SecurityManager()
        session_manager = SessionManager(security)
        
        # Non-existent token should return None
        assert session_manager.get_session("invalid_token") is None
        assert session_manager.get_session("") is None
        assert session_manager.get_session(None) is None
    
    def test_session_destruction(self):
        security = SecurityManager()
        session_manager = SessionManager(security)
        
        username = "test_user"
        token = session_manager.create_session(username)
        
        # Session should exist
        assert session_manager.get_session(token) is not None
        
        # Destroy session
        session_manager.destroy_session(token)
        
        # Session should no longer exist
        assert session_manager.get_session(token) is None
    
    def test_session_expiration(self):
        config = SecureConfig(session_timeout_hours=1)
        security = SecurityManager(config)
        session_manager = SessionManager(security)
        
        username = "test_user"
        token = session_manager.create_session(username)
        
        # Manually set creation time to past
        session_manager.sessions[token]['created_at'] = datetime.now() - timedelta(hours=2)
        
        # Session should be expired and return None
        assert session_manager.get_session(token) is None
        
        # Token should be removed from sessions
        assert token not in session_manager.sessions
    
    def test_cleanup_expired_sessions(self):
        config = SecureConfig(session_timeout_hours=1)
        security = SecurityManager(config)
        session_manager = SessionManager(security)
        
        # Create multiple sessions
        token1 = session_manager.create_session("user1")
        token2 = session_manager.create_session("user2")
        token3 = session_manager.create_session("user3")
        
        # Make some sessions expired
        session_manager.sessions[token1]['created_at'] = datetime.now() - timedelta(hours=2)
        session_manager.sessions[token2]['created_at'] = datetime.now() - timedelta(hours=2)
        
        # Cleanup expired sessions
        session_manager.cleanup_expired_sessions()
        
        # Only non-expired session should remain
        assert token1 not in session_manager.sessions
        assert token2 not in session_manager.sessions
        assert token3 in session_manager.sessions


class TestSecureAccountConfig:
    def test_account_config_encryption_decryption(self):
        security = SecurityManager()
        secure_config = SecureAccountConfig(security)
        
        # Create test account config
        account = AccountConfig(
            name="test_account",
            server="imap.example.com",
            email="test@example.com",
            password="secret_password",
            folders={"inbox": "INBOX", "junk": "Spam"}
        )
        
        # Encrypt
        encrypted_data = secure_config.encrypt_account_config(account)
        
        # Check structure
        assert 'name' in encrypted_data
        assert 'server' in encrypted_data
        assert 'email' in encrypted_data
        assert 'password_encrypted' in encrypted_data
        assert 'folders' in encrypted_data
        
        # Password should be encrypted
        assert encrypted_data['password_encrypted'] != account.password
        
        # Decrypt back
        decrypted_account = secure_config.decrypt_account_config(encrypted_data)
        
        # Should match original
        assert decrypted_account.name == account.name
        assert decrypted_account.server == account.server
        assert decrypted_account.email == account.email
        assert decrypted_account.password == account.password
        assert decrypted_account.folders == account.folders
    
    def test_account_config_without_folders(self):
        security = SecurityManager()
        secure_config = SecureAccountConfig(security)
        
        # Create account without custom folders
        account = AccountConfig(
            name="test_account",
            server="imap.example.com",
            email="test@example.com",
            password="secret_password"
        )
        
        # Encrypt and decrypt
        encrypted_data = secure_config.encrypt_account_config(account)
        decrypted_account = secure_config.decrypt_account_config(encrypted_data)
        
        # Should handle None folders correctly
        assert decrypted_account.folders == account.folders


class TestGlobalSecurityManager:
    def test_get_security_manager_singleton(self):
        manager1 = get_security_manager()
        manager2 = get_security_manager()
        
        assert manager1 is manager2
    
    def test_set_security_manager(self):
        custom_config = SecureConfig(max_login_attempts=10)
        custom_manager = SecurityManager(custom_config)
        
        set_security_manager(custom_manager)
        retrieved_manager = get_security_manager()
        
        assert retrieved_manager is custom_manager
        assert retrieved_manager.config.max_login_attempts == 10


class TestSecureConfig:
    def test_default_values(self):
        config = SecureConfig()
        
        assert config.master_key_env_var == "MAIL_RULEZ_MASTER_KEY"
        assert config.session_secret_env_var == "MAIL_RULEZ_SESSION_SECRET"
        assert config.password_salt_rounds == 12
        assert config.session_timeout_hours == 24
        assert config.max_login_attempts == 5
        assert config.lockout_duration_minutes == 15
    
    def test_custom_values(self):
        config = SecureConfig(
            master_key_env_var="CUSTOM_KEY",
            session_timeout_hours=8,
            max_login_attempts=3
        )
        
        assert config.master_key_env_var == "CUSTOM_KEY"
        assert config.session_timeout_hours == 8
        assert config.max_login_attempts == 3