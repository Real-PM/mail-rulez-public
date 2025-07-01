"""
Account management routes for Mail-Rulez web interface

Handles IMAP account configuration and management.
"""

import sys
from pathlib import Path
from flask import Blueprint, render_template, redirect, url_for, flash, current_app, request, jsonify
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, IntegerField, SelectField, FieldList, FormField, SubmitField
from wtforms.validators import DataRequired, Email, NumberRange, Length
from functools import wraps
import imaplib
import ssl
import socket

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import AccountConfig
from services.email_processor import EmailProcessor


accounts_bp = Blueprint('accounts', __name__)


def login_required(f):
    """Decorator to require authentication for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_app.get_current_user():
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


class FolderConfigForm(FlaskForm):
    """Form for configuring individual folder mappings"""
    folder_type = SelectField('Folder Type', choices=[
        ('inbox', 'Inbox'),
        ('processed', 'Processed'),
        ('pending', 'Pending'),
        ('junk', 'Junk'),
        ('approved_ads', 'Approved Ads'),
        ('headhunt', 'Head Hunt'),
        ('whitelist', 'Whitelist Training'),
        ('blacklist', 'Blacklist Training'),
        ('vendor', 'Vendor Training'),
        ('headhunter', 'Headhunter Training')
    ])
    folder_name = StringField('IMAP Folder Name', validators=[DataRequired()])


class AccountForm(FlaskForm):
    """Form for adding/editing email accounts"""
    name = StringField('Account Name', validators=[
        DataRequired(),
        Length(min=2, max=50, message='Account name must be between 2 and 50 characters')
    ])
    email = StringField('Email Address', validators=[
        DataRequired(),
        Email(message='Please enter a valid email address')
    ])
    server = StringField('IMAP Server', validators=[
        DataRequired(),
        Length(min=3, max=100, message='Server must be between 3 and 100 characters')
    ])
    port = IntegerField('Port', validators=[
        NumberRange(min=1, max=65535, message='Port must be between 1 and 65535')
    ], default=993)
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    use_ssl = SelectField('Security', choices=[
        ('ssl', 'SSL/TLS (Recommended)'),
        ('starttls', 'STARTTLS'),
        ('none', 'None (Not Recommended)')
    ], default='ssl')
    
    # Folder configuration - no defaults, will be populated after connection test
    folder_inbox = StringField('Inbox Folder')
    folder_processed = StringField('Processed Folder')
    folder_pending = StringField('Pending Folder')
    folder_junk = StringField('Junk Folder')
    folder_approved_ads = StringField('Vendor Marketing Folder')
    folder_headhunt = StringField('Head Hunt Folder')
    
    # New rule-based folders
    folder_packages = StringField('Packages Folder')
    folder_receipts = StringField('Receipts Folder')
    folder_linkedin = StringField('LinkedIn Folder')
    
    # Training folders
    folder_whitelist = StringField('Whitelist Training Folder')
    folder_blacklist = StringField('Blacklist Training Folder')
    folder_vendor = StringField('Vendor Training Folder')
    folder_headhunter = StringField('Headhunter Training Folder')
    
    submit = SubmitField('Save Account')


@accounts_bp.route('/')
@login_required
def list_accounts():
    """List all configured email accounts"""
    # Force reload config to get latest saved accounts
    from config import Config
    fresh_config = Config(current_app.mail_config.base_dir, current_app.mail_config.config_file, current_app.mail_config.use_encryption)
    accounts = fresh_config.accounts
    current_app.logger.info(f"Accounts list page loaded {len(accounts)} accounts from config")
    return render_template('accounts/list.html', accounts=accounts)


@accounts_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_account():
    """Add new email account"""
    form = AccountForm()
    
    if form.validate_on_submit():
        try:
            # Create folder configuration
            folders = {
                'inbox': form.folder_inbox.data,
                'processed': form.folder_processed.data,
                'pending': form.folder_pending.data,
                'junk': form.folder_junk.data,
                'approved_ads': form.folder_approved_ads.data,
                'headhunt': form.folder_headhunt.data,
                'whitelist': form.folder_whitelist.data,
                'blacklist': form.folder_blacklist.data,
                'vendor': form.folder_vendor.data,
                'headhunter': form.folder_headhunter.data
            }
            
            # Create account configuration
            account = AccountConfig(
                name=form.name.data,
                email=form.email.data,
                server=form.server.data,
                password=form.password.data,
                folders=folders
            )
            
            # Add port and security settings as attributes
            account.port = form.port.data
            account.username = form.username.data
            account.use_ssl = form.use_ssl.data
            
            # Save account using security manager if available
            if save_account(account):
                flash(f'Account "{account.name}" added successfully!', 'success')
                return redirect(url_for('accounts.list_accounts'))
            else:
                flash('Failed to save account configuration', 'error')
                
        except Exception as e:
            current_app.logger.error(f"Error adding account: {e}")
            flash(f'Error adding account: {str(e)}', 'error')
    
    return render_template('accounts/add.html', form=form)


@accounts_bp.route('/edit/<account_name>', methods=['GET', 'POST'])
@login_required
def edit_account(account_name):
    """Edit existing email account"""
    # Force reload config to get latest saved accounts
    from config import Config
    fresh_config = Config(current_app.mail_config.base_dir, current_app.mail_config.config_file, current_app.mail_config.use_encryption)
    
    # Find the account
    account = None
    for acc in fresh_config.accounts:
        if acc.name == account_name:
            account = acc
            break
    
    if not account:
        current_app.logger.error(f'Account "{account_name}" not found in {len(fresh_config.accounts)} loaded accounts')
        flash(f'Account "{account_name}" not found', 'error')
        return redirect(url_for('accounts.list_accounts'))
    
    form = AccountForm(obj=account)
    
    # Pre-populate folder fields
    if account.folders:
        form.folder_inbox.data = account.folders.get('inbox', 'INBOX')
        form.folder_processed.data = account.folders.get('processed', 'INBOX.Processed')
        form.folder_pending.data = account.folders.get('pending', 'INBOX.Pending')
        form.folder_junk.data = account.folders.get('junk', 'INBOX.Junk')
        form.folder_approved_ads.data = account.folders.get('approved_ads', 'INBOX.Approved_Ads')
        form.folder_headhunt.data = account.folders.get('headhunt', '')
        form.folder_whitelist.data = account.folders.get('whitelist', 'INBOX._whitelist')
        form.folder_blacklist.data = account.folders.get('blacklist', 'INBOX._blacklist')
        form.folder_vendor.data = account.folders.get('vendor', 'INBOX._vendor')
        form.folder_headhunter.data = account.folders.get('headhunter', 'INBOX._headhunter')
    
    # Pre-populate additional fields if they exist
    if hasattr(account, 'port'):
        form.port.data = account.port
    if hasattr(account, 'username'):
        form.username.data = account.username
    if hasattr(account, 'use_ssl'):
        form.use_ssl.data = account.use_ssl
    
    if form.validate_on_submit():
        try:
            # Update account configuration
            account.name = form.name.data
            account.email = form.email.data
            account.server = form.server.data
            account.password = form.password.data
            
            # Update folders
            account.folders = {
                'inbox': form.folder_inbox.data,
                'processed': form.folder_processed.data,
                'pending': form.folder_pending.data,
                'junk': form.folder_junk.data,
                'approved_ads': form.folder_approved_ads.data,
                'headhunt': form.folder_headhunt.data,
                'whitelist': form.folder_whitelist.data,
                'blacklist': form.folder_blacklist.data,
                'vendor': form.folder_vendor.data,
                'headhunter': form.folder_headhunter.data
            }
            
            # Update additional fields
            account.port = form.port.data
            account.username = form.username.data
            account.use_ssl = form.use_ssl.data
            
            # Save updated account using fresh config
            fresh_config.save_config()
            current_app.logger.info(f"Updated and saved account: {account.name}")
            
            # Refresh task manager accounts
            refresh_task_manager_accounts()
            
            flash(f'Account "{account.name}" updated successfully!', 'success')
            return redirect(url_for('accounts.list_accounts'))
                
        except Exception as e:
            current_app.logger.error(f"Error updating account: {e}")
            flash(f'Error updating account: {str(e)}', 'error')
    
    return render_template('accounts/edit.html', form=form, account=account)


@accounts_bp.route('/delete/<account_name>', methods=['POST'])
@login_required
def delete_account(account_name):
    """Delete email account"""
    try:
        # Force reload config to get latest saved accounts
        from config import Config
        fresh_config = Config(current_app.mail_config.base_dir, current_app.mail_config.config_file, current_app.mail_config.use_encryption)
        
        # Find and remove the account
        for i, account in enumerate(fresh_config.accounts):
            if account.name == account_name:
                del fresh_config.accounts[i]
                break
        else:
            flash(f'Account "{account_name}" not found', 'error')
            return redirect(url_for('accounts.list_accounts'))
        
        # Save updated accounts list
        fresh_config.save_config()
        current_app.logger.info(f"Deleted account: {account_name}")
        
        # Refresh task manager accounts
        refresh_task_manager_accounts()
        
        flash(f'Account "{account_name}" deleted successfully!', 'success')
            
    except Exception as e:
        current_app.logger.error(f"Error deleting account: {e}")
        flash(f'Error deleting account: {str(e)}', 'error')
    
    return redirect(url_for('accounts.list_accounts'))


@accounts_bp.route('/test/<account_name>')
@login_required
def test_connection(account_name):
    """Test IMAP connection for an account"""
    try:
        # Force reload config to get latest saved accounts
        from config import Config
        fresh_config = Config(current_app.mail_config.base_dir, current_app.mail_config.config_file, current_app.mail_config.use_encryption)
        
        # Find the account
        account = None
        for acc in fresh_config.accounts:
            if acc.name == account_name:
                account = acc
                break
        
        if not account:
            return jsonify({'success': False, 'error': f'Account "{account_name}" not found'})
        
        # Test connection
        result = test_imap_connection(account)
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f"Error testing connection: {e}")
        return jsonify({'success': False, 'error': str(e)})


@accounts_bp.route('/api/test-connection', methods=['POST'])
@login_required
def api_test_connection():
    """Test IMAP connection with provided credentials"""
    try:
        # Validate CSRF token manually for better error handling
        from flask_wtf.csrf import validate_csrf
        try:
            validate_csrf(request.headers.get('X-CSRFToken'))
        except Exception as e:
            current_app.logger.warning(f"CSRF validation failed: {e}")
            return jsonify({'success': False, 'error': 'CSRF token validation failed. Please refresh the page.'}), 400
        
        data = request.get_json()
        
        # Create temporary account object for testing
        account = AccountConfig(
            name='test',
            email=data.get('email', ''),
            server=data.get('server', ''),
            password=data.get('password', '')
        )
        
        # Add additional fields
        account.port = data.get('port', 993)
        account.username = data.get('username', data.get('email', ''))
        account.use_ssl = data.get('use_ssl', 'ssl')
        
        # Test connection
        result = test_imap_connection(account)
        
        # Add suggested folder configuration if connection successful
        if result.get('success'):
            result['suggested_folders'] = generate_folder_suggestions(result)
        
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f"Error testing connection: {e}")
        return jsonify({'success': False, 'error': str(e)})


def test_imap_connection(account, timeout=30):
    """Test IMAP connection for an account with configurable timeout"""
    try:
        port = getattr(account, 'port', 993)
        username = getattr(account, 'username', account.email)
        use_ssl = getattr(account, 'use_ssl', 'ssl')
        
        # Set socket timeout for connection attempts
        original_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(timeout)
        
        try:
            # Create IMAP connection
            if use_ssl == 'ssl':
                imap = imaplib.IMAP4_SSL(account.server, port)
            else:
                imap = imaplib.IMAP4(account.server, port)
                if use_ssl == 'starttls':
                    imap.starttls()
            
            # Login
            imap.login(username, account.password)
            
            # List folders to verify connection and analyze structure
            status, folders_raw = imap.list()
            
            # Parse folder information
            folders = []
            user_folders = []
            folder_structure = analyze_folder_structure(folders_raw)
            
            if folders_raw:
                for folder_line in folders_raw:
                    if isinstance(folder_line, bytes):
                        folder_line = folder_line.decode('utf-8')
                    
                    # Parse IMAP LIST response: (flags) "delimiter" "name"
                    import re
                    match = re.match(r'\(([^)]*)\)\s+"([^"]*)"\s+"?([^"]*)"?', folder_line)
                    if match:
                        flags, delimiter, name = match.groups()
                        folder_name = name.strip('"')
                        folder_info = {
                            'name': folder_name,
                            'flags': flags,
                            'delimiter': delimiter
                        }
                        folders.append(folder_info)
                        
                        # Filter to user-visible folders (exclude system/hidden folders)
                        if is_user_folder(folder_name, flags):
                            user_folders.append(folder_info)
            
            # Get some basic folder stats
            inbox_exists = any(f['name'].upper() == 'INBOX' for f in folders)
            
            # Logout
            imap.logout()
            
            return {
                'success': True, 
                'message': f'Successfully connected to {account.server}. Found {len(user_folders)} user folders ({len(folders)} total including system folders).',
                'folder_count': len(user_folders),
                'folders': user_folders[:10],  # Limit to first 10 user folders for display
                'folder_structure': folder_structure,
                'inbox_exists': inbox_exists,
                'total_folders': len(folders),
                'user_folders': len(user_folders),
                'all_folders': folders[:20]  # Include all folders for debugging
            }
        
        finally:
            # Restore original timeout
            socket.setdefaulttimeout(original_timeout)
        
    except socket.timeout:
        return {'success': False, 'error': f'Connection timeout after {timeout} seconds. Please check server address and port.'}
    except imaplib.IMAP4.error as e:
        return {'success': False, 'error': f'IMAP error: {str(e)}'}
    except ssl.SSLError as e:
        return {'success': False, 'error': f'SSL error: {str(e)}'}
    except Exception as e:
        return {'success': False, 'error': f'Connection error: {str(e)}'}


def is_user_folder(folder_name, flags):
    """
    Determine if a folder is a user-visible folder (not system/hidden folder)
    
    Args:
        folder_name: Name of the folder
        flags: IMAP flags for the folder
        
    Returns:
        bool: True if folder should be visible to user
    """
    folder_upper = folder_name.upper()
    
    # Always include INBOX
    if folder_upper == 'INBOX':
        return True
    
    # Exclude common system/hidden folders
    system_folders = {
        '[GMAIL]',  # Gmail system folder
        'CALENDAR',  # Calendar folders
        'CONTACTS',  # Contact folders
        'TASKS',     # Task folders
        'NOTES',     # Notes folders
    }
    
    # Check for system folder patterns
    if folder_upper in system_folders:
        return False
    
    # Check for Gmail-style system folders
    if folder_upper.startswith('[') and folder_upper.endswith(']'):
        return False
    
    # Check for folders that start with system prefixes
    system_prefixes = ['&', '#']
    if any(folder_name.startswith(prefix) for prefix in system_prefixes):
        return False
    
    # Check flags for system folders
    if flags:
        flag_upper = flags.upper()
        # Exclude folders marked as noselect (containers only)
        if 'NOSELECT' in flag_upper:
            return False
    
    # Common user folders we want to include
    user_folder_names = {
        'SENT', 'DRAFTS', 'TRASH', 'SPAM', 'JUNK', 'ARCHIVE', 'DELETED',
        'OUTBOX', 'SENT ITEMS', 'DELETED ITEMS', 'SENT MESSAGES'
    }
    
    if folder_upper in user_folder_names:
        return True
    
    # Include folders under INBOX (like INBOX.Sent, INBOX.Trash)
    if folder_upper.startswith('INBOX.') or folder_upper.startswith('INBOX/'):
        return True
    
    # Include other regular folders (not starting with special characters)
    if not folder_name.startswith('.') and not folder_name.startswith('_'):
        return True
    
    return False


def analyze_folder_structure(folders_raw):
    """Analyze IMAP folder structure to determine naming convention"""
    if not folders_raw:
        return {'type': 'unknown', 'delimiter': '.', 'pattern': 'Unable to determine'}
    
    patterns = []
    delimiters = set()
    
    for folder_line in folders_raw:
        if isinstance(folder_line, bytes):
            folder_line = folder_line.decode('utf-8')
        
        # Extract folder name and delimiter
        import re
        match = re.match(r'\(([^)]*)\)\s+"([^"]*)"\s+"?([^"]*)"?', folder_line)
        if match:
            flags, delimiter, name = match.groups()
            name = name.strip('"')
            
            if delimiter:
                delimiters.add(delimiter)
            
            # Look for common patterns
            if name.upper().startswith('INBOX'):
                if delimiter and delimiter in name:
                    patterns.append(f'INBOX{delimiter}SubFolder')
                else:
                    patterns.append('INBOX')
    
    # Determine most common delimiter
    common_delimiter = '.' if '.' in delimiters else (list(delimiters)[0] if delimiters else '.')
    
    # Determine structure type
    if any('INBOX.' in p for p in patterns):
        structure_type = 'hierarchical'
        pattern = f'INBOX{common_delimiter}FolderName'
    elif any('INBOX/' in p for p in patterns):
        structure_type = 'hierarchical'
        pattern = f'INBOX{common_delimiter}FolderName'
    elif len(patterns) > 0:
        structure_type = 'flat'
        pattern = 'FolderName (flat structure)'
    else:
        structure_type = 'unknown'
        pattern = 'Unable to determine pattern'
    
    return {
        'type': structure_type,
        'delimiter': common_delimiter,
        'pattern': pattern,
        'example_folders': patterns[:3]  # First 3 examples
    }


def generate_folder_suggestions(connection_result):
    """Generate suggested folder configuration based on IMAP connection results"""
    folder_structure = connection_result.get('folder_structure', {})
    delimiter = folder_structure.get('delimiter', '.')
    structure_type = folder_structure.get('type', 'unknown')
    
    # Base folder suggestions
    suggestions = {}
    
    if structure_type == 'hierarchical':
        # Use INBOX.FolderName pattern
        suggestions = {
            'folder_inbox': 'INBOX',
            'folder_processed': f'INBOX{delimiter}Processed',
            'folder_pending': f'INBOX{delimiter}Pending',
            'folder_junk': f'INBOX{delimiter}Junk',
            'folder_approved_ads': f'INBOX{delimiter}Approved_Ads',
            'folder_headhunt': f'INBOX{delimiter}HeadHunt',
            'folder_packages': f'INBOX{delimiter}Packages',
            'folder_receipts': f'INBOX{delimiter}Receipts',
            'folder_linkedin': f'INBOX{delimiter}LinkedIn',
            'folder_whitelist': f'INBOX{delimiter}_whitelist',
            'folder_blacklist': f'INBOX{delimiter}_blacklist',
            'folder_vendor': f'INBOX{delimiter}_vendor',
            'folder_headhunter': f'INBOX{delimiter}_headhunter'
        }
    else:
        # Use flat structure or best guess
        suggestions = {
            'folder_inbox': 'INBOX',
            'folder_processed': 'Processed',
            'folder_pending': 'Pending',
            'folder_junk': 'Junk',
            'folder_approved_ads': 'Approved_Ads',
            'folder_headhunt': 'HeadHunt',
            'folder_packages': 'Packages',
            'folder_receipts': 'Receipts',
            'folder_linkedin': 'LinkedIn',
            'folder_whitelist': '_whitelist',
            'folder_blacklist': '_blacklist',
            'folder_vendor': '_vendor',
            'folder_headhunter': '_headhunter'
        }
    
    # Check for existing folders and adjust suggestions
    existing_folders = connection_result.get('folders', [])
    existing_names = {f['name'].upper() for f in existing_folders}
    
    # Look for common existing folders and suggest them
    folder_mapping = {
        'SPAM': 'folder_junk',
        'TRASH': 'folder_junk',
        'SENT': None,  # Don't suggest for our purposes
        'DRAFTS': None,  # Don't suggest for our purposes
        'JUNK': 'folder_junk'
    }
    
    for folder in existing_folders:
        folder_upper = folder['name'].upper()
        if folder_upper in folder_mapping and folder_mapping[folder_upper]:
            suggestions[folder_mapping[folder_upper]] = folder['name']
    
    return suggestions


def refresh_task_manager_accounts():
    """Notify task manager to refresh accounts from configuration"""
    try:
        # Import and call task manager directly
        from services.task_manager import get_task_manager
        task_manager = get_task_manager()
        task_manager.refresh_accounts_from_config()
        current_app.logger.info("Task manager accounts refreshed successfully")
    except Exception as e:
        current_app.logger.warning(f"Could not refresh task manager accounts: {e}")


def save_account(account):
    """Save a new account to configuration"""
    try:
        # Force reload config to get latest saved accounts before adding new one
        from config import Config
        fresh_config = Config(current_app.mail_config.base_dir, current_app.mail_config.config_file, current_app.mail_config.use_encryption)
        
        # Add account to fresh config and save
        fresh_config.accounts.append(account)
        fresh_config.save_config()
        current_app.logger.info(f"Added and saved account: {account.name} (total accounts now: {len(fresh_config.accounts)})")
        
        # Refresh task manager accounts
        refresh_task_manager_accounts()
        
        return True
    except Exception as e:
        current_app.logger.error(f"Error saving account: {e}")
        return False


def save_all_accounts():
    """Save all accounts to secure configuration"""
    try:
        # Use the config's save_config method which handles secure storage
        current_app.mail_config.save_config()
        current_app.logger.info(f"Saved {len(current_app.mail_config.accounts)} accounts to secure storage")
        
        # Refresh task manager accounts
        refresh_task_manager_accounts()
        
        return True
    except Exception as e:
        current_app.logger.error(f"Error saving accounts: {e}")
        return False


@accounts_bp.route('/create-folders/<account_name>', methods=['GET', 'POST'])
@login_required
def create_folders(account_name):
    """Display folder creation page and handle folder creation"""
    try:
        # Force reload config to get latest saved accounts
        from config import Config
        fresh_config = Config(current_app.mail_config.base_dir, current_app.mail_config.config_file, current_app.mail_config.use_encryption)
        
        # Find the account
        account = None
        for acc in fresh_config.accounts:
            if acc.name == account_name:
                account = acc
                break
        
        if not account:
            flash(f'Account "{account_name}" not found', 'error')
            return redirect(url_for('accounts.list_accounts'))
        
        # Get folder information
        processor = EmailProcessor(account)
        folder_info = processor.get_folder_status()
        
        if request.method == 'POST':
            action = request.form.get('action')
            current_app.logger.info(f"POST request received for create_folders: action={action}")
            
            if action == 'create':
                try:
                    # Create the missing folders
                    current_app.logger.info(f"Creating folders for account {account.email}")
                    creation_result = processor._validate_and_setup_folders()
                    current_app.logger.info(f"Folder creation result: {creation_result}")
                    
                    if creation_result['success']:
                        created_count = len(creation_result['created_folders'])
                        if created_count > 0:
                            flash(f'Successfully created {created_count} folders for {account.email}!', 'success')
                            current_app.logger.info(f"Successfully created {created_count} folders")
                        else:
                            flash('All required folders already exist.', 'info')
                            current_app.logger.info("No folders needed to be created")
                    else:
                        flash(f'Error creating folders: {creation_result["error"]}', 'error')
                        current_app.logger.error(f"Folder creation failed: {creation_result['error']}")
                    
                    return redirect(url_for('accounts.list_accounts'))
                    
                except Exception as folder_error:
                    current_app.logger.error(f"Exception during folder creation: {folder_error}")
                    flash(f'Exception during folder creation: {str(folder_error)}', 'error')
                    return redirect(url_for('accounts.list_accounts'))
            
            elif action == 'skip':
                flash('Folder creation skipped. You can create folders later if needed.', 'info')
                return redirect(url_for('accounts.list_accounts'))
        
        return render_template('accounts/create_folders.html', 
                             account=account, 
                             folder_info=folder_info)
        
    except Exception as e:
        current_app.logger.error(f"Error in create_folders: {e}")
        flash(f'Error accessing folder information: {str(e)}', 'error')
        return redirect(url_for('accounts.list_accounts'))


@accounts_bp.route('/api/accounts/<account_email>/folders')
@login_required
def get_account_folders(account_email):
    """API endpoint to get folders for a specific account (for rules dropdown)"""
    try:
        # Force reload config to get latest saved accounts
        from config import Config
        fresh_config = Config(current_app.mail_config.base_dir, current_app.mail_config.config_file, current_app.mail_config.use_encryption)
        
        # Find the account
        account = None
        for acc in fresh_config.accounts:
            if acc.email == account_email:
                account = acc
                break
        
        if not account:
            return {'success': False, 'error': 'Account not found'}, 404
        
        # Get folder list from IMAP server
        folders = []
        try:
            # Test IMAP connection and get folders
            mb = imaplib.IMAP4_SSL(account.server, account.port or 993)
            mb.login(account.email, account.password)
            
            # Get folder list
            result, folder_list = mb.list()
            mb.logout()
            
            if result == 'OK':
                for folder_item in folder_list:
                    # Parse folder item - format is usually: (flags) "delimiter" "folder_name"
                    if isinstance(folder_item, bytes):
                        folder_item = folder_item.decode('utf-8')
                    
                    # Extract folder name from IMAP response
                    parts = folder_item.split('"')
                    if len(parts) >= 3:
                        folder_name = parts[-2]  # Usually the last quoted string is the folder name
                        if folder_name and is_user_folder(folder_name, None):
                            folders.append(folder_name)
            
            # Add common folders from account configuration if not already in list
            if hasattr(account, 'folders') and account.folders:
                config_folders = [
                    account.folders.get('processed'),
                    account.folders.get('pending'), 
                    account.folders.get('junk'),
                    account.folders.get('approved_ads'),
                    account.folders.get('whitelist'),
                    account.folders.get('blacklist'),
                    account.folders.get('vendor')
                ]
                
                for folder in config_folders:
                    if folder and folder not in folders and folder != 'INBOX':
                        folders.append(folder)
            
            # Sort folders
            folders.sort()
            
        except Exception as e:
            current_app.logger.warning(f"Could not fetch folders for {account_email}: {e}")
            # Return basic folders from configuration as fallback
            if hasattr(account, 'folders') and account.folders:
                folders = [folder for folder in account.folders.values() 
                          if folder and folder != 'INBOX']
            else:
                folders = ['INBOX.Processed', 'INBOX.Pending', 'INBOX.Packages', 'INBOX.Receipts']
        
        return {'success': True, 'folders': folders}
        
    except Exception as e:
        current_app.logger.error(f"Error getting folders for account {account_email}: {e}")
        return {'success': False, 'error': str(e)}, 500