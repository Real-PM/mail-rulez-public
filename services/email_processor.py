"""
Email Processing Service

Core service class for managing email processing for individual accounts.
Handles startup and maintenance modes, integrates with rules engine,
and provides web-manageable email processing capabilities.
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, asdict
import json
import imaplib

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

# Import existing modules
import functions as pf
import process_inbox as pi
import rules as r
from functions import Account
from config import get_config, AccountConfig


class ServiceState(Enum):
    """Email processing service states"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING_STARTUP = "running_startup"
    RUNNING_MAINTENANCE = "running_maintenance"
    STOPPING = "stopping"
    ERROR = "error"


class ProcessingMode(Enum):
    """Email processing modes"""
    STARTUP = "startup"
    MAINTENANCE = "maintenance"


@dataclass
class ServiceStats:
    """Statistics for email processing service"""
    emails_processed: int = 0
    emails_pending: int = 0
    last_run: Optional[datetime] = None
    total_runtime: timedelta = timedelta()
    error_count: int = 0
    avg_processing_time: float = 0.0
    mode_start_time: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'emails_processed': self.emails_processed,
            'emails_pending': self.emails_pending,
            'last_run': self.last_run.isoformat() if self.last_run else None,
            'total_runtime': str(self.total_runtime),
            'error_count': self.error_count,
            'avg_processing_time': self.avg_processing_time,
            'mode_start_time': self.mode_start_time.isoformat() if self.mode_start_time else None
        }


