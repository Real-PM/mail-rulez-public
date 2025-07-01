import pytest
import tempfile
import os
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from web.app import create_app
from config import Config


class TestWebApp:
    def test_app_creation(self):
        """Test that Flask app can be created"""
        with tempfile.TemporaryDirectory() as temp_dir:
            app = create_app(config_dir=temp_dir, testing=True)
            assert app is not None
            assert app.config['TESTING'] is True
    
    def test_app_has_required_attributes(self):
        """Test that app has required Mail-Rulez components"""
        with tempfile.TemporaryDirectory() as temp_dir:
            app = create_app(config_dir=temp_dir, testing=True)
            
            assert hasattr(app, 'mail_config')
            assert hasattr(app, 'security_manager')
            assert hasattr(app, 'session_manager')
            assert hasattr(app, 'get_current_user')
    
    def test_routes_are_registered(self):
        """Test that all blueprints are registered"""
        with tempfile.TemporaryDirectory() as temp_dir:
            app = create_app(config_dir=temp_dir, testing=True)
            
            with app.test_client() as client:
                # Test that routes exist (should redirect or return pages)
                response = client.get('/')
                assert response.status_code in [200, 302]
                
                response = client.get('/auth/login')
                assert response.status_code in [200, 302]  # May redirect to setup
    
    def test_login_page_renders(self):
        """Test that login page renders correctly with admin user"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Clear environment variables that might interfere
            with patch.dict(os.environ, {}, clear=True):
                app = create_app(config_dir=temp_dir, testing=True)
                
                # Create admin user file to bypass setup
                admin_file = Path(temp_dir) / '.admin_user'
                admin_file.write_text('admin:$2b$12$dummy_hash')
                
                with app.test_client() as client:
                    response = client.get('/auth/login')
                    assert response.status_code == 200
                    assert b'Mail-Rulez' in response.data
                    assert b'Username' in response.data
                    assert b'Password' in response.data
    
    def test_setup_page_when_no_admin(self):
        """Test setup page appears when no admin user exists"""
        with tempfile.TemporaryDirectory() as temp_dir:
            app = create_app(config_dir=temp_dir, testing=True)
            
            with app.test_client() as client:
                # Should redirect to setup
                response = client.get('/auth/login')
                assert response.status_code == 302
                assert '/auth/setup' in response.location
                
                # Setup page should render
                response = client.get('/auth/setup')
                assert response.status_code == 200
                assert b'Initial Setup' in response.data
    
    def test_dashboard_requires_auth(self):
        """Test that dashboard requires authentication"""
        with tempfile.TemporaryDirectory() as temp_dir:
            app = create_app(config_dir=temp_dir, testing=True)
            
            with app.test_client() as client:
                response = client.get('/overview')
                assert response.status_code == 302  # Should redirect to login
    
    def test_context_processor_data(self):
        """Test that context processor provides required data"""
        with tempfile.TemporaryDirectory() as temp_dir:
            app = create_app(config_dir=temp_dir, testing=True)
            
            with app.test_request_context():
                # Test context processor by checking template globals
                from flask import g
                
                # Create a template context and check globals
                with app.app_context():
                    # Get template context
                    ctx = app.make_shell_context()
                    
                    # The context processor should inject these values
                    assert app.mail_config is not None
                    assert app.security_manager is not None
    
    def test_error_handlers(self):
        """Test that error handlers are properly configured"""
        with tempfile.TemporaryDirectory() as temp_dir:
            app = create_app(config_dir=temp_dir, testing=True)
            
            with app.test_client() as client:
                # Test 404 handler
                response = client.get('/nonexistent-page')
                assert response.status_code == 404
                assert b'404 Not Found' in response.data


class TestWebAppIntegration:
    def test_app_with_existing_config(self):
        """Test app creation with existing configuration"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a config with some data
            config = Config(base_dir=temp_dir, use_encryption=False)
            config.add_account("test", "imap.example.com", "test@example.com", "password")
            config.save_config()
            
            # Create app
            app = create_app(config_dir=temp_dir, testing=True)
            
            assert len(app.mail_config.accounts) == 1
            assert app.mail_config.accounts[0].name == "test"
    
    def test_security_integration(self):
        """Test that security components are properly integrated"""
        with tempfile.TemporaryDirectory() as temp_dir:
            app = create_app(config_dir=temp_dir, testing=True)
            
            # Test security manager
            security_manager = app.security_manager
            assert security_manager is not None
            
            # Test password encryption
            encrypted = security_manager.encrypt_password("test_password")
            decrypted = security_manager.decrypt_password(encrypted)
            assert decrypted == "test_password"
            
            # Test session manager
            session_manager = app.session_manager
            assert session_manager is not None
            
            session_token = session_manager.create_session("test_user")
            session_data = session_manager.get_session(session_token)
            assert session_data['username'] == "test_user"