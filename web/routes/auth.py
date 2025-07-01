"""
Authentication routes for Mail-Rulez web interface

Handles login, logout, and user session management using the integrated
security system.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length
import os


auth_bp = Blueprint('auth', __name__)


class LoginForm(FlaskForm):
    """Login form with username and password"""
    username = StringField('Username', validators=[
        DataRequired(),
        Length(min=3, max=50, message='Username must be between 3 and 50 characters')
    ])
    password = PasswordField('Password', validators=[
        DataRequired(),
        Length(min=6, message='Password must be at least 6 characters')
    ])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')


class SetupForm(FlaskForm):
    """Initial setup form for creating admin user"""
    username = StringField('Admin Username', validators=[
        DataRequired(),
        Length(min=3, max=50, message='Username must be between 3 and 50 characters')
    ])
    password = PasswordField('Admin Password', validators=[
        DataRequired(),
        Length(min=8, message='Password must be at least 8 characters')
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired()
    ])
    submit = SubmitField('Create Admin Account')


class PasswordResetRequestForm(FlaskForm):
    """Form to request password reset"""
    username = StringField('Username', validators=[
        DataRequired(),
        Length(min=3, max=50, message='Username must be between 3 and 50 characters')
    ])
    submit = SubmitField('Generate Reset Token')


class PasswordResetForm(FlaskForm):
    """Form to reset password with token"""
    token = StringField('Reset Token', validators=[
        DataRequired(),
        Length(min=32, max=64, message='Invalid token format')
    ])
    password = PasswordField('New Password', validators=[
        DataRequired(),
        Length(min=8, message='Password must be at least 8 characters')
    ])
    confirm_password = PasswordField('Confirm New Password', validators=[
        DataRequired()
    ])
    submit = SubmitField('Reset Password')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login"""
    # Check if initial setup is needed
    if needs_initial_setup():
        return redirect(url_for('auth.setup'))
    
    form = LoginForm()
    
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        
        # Check if account is locked
        if current_app.security_manager.is_account_locked(username):
            flash('Account is temporarily locked due to too many failed login attempts. Please try again later.', 'error')
            return render_template('auth/login.html', form=form)
        
        # Verify credentials
        if verify_user_credentials(username, password):
            # Clear failed login attempts
            current_app.security_manager.clear_failed_attempts(username)
            
            # Store username directly in Flask session (no custom SessionManager needed)
            session['username'] = username
            session.permanent = True  # Always use permanent sessions for proper timeout
            
            flash(f'Welcome back, {username}!', 'success')
            
            # Redirect to originally requested page or dashboard
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('dashboard.overview'))
        else:
            # Record failed login attempt
            current_app.security_manager.record_failed_login(username)
            flash('Invalid username or password', 'error')
    
    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout')
