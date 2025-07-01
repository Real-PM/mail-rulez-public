import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config import Config, AccountConfig, get_config, set_config


class TestAccountConfig:
    def test_account_config_creation(self):
        account = AccountConfig("test", "imap.example.com", "test@example.com", "password123")
        
        assert account.name == "test"
        assert account.server == "imap.example.com"
        assert account.email == "test@example.com"
        assert account.password == "password123"
        assert account.folders is not None
        assert account.folders['inbox'] == 'INBOX'
        assert account.folders['junk'] == 'INBOX.Junk'
    
    def test_account_config_custom_folders(self):
        custom_folders = {'inbox': 'INBOX', 'junk': 'Spam'}
        account = AccountConfig("test", "imap.example.com", "test@example.com", "password123", custom_folders)
        
        assert account.folders['junk'] == 'Spam'


class TestConfig:
    def test_config_creation_with_temp_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # Clear environment variables that might interfere with test
            with patch.dict(os.environ, {}, clear=True):
                config = Config(base_dir=temp_dir)
                
                assert config.base_dir == Path(temp_dir)
                assert config.lists_dir == Path(temp_dir) / "lists"
                assert config.lists_dir.exists()
    
    def test_list_file_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # Clear environment variables that might interfere with test
            with patch.dict(os.environ, {}, clear=True):
                config = Config(base_dir=temp_dir)
                
                assert config.get_list_file_path('white') == str(Path(temp_dir) / "lists" / "white.txt")
                assert config.get_list_file_path('black') == str(Path(temp_dir) / "lists" / "black.txt")
                assert config.get_list_file_path('vendor') == str(Path(temp_dir) / "lists" / "vendor.txt")
    
    def test_invalid_list_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Config(base_dir=temp_dir)
            
            with pytest.raises(ValueError):
                config.get_list_file_path('invalid')
    
    def test_add_account(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Config(base_dir=temp_dir)
            
            account = config.add_account("test", "imap.example.com", "test@example.com", "password123")
            
            assert len(config.accounts) == 1
            assert config.accounts[0] == account
            assert account.name == "test"
    
    def test_get_account(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Config(base_dir=temp_dir)
            config.add_account("test", "imap.example.com", "test@example.com", "password123")
            
            found_account = config.get_account("test")
            assert found_account is not None
            assert found_account.name == "test"
            
            not_found = config.get_account("nonexistent")
            assert not_found is None
    
    @patch.dict(os.environ, {
        'MAIL_RULEZ_SERVER': 'imap.test.com',
        'MAIL_RULEZ_EMAIL': 'env@test.com',
        'MAIL_RULEZ_PASSWORD': 'envpass',
        'MAIL_RULEZ_TIMEZONE': 'US/Eastern'
    })
    def test_load_from_env(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Config(base_dir=temp_dir)
            
            assert config.timezone == "US/Eastern"
            
            env_account = config.get_account("env_account")
            assert env_account is not None
            assert env_account.server == "imap.test.com"
            assert env_account.email == "env@test.com"
            assert env_account.password == "envpass"
    
    @patch.dict(os.environ, {
        'MAIL_RULEZ_BASE_DIR': '/custom/base',
        'MAIL_RULEZ_LISTS_DIR': '/custom/lists'
    })
    def test_env_path_overrides(self):
        # Don't actually create directories for this test
        with patch('pathlib.Path.mkdir'):
            with patch('pathlib.Path.touch'):
                config = Config()
                
                assert str(config.base_dir) == '/custom/base'
                assert str(config.lists_dir) == '/custom/lists'
                assert config.get_list_file_path('white') == '/custom/lists/white.txt'
    
    def test_config_ini_loading(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.ini"
            
            # Create a test config.ini
            config_content = """[account_primary]
server = imap.primary.com
email = primary@test.com
password = primarypass

[account_secondary]
server = imap.secondary.com
email = secondary@test.com
password = secondarypass
"""
            config_file.write_text(config_content)
            
            config = Config(base_dir=temp_dir, config_file=str(config_file))
            
            assert len(config.accounts) == 2
            
            primary = config.get_account("account_primary")
            assert primary.server == "imap.primary.com"
            assert primary.email == "primary@test.com"
            
            secondary = config.get_account("account_secondary")
            assert secondary.server == "imap.secondary.com"
            assert secondary.email == "secondary@test.com"
    
    def test_save_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Config(base_dir=temp_dir, use_encryption=False)  # Disable encryption for this test
            config.add_account("test", "imap.example.com", "test@example.com", "password123")
            
            config.save_config()
            
            # Verify the file was created and can be read
            assert config.config_file.exists()
            
            # Create a new config instance and verify it loads the saved data
            new_config = Config(base_dir=temp_dir, use_encryption=False)
            assert len(new_config.accounts) == 1
            assert new_config.get_account("test").email == "test@example.com"


class TestGlobalConfig:
    def test_get_config_singleton(self):
        config1 = get_config()
        config2 = get_config()
        
        assert config1 is config2
    
    def test_set_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            custom_config = Config(base_dir=temp_dir)
            set_config(custom_config)
            
            retrieved_config = get_config()
            assert retrieved_config is custom_config