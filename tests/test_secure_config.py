import pytest
import tempfile
import os
import json
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config import Config, AccountConfig
from security import SecurityManager, set_security_manager


class TestSecureConfig:
    def test_secure_config_save_and_load(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create config with encryption enabled
            config = Config(base_dir=temp_dir, use_encryption=True)
            
            # Add test account
            account = config.add_account(
                "test_account",
                "imap.example.com", 
                "test@example.com",
                "secret_password"
            )
            
            # Save with secure storage
            config.save_config(use_secure_storage=True)
            
            # Verify secure config file was created
            assert config.secure_config_file.exists()
            
            # Verify password is encrypted in file
            with open(config.secure_config_file, 'r') as f:
                secure_data = json.load(f)
            
            assert len(secure_data['accounts']) == 1
            account_data = secure_data['accounts'][0]
            assert 'password_encrypted' in account_data
            assert account_data['password_encrypted'] != "secret_password"
            
            # Create new config instance and verify it loads encrypted data
            new_config = Config(base_dir=temp_dir, use_encryption=True)
            
            assert len(new_config.accounts) == 1
            loaded_account = new_config.accounts[0]
            assert loaded_account.name == "test_account"
            assert loaded_account.server == "imap.example.com"
            assert loaded_account.email == "test@example.com"
            assert loaded_account.password == "secret_password"  # Should be decrypted
    
    def test_fallback_to_legacy_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create config with encryption disabled
            config = Config(base_dir=temp_dir, use_encryption=False)
            
            # Add test account
            config.add_account(
                "test_account",
                "imap.example.com",
                "test@example.com", 
                "secret_password"
            )
            
            # Save should use legacy format
            config.save_config()
            
            # Verify config.ini was created, not secure config
            assert config.config_file.exists()
            assert not config.secure_config_file.exists()
            
            # Verify password is stored in plaintext (legacy format)
            import configparser
            legacy_config = configparser.ConfigParser()
            legacy_config.read(config.config_file)
            
            assert legacy_config['test_account']['password'] == "secret_password"
    
    def test_migration_from_legacy_to_secure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create legacy config first
            config_ini_path = Path(temp_dir) / "config.ini"
            config_content = """[test_account]
server = imap.example.com
email = test@example.com
password = legacy_password
"""
            config_ini_path.write_text(config_content)
            
            # Create config with encryption enabled
            config = Config(base_dir=temp_dir, use_encryption=True)
            
            # Should load from legacy config
            assert len(config.accounts) == 1
            account = config.accounts[0]
            assert account.password == "legacy_password"
            
            # Save with secure storage to migrate
            config.save_config(use_secure_storage=True)
            
            # Verify secure config was created
            assert config.secure_config_file.exists()
            
            # Create new instance - should load from secure config
            new_config = Config(base_dir=temp_dir, use_encryption=True)
            assert len(new_config.accounts) == 1
            assert new_config.accounts[0].password == "legacy_password"
    
    def test_config_without_security_manager(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock security manager to return None
            with patch('security.get_security_manager', return_value=None):
                config = Config(base_dir=temp_dir, use_encryption=True)
                
                # Add account
                config.add_account("test", "imap.example.com", "test@example.com", "password")
                
                # Should fallback to legacy save
                config.save_config(use_secure_storage=True)
                
                # Should create config.ini, not secure config
                assert config.config_file.exists()
                assert not config.secure_config_file.exists()
    
    def test_corrupted_secure_config_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create corrupted secure config file
            secure_config_path = Path(temp_dir) / "secure_config.json"
            secure_config_path.write_text("invalid json content")
            
            # Should handle gracefully and not load accounts
            config = Config(base_dir=temp_dir, use_encryption=True)
            assert len(config.accounts) == 0
    
    @patch.dict(os.environ, {'MAIL_RULEZ_MASTER_KEY': 'MFZ0Wi1DdmNLdG5ncTVlOGpLSmlEV205TmRLRFB0VFdnTDcxN3h4bXdhdz0='})
    def test_consistent_encryption_with_env_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create first config instance
            config1 = Config(base_dir=temp_dir, use_encryption=True)
            config1.add_account("test", "imap.example.com", "test@example.com", "password123")
            config1.save_config(use_secure_storage=True)
            
            # Create second config instance - should decrypt with same key
            config2 = Config(base_dir=temp_dir, use_encryption=True)
            
            assert len(config2.accounts) == 1
            assert config2.accounts[0].password == "password123"
    
    def test_account_folders_encryption(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Config(base_dir=temp_dir, use_encryption=True)
            
            # Add account with custom folders
            custom_folders = {
                'inbox': 'INBOX',
                'junk': 'Spam',
                'sent': 'Sent Items'
            }
            
            account = AccountConfig(
                "test_account",
                "imap.example.com",
                "test@example.com", 
                "password123",
                custom_folders
            )
            config.accounts.append(account)
            
            # Save and reload
            config.save_config(use_secure_storage=True)
            
            new_config = Config(base_dir=temp_dir, use_encryption=True)
            loaded_account = new_config.accounts[0]
            
            assert loaded_account.folders == custom_folders