def logout():
    """Handle user logout"""
    session.clear()
    flash('You have been logged out successfully', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/setup', methods=['GET', 'POST'])
def setup():
    """Handle initial admin user setup"""
    if not needs_initial_setup():
        flash('Setup has already been completed', 'info')
        return redirect(url_for('auth.login'))
    
    form = SetupForm()
    
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        confirm_password = form.confirm_password.data
        
        # Validate password confirmation
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('auth/setup.html', form=form)
        
        # Create admin user
        if create_admin_user(username, password):
            flash('Admin account created successfully! Please log in.', 'success')
            return redirect(url_for('auth.login'))
        else:
            flash('Failed to create admin account. Please try again.', 'error')
    
    return render_template('auth/setup.html', form=form)


def needs_initial_setup():
    """Check if initial setup is needed"""
    # Check if admin user exists in config directory (persistent storage)
    admin_file = current_app.mail_config.config_dir / '.admin_user'
    
    # Migration: check old location and move to new location if needed
    old_admin_file = current_app.mail_config.base_dir / '.admin_user'
    
    if not admin_file.exists() and old_admin_file.exists():
        try:
            # Migrate admin file from old location to new persistent location
            admin_file.parent.mkdir(parents=True, exist_ok=True)
            admin_file.write_text(old_admin_file.read_text())
            admin_file.chmod(0o600)
            
            # Remove old file
            old_admin_file.unlink()
            
            current_app.logger.info("Migrated admin file from base_dir to config_dir")
            return False  # Setup not needed, migration completed
        except Exception as e:
            current_app.logger.error(f"Failed to migrate admin file: {e}")
    
    return not admin_file.exists()


def create_admin_user(username, password):
    """Create the initial admin user"""
    try:
        # Hash the password
        hashed_password = current_app.security_manager.hash_user_password(password)
        
        # Store admin credentials in config directory (persistent storage)
        admin_file = current_app.mail_config.config_dir / '.admin_user'
        admin_data = f"{username}:{hashed_password}"
        
        # Ensure config directory exists
        admin_file.parent.mkdir(parents=True, exist_ok=True)
        admin_file.write_text(admin_data)
        
        # Set restrictive permissions
        admin_file.chmod(0o600)
        
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to create admin user: {e}")
        return False


def verify_user_credentials(username, password):
    """Verify user login credentials"""
    try:
        admin_file = current_app.mail_config.config_dir / '.admin_user'
        
        if not admin_file.exists():
            return False
        
        admin_data = admin_file.read_text().strip()
        stored_username, stored_hash = admin_data.split(':', 1)
        
        # Check username and password
        if (current_app.security_manager.secure_compare(username, stored_username) and
            current_app.security_manager.verify_user_password(password, stored_hash)):
            return True
        
        return False
    except Exception as e:
        current_app.logger.error(f"Failed to verify credentials: {e}")
        return False


@auth_bp.route('/session/status')
def session_status():
    """API endpoint to check session status"""
    username = session.get('username')
    if username:
        return {
            'authenticated': True,
            'username': username,
            'expires_in': 'TODO'  # Calculate remaining time
        }
    
    return {'authenticated': False}


@auth_bp.route('/password-reset/request', methods=['GET', 'POST'])
def password_reset_request():
    """Handle password reset request"""
    # Don't allow password reset if setup is needed
    if needs_initial_setup():
        flash('Please complete initial setup first', 'info')
        return redirect(url_for('auth.setup'))
    
    form = PasswordResetRequestForm()
    
    if form.validate_on_submit():
        username = form.username.data
        
        # Verify username exists
        if verify_username_exists(username):
            # Generate reset token
            token = generate_password_reset_token(username)
            if token:
                current_app.logger.info(f"Password reset token generated for user: {username}")
                # Redirect to token display page instead of flashing
                return redirect(url_for('auth.password_reset_token_display', token=token, username=username))
            else:
                flash('Failed to generate reset token. Please try again.', 'error')
        else:
            # Don't reveal if username exists or not for security
            flash('If the username exists, a reset token has been generated.', 'info')
    
    return render_template('auth/password_reset_request.html', form=form)


@auth_bp.route('/password-reset/token/<token>')
def password_reset_token_display(token):
    """Display the generated reset token with copy functionality"""
    # Don't allow if setup is needed
    if needs_initial_setup():
        flash('Please complete initial setup first', 'info')
        return redirect(url_for('auth.setup'))
    
    # Get username from query params (for display purposes)
    username = request.args.get('username', 'admin')
    
    # Verify token exists and is valid (but don't consume it)
    if not verify_token_exists(token):
        flash('Invalid or expired reset token.', 'error')
        return redirect(url_for('auth.password_reset_request'))
    
    return render_template('auth/password_reset_token_display.html', 
                         token=token, 
                         username=username)


@auth_bp.route('/password-reset', methods=['GET', 'POST'])
def password_reset():
    """Handle password reset with token"""
    # Don't allow password reset if setup is needed
    if needs_initial_setup():
        flash('Please complete initial setup first', 'info')
        return redirect(url_for('auth.setup'))
    
    form = PasswordResetForm()
    
    # Pre-populate token from URL parameter
    if request.method == 'GET' and request.args.get('token'):
        form.token.data = request.args.get('token')
    
    if form.validate_on_submit():
        token = form.token.data
        password = form.password.data
        confirm_password = form.confirm_password.data
        
        # Validate password confirmation
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('auth/password_reset.html', form=form)
        
        # Verify and use reset token
        username = verify_password_reset_token(token)
        if username:
            # Reset password
            if reset_admin_password(username, password):
                flash('Password reset successfully! Please log in with your new password.', 'success')
                current_app.logger.info(f"Password reset completed for user: {username}")
                return redirect(url_for('auth.login'))
            else:
                flash('Failed to reset password. Please try again.', 'error')
        else:
            flash('Invalid or expired reset token.', 'error')
    
    return render_template('auth/password_reset.html', form=form)


def verify_username_exists(username):
    """Check if the username exists in the admin file"""
    try:
        admin_file = current_app.mail_config.config_dir / '.admin_user'
        
        if not admin_file.exists():
            return False
        
        admin_data = admin_file.read_text().strip()
        stored_username, _ = admin_data.split(':', 1)
        
        return current_app.security_manager.secure_compare(username, stored_username)
    except Exception as e:
        current_app.logger.error(f"Failed to verify username: {e}")
        return False


def generate_password_reset_token(username):
    """Generate a secure password reset token"""
    try:
        import secrets
        import time
        import json
        
        # Generate random token
        token = secrets.token_urlsafe(32)
        
        # Create token data with expiration (1 hour)
        token_data = {
            'username': username,
            'token': token,
            'expires': time.time() + 3600,  # 1 hour from now
            'used': False
        }
        
        # Store token securely in config directory
        token_file = current_app.mail_config.config_dir / f'.reset_token_{token[:8]}'
        
        # Encrypt token data
        encrypted_data = current_app.security_manager.encrypt_data(json.dumps(token_data))
        token_file.write_text(encrypted_data)
        token_file.chmod(0o600)
        
        return token
    except Exception as e:
        current_app.logger.error(f"Failed to generate reset token: {e}")
        return None


def verify_token_exists(token):
    """Check if a token exists and is valid (without consuming it)"""
    try:
        import time
        import json
        
        # Find token file in config directory
        token_file = current_app.mail_config.config_dir / f'.reset_token_{token[:8]}'
        
        if not token_file.exists():
            return False
        
        # Decrypt and verify token data
        encrypted_data = token_file.read_text()
        token_data = json.loads(current_app.security_manager.decrypt_data(encrypted_data))
        
        # Check if token matches
        if not current_app.security_manager.secure_compare(token, token_data['token']):
            return False
        
        # Check if token is expired
        if time.time() > token_data['expires']:
            return False
        
        # Check if token was already used
        if token_data['used']:
            return False
        
        return True
        
    except Exception as e:
        current_app.logger.error(f"Failed to check token existence: {e}")
        return False


def verify_password_reset_token(token):
    """Verify and consume a password reset token"""
    try:
        import time
        import json
        
        # Find token file in config directory
        token_file = current_app.mail_config.config_dir / f'.reset_token_{token[:8]}'
        
        if not token_file.exists():
            return None
        
        # Decrypt and verify token data
        encrypted_data = token_file.read_text()
        token_data = json.loads(current_app.security_manager.decrypt_data(encrypted_data))
        
        # Check if token matches
        if not current_app.security_manager.secure_compare(token, token_data['token']):
            return None
        
        # Check if token is expired
        if time.time() > token_data['expires']:
            # Clean up expired token
            token_file.unlink()
            return None
        
        # Check if token was already used
        if token_data['used']:
            return None
        
        # Mark token as used
        token_data['used'] = True
        encrypted_data = current_app.security_manager.encrypt_data(json.dumps(token_data))
        token_file.write_text(encrypted_data)
        
        # Return username for successful verification
        return token_data['username']
        
    except Exception as e:
        current_app.logger.error(f"Failed to verify reset token: {e}")
        return None


def reset_admin_password(username, new_password):
    """Reset the admin user's password"""
    try:
        # Hash the new password
        hashed_password = current_app.security_manager.hash_user_password(new_password)
        
        # Update admin credentials in config directory
        admin_file = current_app.mail_config.config_dir / '.admin_user'
        admin_data = f"{username}:{hashed_password}"
        
        admin_file.write_text(admin_data)
        admin_file.chmod(0o600)
        
        # Clean up any remaining reset tokens for this user
        cleanup_reset_tokens()
        
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to reset password: {e}")
        return False


def cleanup_reset_tokens():
    """Clean up expired or used reset tokens"""
    try:
        import time
        import json
        
        token_files = list(current_app.mail_config.config_dir.glob('.reset_token_*'))
        
        for token_file in token_files:
            try:
                encrypted_data = token_file.read_text()
                token_data = json.loads(current_app.security_manager.decrypt_data(encrypted_data))
                
                # Remove if expired or used
                if time.time() > token_data['expires'] or token_data['used']:
                    token_file.unlink()
                    
            except Exception:
                # Remove corrupted token files
                token_file.unlink()
                
    except Exception as e:
        current_app.logger.error(f"Failed to cleanup reset tokens: {e}")