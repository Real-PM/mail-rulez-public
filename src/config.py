import os
import configparser
from typing import List, Optional, Dict
from dataclasses import dataclass
from pathlib import Path
import json


@dataclass
class AccountConfig:
    """Configuration for a single email account"""
    name: str
    server: str
    email: str
    password: str
    folders: Optional[Dict[str, str]] = None
    
    def __post_init__(self):
        if self.folders is None:
            self.folders = {
                'inbox': 'INBOX',
                'processed': 'INBOX.Processed',
                'pending': 'INBOX.Pending',
                'junk': 'INBOX.Junk',
                'approved_ads': 'INBOX.Approved_Ads',
                'headhunt': 'INBOX.HeadHunt',
                'whitelist': 'INBOX._whitelist',
                'blacklist': 'INBOX._blacklist',
                'vendor': 'INBOX._vendor',
                'headhunter': 'INBOX._headhunter'
            }


class Config:
    """Centralized configuration management for Mail-Rulez"""
    
    def __init__(self, base_dir: Optional[str] = None, config_file: Optional[str] = None, use_encryption: bool = True):
        # Set base directory - check environment variables first
        if base_dir:
            self.base_dir = Path(base_dir)
        elif os.getenv('MAIL_RULEZ_APP_DIR'):
            self.base_dir = Path(os.getenv('MAIL_RULEZ_APP_DIR'))
        elif os.getenv('MAIL_RULEZ_BASE_DIR'):
            self.base_dir = Path(os.getenv('MAIL_RULEZ_BASE_DIR'))
        else:
            self.base_dir = Path.cwd()
        
        # Set up directory paths with environment variable support
        self.data_dir = Path(os.getenv('MAIL_RULEZ_DATA_DIR', self.base_dir / "data"))
        self.lists_dir = Path(os.getenv('MAIL_RULEZ_LISTS_DIR', self.base_dir / "lists"))
        self.config_dir = Path(os.getenv('MAIL_RULEZ_CONFIG_DIR', self.base_dir))
        self.backups_dir = Path(os.getenv('MAIL_RULEZ_BACKUPS_DIR', self.base_dir / "backups"))
        
        # Configuration file paths
        self.config_file = Path(config_file) if config_file else self.config_dir / "config.ini"
        self.secure_config_file = self.config_dir / "secure_config.json"
        
        # Security settings
        self.use_encryption = use_encryption
        self._security_manager = None
        
        # Core lists and file paths
        self.core_lists = ['white', 'black', 'vendor']
        self.list_files = {
            'white': self.lists_dir / "white.txt",
            'black': self.lists_dir / "black.txt", 
            'vendor': self.lists_dir / "vendor.txt"
        }
        
        # Load configuration
        self.accounts: List[AccountConfig] = []
        self.timezone = "US/Pacific"
        self.processing_intervals = {
            'inbox': 5,
            'folders': 4,
            'forwarding': 1
        }
        
        # Email retention settings (days)
        self.retention_settings = {
            'approved_ads': 30,  # Vendor emails default 30 days
            'processed': 90,     # Processed emails 90 days
            'pending': 365,      # Pending emails 1 year (user decisions)
            'junk': 7           # Junk emails 7 days
        }
        
        self._load_config()
        self._ensure_directories()
    
    def _get_security_manager(self):
        """Get or create security manager"""
        if self._security_manager is None and self.use_encryption:
            from security import get_security_manager
            self._security_manager = get_security_manager()
        return self._security_manager
    
    def _load_config(self):
        """Load configuration from file and environment variables"""
        # Load from secure config first if it exists
        if self.secure_config_file.exists() and self.use_encryption:
            self._load_from_secure_config()
        # Only load from config.ini if no secure config was loaded
        elif self.config_file.exists():
            self._load_from_ini()
        
        # Override with environment variables
        self._load_from_env()
    
    def _load_from_ini(self):
        """Load configuration from config.ini file"""
        config = configparser.ConfigParser()
        config.read(self.config_file)
        
        for section_name in config.sections():
            account = AccountConfig(
                name=section_name,
                server=config[section_name].get('server'),
                email=config[section_name].get('email'),
                password=config[section_name].get('password')
            )
            self.accounts.append(account)
    
    def _load_from_env(self):
        """Load configuration from environment variables"""
        # Override timezone if set
        if os.getenv('MAIL_RULEZ_TIMEZONE'):
            self.timezone = os.getenv('MAIL_RULEZ_TIMEZONE')
        
        # Override base directory if set
        if os.getenv('MAIL_RULEZ_BASE_DIR'):
            self.base_dir = Path(os.getenv('MAIL_RULEZ_BASE_DIR'))
            self.lists_dir = self.base_dir / "lists"
            self._update_list_paths()
        
        # Override lists directory if set
        if os.getenv('MAIL_RULEZ_LISTS_DIR'):
            self.lists_dir = Path(os.getenv('MAIL_RULEZ_LISTS_DIR'))
            self._update_list_paths()
        
        # Load single account from environment (for backward compatibility)
        server = os.getenv('MAIL_RULEZ_SERVER')
        email = os.getenv('MAIL_RULEZ_EMAIL') 
        password = os.getenv('MAIL_RULEZ_PASSWORD')
        
        if server and email and password:
            # Remove any existing env account and add new one
            self.accounts = [acc for acc in self.accounts if acc.name != 'env_account']
            account = AccountConfig(
                name='env_account',
                server=server,
                email=email,
                password=password
            )
            self.accounts.append(account)
    
    def _update_list_paths(self):
        """Update list file paths when lists_dir changes"""
        self.list_files = {
            'white': self.lists_dir / "white.txt",
            'black': self.lists_dir / "black.txt",
            'vendor': self.lists_dir / "vendor.txt"
        }
    
    def _ensure_directories(self):
        """Create necessary directories if they don't exist"""
        # Create all configured directories
        for directory in [self.data_dir, self.lists_dir, self.config_dir, self.backups_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Create empty list files if they don't exist
        for list_file in self.list_files.values():
            if not list_file.exists():
                list_file.touch()
    
    def get_all_lists(self) -> Dict[str, Path]:
        """Discover all .txt files in lists directory (core + custom)"""
        all_lists = {}
        
        # Add core lists
        for name, path in self.list_files.items():
            all_lists[name] = path
        
        # Discover custom lists (any .txt file not in core lists)
        if self.lists_dir.exists():
            for list_file in self.lists_dir.glob("*.txt"):
                list_name = list_file.stem
                if list_name not in self.core_lists:
                    all_lists[list_name] = list_file
        
        return all_lists
    
    def get_list_metadata(self) -> Dict[str, Dict]:
        """Get metadata about all lists"""
        metadata = {}
        all_lists = self.get_all_lists()
        
        for list_name, list_path in all_lists.items():
            entry_count = 0
            if list_path.exists():
                try:
                    with open(list_path, 'r') as f:
                        entry_count = len([line.strip() for line in f.readlines() if line.strip()])
                except Exception:
                    entry_count = 0
            
            metadata[list_name] = {
                'type': 'core' if list_name in self.core_lists else 'custom',
                'path': str(list_path),
                'entry_count': entry_count,
                'exists': list_path.exists()
            }
        
        return metadata
    
    def get_list_file_path(self, list_name: str) -> str:
        """Get the full path to a list file (core or custom)"""
        all_lists = self.get_all_lists()
        if list_name not in all_lists:
            raise ValueError(f"Unknown list name: {list_name}. Valid names: {list(all_lists.keys())}")
        return str(all_lists[list_name])
    
    def add_account(self, name: str, server: str, email: str, password: str, 
                   folders: Optional[Dict[str, str]] = None) -> AccountConfig:
        """Add a new account configuration"""
        account = AccountConfig(name, server, email, password, folders)
        self.accounts.append(account)
        return account
    
    def get_account(self, name: str) -> Optional[AccountConfig]:
        """Get account configuration by name"""
        for account in self.accounts:
            if account.name == name:
                return account
        return None
    
    def get_retention_setting(self, folder_type: str) -> int:
        """Get retention setting for a folder type (in days)"""
        return self.retention_settings.get(folder_type, 30)  # Default 30 days
    
    def set_retention_setting(self, folder_type: str, days: int):
        """Set retention setting for a folder type"""
        self.retention_settings[folder_type] = days
    
    def get_all_retention_settings(self) -> Dict[str, int]:
        """Get all retention settings"""
        return self.retention_settings.copy()
    
    def _load_from_secure_config(self):
        """Load configuration from encrypted secure_config.json"""
        try:
            with open(self.secure_config_file, 'r') as f:
                secure_data = json.load(f)
            
            security_manager = self._get_security_manager()
            if not security_manager:
                return
            
            from security import SecureAccountConfig
            secure_account_config = SecureAccountConfig(security_manager)
            
            # Load accounts from secure storage
            for account_data in secure_data.get('accounts', []):
                try:
                    account = secure_account_config.decrypt_account_config(account_data)
                    self.accounts.append(account)
                except Exception as e:
                    print(f"Warning: Could not decrypt account {account_data.get('name', 'unknown')}: {e}")
            
            # Load retention settings if present
            if 'retention_settings' in secure_data:
                self.retention_settings.update(secure_data['retention_settings'])
        except Exception as e:
            print(f"Warning: Could not load secure config: {e}")
    
    def save_config(self, use_secure_storage: bool = None):
        """Save current configuration"""
        if use_secure_storage is None:
            use_secure_storage = self.use_encryption
        
        if use_secure_storage and self._get_security_manager():
            self._save_secure_config()
        else:
            self._save_config_ini()
    
    def _save_secure_config(self):
        """Save configuration to encrypted secure_config.json"""
        security_manager = self._get_security_manager()
        if not security_manager:
            return
        
        from security import SecureAccountConfig
        secure_account_config = SecureAccountConfig(security_manager)
        
        secure_data = {
            'accounts': [],
            'retention_settings': self.retention_settings,
            'version': '1.0',
            'created_at': str(Path(__file__).stat().st_mtime)
        }
        
        for account in self.accounts:
            if account.name != 'env_account':  # Don't save env-based accounts
                encrypted_account = secure_account_config.encrypt_account_config(account)
                secure_data['accounts'].append(encrypted_account)
        
        with open(self.secure_config_file, 'w') as f:
            json.dump(secure_data, f, indent=2)
        
        # Set secure permissions and ownership for container environment
        try:
            import os
            import stat
            
            # Set file permissions to read/write for owner only
            os.chmod(self.secure_config_file, stat.S_IRUSR | stat.S_IWUSR)
            
            # In container, set ownership to mailrulez user if running as root
            if hasattr(os, 'getuid') and hasattr(os, 'chown'):
                try:
                    if os.getuid() == 0:  # Running as root
                        os.chown(self.secure_config_file, 999, 999)  # mailrulez:mailrulez
                except (OSError, PermissionError):
                    # May fail if not running as root or user doesn't exist
                    pass
        except ImportError:
            # os module not available (shouldn't happen, but be safe)
            pass
    
    def _save_config_ini(self):
        """Save configuration to config.ini (legacy format)"""
        config = configparser.ConfigParser()
        
        for account in self.accounts:
            if account.name != 'env_account':  # Don't save env-based accounts
                config[account.name] = {
                    'server': account.server,
                    'email': account.email,
                    'password': account.password
                }
        
        with open(self.config_file, 'w') as f:
            config.write(f)
        
        # Set secure permissions and ownership for container environment
        try:
            import os
            import stat
            
            # Set file permissions to read/write for owner only
            os.chmod(self.config_file, stat.S_IRUSR | stat.S_IWUSR)
            
            # In container, set ownership to mailrulez user if running as root
            if hasattr(os, 'getuid') and hasattr(os, 'chown'):
                try:
                    if os.getuid() == 0:  # Running as root
                        os.chown(self.config_file, 999, 999)  # mailrulez:mailrulez
                except (OSError, PermissionError):
                    # May fail if not running as root or user doesn't exist
                    pass
        except ImportError:
            # os module not available (shouldn't happen, but be safe)
            pass


# Global config instance - can be overridden for testing
_config_instance = None

def get_config(base_dir: Optional[str] = None, config_file: Optional[str] = None) -> Config:
    """Get the global configuration instance"""
    global _config_instance
    if _config_instance is None or base_dir is not None or config_file is not None:
        _config_instance = Config(base_dir, config_file)
    return _config_instance

def set_config(config: Config):
    """Set the global configuration instance (useful for testing)"""
    global _config_instance
    _config_instance = config