class EmailProcessor:
    """
    Email processing service for a single account
    
    Manages email processing in startup or maintenance mode,
    provides statistics, and integrates with the rules engine.
    """
    
    def __init__(self, account_config: AccountConfig):
        self.account_config = account_config
        self.account = Account(
            account_config.server,
            account_config.email, 
            account_config.password
        )
        
        # Service state
        self.state = ServiceState.STOPPED
        self.mode = ProcessingMode.STARTUP
        self.stats = ServiceStats()
        
        # Scheduler and threading
        import pytz
        
        self.scheduler = BackgroundScheduler(timezone=pytz.UTC)
        self._lock = threading.Lock()
        
        # Configuration
        self.config = get_config()
        self.processing_intervals = {
            'inbox': 5,      # Process inbox every 5 minutes
            'folders': 4,    # Process training folders every 4 minutes
            'forwarding': 1  # Check forwarding every minute
        }
        
        # Logger with structured context
        from logging_config import get_logger
        self.logger = get_logger(
            f'email_processor.{account_config.email}',
            account_email=account_config.email
        )
        
        # Error tracking
        self.last_error = None
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5
        
    def start(self, mode: ProcessingMode = ProcessingMode.STARTUP) -> bool:
        """
        Start email processing service
        
        Args:
            mode: Processing mode (startup or maintenance)
            
        Returns:
            bool: True if started successfully, False otherwise
        """
        with self._lock:
            if self.state != ServiceState.STOPPED:
                self.logger.warning(f"Cannot start service in state {self.state}")
                return False
                
            try:
                self.state = ServiceState.STARTING
                self.mode = mode
                self.stats.mode_start_time = datetime.now()
                
                self.logger.info(f"Starting email processing service in {mode.value} mode")
                
                # Test connection first
                if not self._test_connection():
                    self.state = ServiceState.ERROR
                    self.last_error = "Failed to connect to email server"
                    return False
                
                # Validate and create required folders
                folder_status = self._validate_and_setup_folders()
                if not folder_status['success']:
                    self.state = ServiceState.ERROR
                    self.last_error = f"Folder setup failed: {folder_status['error']}"
                    return False
                
                # Start scheduler with appropriate jobs
                self._setup_jobs()
                self.scheduler.start()
                
                self.state = ServiceState.RUNNING_STARTUP if mode == ProcessingMode.STARTUP else ServiceState.RUNNING_MAINTENANCE
                self.logger.info(f"Email processing service started successfully")
                return True
                
            except Exception as e:
                self.state = ServiceState.ERROR
                self.last_error = str(e)
                self.logger.error(f"Failed to start service: {e}")
                return False
    
    def stop(self) -> bool:
        """
        Stop email processing service
        
        Returns:
            bool: True if stopped successfully, False otherwise
        """
        with self._lock:
            if self.state in [ServiceState.STOPPED, ServiceState.STOPPING]:
                return True
                
            try:
                self.state = ServiceState.STOPPING
                self.logger.info("Stopping email processing service")
                
                # Stop scheduler
                if self.scheduler.running:
                    self.scheduler.shutdown(wait=True)
                
                self.state = ServiceState.STOPPED
                self.logger.info("Email processing service stopped")
                return True
                
            except Exception as e:
                self.state = ServiceState.ERROR
                self.last_error = str(e)
                self.logger.error(f"Failed to stop service: {e}")
                return False
    
    def restart(self) -> bool:
        """
        Restart email processing service
        
        Returns:
            bool: True if restarted successfully, False otherwise
        """
        current_mode = self.mode
        if self.stop():
            time.sleep(1)  # Brief pause
            return self.start(current_mode)
        return False
    
    def switch_mode(self, new_mode: ProcessingMode) -> bool:
        """
        Switch processing mode (startup <-> maintenance)
        
        Args:
            new_mode: New processing mode
            
        Returns:
            bool: True if switched successfully, False otherwise
        """
        if self.mode == new_mode:
            return True
            
        with self._lock:
            if self.state not in [ServiceState.RUNNING_STARTUP, ServiceState.RUNNING_MAINTENANCE]:
                self.logger.warning(f"Cannot switch mode in state {self.state}")
                return False
                
            try:
                old_mode = self.mode
                self.logger.info(f"Switching from {old_mode.value} to {new_mode.value} mode")
                
                # Stop current jobs
                self.scheduler.remove_all_jobs()
                
                # Update mode and state
                self.mode = new_mode
                self.state = ServiceState.RUNNING_STARTUP if new_mode == ProcessingMode.STARTUP else ServiceState.RUNNING_MAINTENANCE
                self.stats.mode_start_time = datetime.now()
                
                # Setup new jobs
                self._setup_jobs()
                
                self.logger.info(f"Successfully switched to {new_mode.value} mode")
                return True
                
            except Exception as e:
                self.state = ServiceState.ERROR
                self.last_error = str(e)
                self.logger.error(f"Failed to switch mode: {e}")
                return False
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current service status
        
        Returns:
            dict: Service status information
        """
        with self._lock:
            return {
                'account_email': self.account_config.email,
                'state': self.state.value,
                'mode': self.mode.value,
                'stats': self.stats.to_dict(),
                'last_error': self.last_error,
                'consecutive_errors': self.consecutive_errors,
                'scheduler_running': self.scheduler.running if hasattr(self.scheduler, 'running') else False,
                'active_jobs': len(self.scheduler.get_jobs()) if hasattr(self.scheduler, 'get_jobs') else 0
            }
    
    def get_stats_snapshot(self) -> Dict[str, Any]:
        """
        Get atomic snapshot of current statistics for safe concurrent access
        
        Returns:
            dict: Immutable copy of current stats
        """
        with self._lock:
            # Create deep copy of stats to prevent concurrent modification
            snapshot = {
                'emails_processed': self.stats.emails_processed,
                'emails_pending': self.stats.emails_pending,
                'last_run': self.stats.last_run,
                'total_runtime': self.stats.total_runtime,
                'error_count': self.stats.error_count,
                'avg_processing_time': self.stats.avg_processing_time,
                'mode_start_time': self.stats.mode_start_time,
                'state': self.state.value,
                'mode': self.mode.value,
                'account': self.account_config.email
            }
            return snapshot
    
    def _test_connection(self) -> bool:
        """Test connection to email server"""
        try:
            mb = self.account.login()
            mb.logout()
            return True
        except Exception as e:
            self.logger.error(f"Connection test failed: {e}")
            return False
    
    def _validate_and_setup_folders(self) -> Dict[str, Any]:
        """
        Validate and create required folders for email processing
        
        Returns:
            dict: Status with success/error information and folder details
        """
        try:
            mb = self.account.login()
            
            # Get list of existing folders
            existing_folders = self._get_existing_folders(mb)
            
            # Get required folders from account configuration
            required_folders = self._get_required_folders()
            
            # Check which folders need to be created
            missing_folders = []
            for folder_type, folder_name in required_folders.items():
                if folder_name not in existing_folders:
                    missing_folders.append((folder_type, folder_name))
            
            result = {
                'success': True,
                'existing_folders': existing_folders,
                'required_folders': required_folders,
                'missing_folders': missing_folders,
                'created_folders': [],
                'error': None
            }
            
            # If folders are missing, attempt to create them
            if missing_folders:
                self.logger.info(f"Found {len(missing_folders)} missing folders that need to be created")
                
                for folder_type, folder_name in missing_folders:
                    try:
                        # Create the folder using imap_tools folder manager
                        mb.folder.create(folder_name)
                        result['created_folders'].append((folder_type, folder_name))
                        self.logger.info(f"Created folder: {folder_name} ({folder_type})")
                            
                    except Exception as e:
                        self.logger.warning(f"Exception creating folder {folder_name}: {e}")
                        # Continue with other folders
            
            mb.logout()
            return result
            
        except Exception as e:
            self.logger.error(f"Folder validation failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'existing_folders': [],
                'required_folders': {},
                'missing_folders': [],
                'created_folders': []
            }
    
    def _get_existing_folders(self, mb) -> List[str]:
        """Get list of existing folders from IMAP server"""
        try:
            # Use imap_tools folder manager to get folder list
            folders = mb.folder.list()
            folder_names = [folder.name for folder in folders]
            return folder_names
            
        except Exception as e:
            self.logger.error(f"Failed to get existing folders: {e}")
            return []
    
    def _get_required_folders(self) -> Dict[str, str]:
        """Get required folders based on account configuration and processing mode"""
        folders = {}
        
        # Core processing folders (always required)
        if hasattr(self.account_config, 'folders') and self.account_config.folders:
            # Essential folders for email processing
            essential_folders = [
                'pending',      # For unknown senders in startup mode
                'processed',    # For processed emails in startup mode  
                'junk',         # For spam/rejected emails
                'approved_ads', # For approved vendor emails
                'headhunt',     # For head hunt emails
                'packages',     # For package delivery emails
                'receipts',     # For receipt emails
                'linkedin',     # For LinkedIn emails
                'whitelist',    # Training folder for whitelisted emails
                'blacklist',    # Training folder for blacklisted emails
                'vendor',       # Training folder for vendor emails
                'headhunter',   # Training folder for headhunter emails
            ]
            
            for folder_key in essential_folders:
                if folder_key in self.account_config.folders:
                    folder_name = self.account_config.folders[folder_key]
                    if folder_name and folder_name != 'INBOX':  # Don't try to create INBOX
                        folders[folder_key] = folder_name
        
        return folders
    
    def get_folder_status(self) -> Dict[str, Any]:
        """
        Get folder status without creating missing folders
        
        Returns:
            dict: Folder analysis for user review
        """
        try:
            mb = self.account.login()
            
            # Get list of existing folders
            existing_folders = self._get_existing_folders(mb)
            
            # Get required folders from account configuration
            required_folders = self._get_required_folders()
            
            # Check which folders need to be created
            missing_folders = []
            existing_required = []
            
            for folder_type, folder_name in required_folders.items():
                if folder_name in existing_folders:
                    existing_required.append((folder_type, folder_name))
                else:
                    missing_folders.append((folder_type, folder_name))
            
            mb.logout()
            
            return {
                'success': True,
                'total_existing': len(existing_folders),
                'required_folders': required_folders,
                'existing_required': existing_required,
                'missing_folders': missing_folders,
                'needs_creation': len(missing_folders) > 0,
                'error': None
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get folder status: {e}")
            return {
                'success': False,
                'error': str(e),
                'total_existing': 0,
                'required_folders': {},
                'existing_required': [],
                'missing_folders': [],
                'needs_creation': False
            }
    
    def _setup_jobs(self):
        """Setup scheduler jobs based on current mode"""
        try:
            if self.mode == ProcessingMode.STARTUP:
                # Startup mode: NO automatic jobs scheduled
                # Processing only happens via manual API calls ("Process Next 100" button)
                self.logger.info("Startup mode: Manual processing only - no automatic jobs scheduled")
                return  # Exit early, no jobs scheduled
            else:
                # Maintenance mode jobs - run immediately then at intervals
                self.scheduler.add_job(
                    func=self._process_inbox_maintenance,
                    trigger=IntervalTrigger(minutes=self.processing_intervals['inbox']),
                    id=f'inbox_maintenance_{self.account_config.email}',
                    replace_existing=True,
                    next_run_time=datetime.now()  # Run immediately
                )
                
                # Training folder jobs also run automatically in maintenance mode
                self._setup_folder_processing_jobs()
            
        except Exception as e:
            self.logger.error(f"Failed to setup jobs: {e}")
            raise
    
    def _setup_folder_processing_jobs(self):
        """Setup jobs for processing training folders"""
        # Get configured folder names
        if hasattr(self.account_config, 'folders') and self.account_config.folders:
            whitelist_folder = self.account_config.folders.get('whitelist', 'INBOX._whitelist')
            blacklist_folder = self.account_config.folders.get('blacklist', 'INBOX._blacklist')
            vendor_folder = self.account_config.folders.get('vendor', 'INBOX._vendor')
            junk_folder = self.account_config.folders.get('junk', 'INBOX.Junk')
            approved_ads_folder = self.account_config.folders.get('approved_ads', 'INBOX.Approved_Ads')
        else:
            # Fallback to hardcoded names
            whitelist_folder = 'INBOX._whitelist'
            blacklist_folder = 'INBOX._blacklist'
            vendor_folder = 'INBOX._vendor'
            junk_folder = 'INBOX.Junk'
            approved_ads_folder = 'INBOX.Approved_Ads'
        
        folders = [
            ('white', whitelist_folder, 'INBOX'),
            ('black', blacklist_folder, junk_folder), 
            ('vendor', vendor_folder, approved_ads_folder)
        ]
        
        for list_name, source_folder, dest_folder in folders:
            self.scheduler.add_job(
                func=lambda ln=list_name, sf=source_folder, df=dest_folder: self._process_training_folder(ln, sf, df),
                trigger=IntervalTrigger(minutes=self.processing_intervals['folders']),
                id=f'folder_{list_name}_{self.account_config.email}',
                replace_existing=True,
                next_run_time=datetime.now()  # Run immediately
            )
    
    def _process_inbox_startup(self):
        """Process inbox in startup mode with batch processing"""
        try:
            start_time = time.time()
            batch_size = 100  # Process 100 messages at a time in startup mode
            self.logger.info(f"Starting inbox processing for {self.account_config.email} (batch size: {batch_size})")
            
            # Execute rules first
            self._execute_rules()
            
            # Process inbox with startup logic and batch limit
            result = pi.process_inbox(self.account, limit=batch_size)
            self.logger.info(f"Process inbox result: {result}")
            
            # Update statistics
            processing_time = time.time() - start_time
            self._update_stats(result, processing_time)
            
            self.consecutive_errors = 0
            self.logger.info(f"Startup inbox processing completed in {processing_time:.2f}s (processed {result.get('mail_list count', 0)} messages)")
            
        except Exception as e:
            self._handle_processing_error(e, "startup inbox processing")
    
    def process_manual_batch(self) -> Dict[str, Any]:
        """
        Manual processing for startup mode - combines all processing types
        This method is called by the dashboard "Process Next 100" button
        
        Returns:
            dict: Comprehensive processing results
        """
        if self.state != ServiceState.RUNNING_STARTUP:
            raise ValueError("Manual batch processing only available in startup mode")
            
        try:
            start_time = time.time()
            batch_size = 100
            
            self.logger.info(f"Starting manual batch processing for {self.account_config.email} (batch size: {batch_size})")
            
            # Step 1: Execute user-created rules first
            self.logger.info("Executing user-created rules...")
            try:
                self._execute_rules()
            except Exception as e:
                self.logger.warning(f"Rule execution failed: {e}")
            
            # Step 2: Process training folders
            self.logger.info("Processing training folders...")
            training_results = self._process_all_training_folders()
            
            # Step 3: Process inbox with batch limit
            self.logger.info(f"Processing inbox (batch size: {batch_size})...")
            inbox_result = pi.process_inbox_batch(self.account, limit=batch_size)
            
            # Update statistics
            processing_time = time.time() - start_time
            self._update_stats(inbox_result, processing_time)
            
            # Reset error counter on successful processing
            self.consecutive_errors = 0
            
            # Combine results
            combined_result = {
                'success': True,
                'processing_time': processing_time,
                'inbox_result': inbox_result,
                'training_results': training_results,
                'batch_size': batch_size,
                'emails_processed': inbox_result.get('emails_processed', 0),
                'emails_pending': inbox_result.get('inbox_remaining', 0),
                'timestamp': datetime.now().isoformat()
            }
            
            self.logger.info(f"Manual batch processing completed in {processing_time:.2f}s")
            self.logger.info(f"Results: {combined_result['emails_processed']} processed, {combined_result['emails_pending']} pending")
            
            return combined_result
            
        except Exception as e:
            self._handle_processing_error(e, "manual batch processing")
            return {
                'success': False,
                'error': str(e),
                'processing_time': 0,
                'emails_processed': 0,
                'emails_pending': 0,
                'timestamp': datetime.now().isoformat()
            }
    
    def _process_all_training_folders(self) -> Dict[str, Any]:
        """Process all training folders and return results"""
        results = {}
        
        # Get configured folder names
        if hasattr(self.account_config, 'folders') and self.account_config.folders:
            whitelist_folder = self.account_config.folders.get('whitelist', 'INBOX._whitelist')
            blacklist_folder = self.account_config.folders.get('blacklist', 'INBOX._blacklist')
            vendor_folder = self.account_config.folders.get('vendor', 'INBOX._vendor')
            junk_folder = self.account_config.folders.get('junk', 'INBOX.Junk')
            approved_ads_folder = self.account_config.folders.get('approved_ads', 'INBOX.Approved_Ads')
        else:
            # Fallback to hardcoded names
            whitelist_folder = 'INBOX._whitelist'
            blacklist_folder = 'INBOX._blacklist'
            vendor_folder = 'INBOX._vendor'
            junk_folder = 'INBOX.Junk'
            approved_ads_folder = 'INBOX.Approved_Ads'
            
        # Process each training folder
        training_folders = [
            ('white', whitelist_folder, self.account_config.folders.get('processed', 'INBOX.Processed')),
            ('black', blacklist_folder, junk_folder),
            ('vendor', vendor_folder, approved_ads_folder)
        ]
        
        for list_name, source_folder, dest_folder in training_folders:
            try:
                self.logger.debug(f"Processing training folder: {source_folder} -> {dest_folder}")
                self._process_training_folder(list_name, source_folder, dest_folder)
                results[list_name] = {'success': True, 'source': source_folder, 'dest': dest_folder}
            except Exception as e:
                self.logger.error(f"Failed to process training folder {source_folder}: {e}")
                results[list_name] = {'success': False, 'error': str(e), 'source': source_folder, 'dest': dest_folder}
                
        return results
    
    def _process_inbox_maintenance(self):
        """Process inbox in maintenance mode with batch processing"""
        try:
            start_time = time.time()
            batch_size = 200  # Process 200 messages at a time in maintenance mode
            
            # Execute rules first
            self._execute_rules()
            
            # Process inbox with maintenance logic and batch limit
            result = pi.process_inbox_maint(self.account, limit=batch_size)
            
            # Update statistics
            processing_time = time.time() - start_time
            self._update_stats(result, processing_time)
            
            self.consecutive_errors = 0
            self.logger.debug(f"Maintenance inbox processing completed in {processing_time:.2f}s (processed {result.get('mail_list count', 0)} messages)")
            
        except Exception as e:
            self._handle_processing_error(e, "maintenance inbox processing")
    
    def _process_training_folder(self, list_name: str, source_folder: str, dest_folder: str):
        """Process training folder"""
        try:
            self.logger.info(f"Processing training folder {source_folder} -> {dest_folder} for list {list_name}")
            list_file_path = self.config.get_list_file_path(list_name)
            result = pf.process_folder(list_file_path, self.account, source_folder, dest_folder)
            self.logger.info(f"Training folder processing result: {result}")
            
        except Exception as e:
            self.logger.error(f"Failed to process training folder {source_folder}: {e}")
    
    def _execute_rules(self):
        """Execute rules from the rules engine"""
        try:
            # Load and execute active rules for this account
            active_rules = r.load_active_rules_for_account(self.account_config.email)
            for rule in active_rules:
                rule.process_emails(self.account)
                
        except Exception as e:
            self.logger.error(f"Failed to execute rules: {e}")
    
    def _update_stats(self, result: Dict[str, Any], processing_time: float):
        """Update processing statistics"""
        with self._lock:
            self.stats.last_run = datetime.now()
            
            # Update processing time average
            if self.stats.avg_processing_time == 0:
                self.stats.avg_processing_time = processing_time
            else:
                self.stats.avg_processing_time = (self.stats.avg_processing_time + processing_time) / 2
            
            # Update email counts from result (handle both old and new result formats)
            if 'emails_processed' in result:
                # New format from process_inbox_batch
                self.stats.emails_processed += result['emails_processed']
            elif 'mail_list count' in result:
                # Old format from process_inbox
                self.stats.emails_processed += result['mail_list count']
                
            if 'inbox_remaining' in result:
                # New format from process_inbox_batch
                self.stats.emails_pending = result['inbox_remaining']
            elif 'uids in pending' in result:
                # Old format from process_inbox
                self.stats.emails_pending = len(result['uids in pending'])
    
    def _handle_processing_error(self, error: Exception, operation: str):
        """Handle processing errors with consecutive error tracking"""
        self.consecutive_errors += 1
        self.stats.error_count += 1
        self.last_error = str(error)
        
        self.logger.error(f"Error in {operation}: {error}")
        
        if self.consecutive_errors >= self.max_consecutive_errors:
            self.logger.critical(f"Too many consecutive errors ({self.consecutive_errors}), stopping service")
            self.state = ServiceState.ERROR
            self.stop()
    
    def should_transition_to_maintenance(self) -> bool:
        """
        Check if service should transition from startup to maintenance mode
        
        Returns:
            bool: True if should transition, False otherwise
        """
        if self.mode != ProcessingMode.STARTUP:
            return False
            
        # Check criteria for transition
        criteria_met = (
            self.stats.emails_pending < 50 and  # Less than 50 pending emails
            self.stats.mode_start_time and 
            (datetime.now() - self.stats.mode_start_time).days >= 14 and  # Running for 2+ weeks
            self.consecutive_errors == 0 and  # No recent errors
            self.stats.error_count / max(1, self.stats.emails_processed) < 0.05  # Error rate < 5%
        )
        
        return criteria_met