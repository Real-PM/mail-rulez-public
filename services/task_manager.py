"""
Task Manager

Background task orchestration for managing multiple email processors.
Provides centralized control, monitoring, and coordination of email
processing services across multiple accounts.
"""

import logging
import threading
import time
from typing import Dict, List, Optional, Any
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, Future
import json

from .email_processor import EmailProcessor, ServiceState, ProcessingMode
from config import get_config, AccountConfig


class TaskManager:
    """
    Centralized task manager for email processing services
    
    Manages multiple EmailProcessor instances, provides unified control,
    and handles resource coordination across accounts.
    """
    
    def __init__(self, max_workers: int = 4):
        """
        Initialize task manager
        
        Args:
            max_workers: Maximum number of concurrent processing threads
        """
        self.processors: Dict[str, EmailProcessor] = {}
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.Lock()
        self._initialized = False  # Track initialization state
        
        # Configuration
        self.config = get_config()
        self.logger = logging.getLogger('task_manager')
        
        # Monitoring
        self.startup_time = datetime.now()
        self.task_history: List[Dict[str, Any]] = []
        self.max_history_size = 1000
        
        # Auto-transition monitoring
        self.transition_check_interval = 3600  # Check every hour
        self.last_transition_check = datetime.now()
        
        self.logger.info("Task manager initialized")
    
    def add_account(self, account_config: AccountConfig) -> bool:
        """
        Add an account for processing
        
        Args:
            account_config: Account configuration
            
        Returns:
            bool: True if added successfully, False otherwise
        """
        with self._lock:
            email = account_config.email
            
            if email in self.processors:
                self.logger.warning(f"Account {email} already exists")
                return False
            
            try:
                processor = EmailProcessor(account_config)
                self.processors[email] = processor
                
                self.logger.info(f"Added account {email} for processing")
                self._log_task("account_added", {"account": email})
                return True
                
            except Exception as e:
                self.logger.error(f"Failed to add account {email}: {e}")
                return False
    
    def remove_account(self, account_email: str) -> bool:
        """
        Remove an account from processing
        
        Args:
            account_email: Email address of account to remove
            
        Returns:
            bool: True if removed successfully, False otherwise
        """
        with self._lock:
            if account_email not in self.processors:
                self.logger.warning(f"Account {account_email} not found")
                return False
            
            try:
                processor = self.processors[account_email]
                
                # Stop processor if running
                if processor.state != ServiceState.STOPPED:
                    processor.stop()
                
                # Remove from processors
                del self.processors[account_email]
                
                self.logger.info(f"Removed account {account_email}")
                self._log_task("account_removed", {"account": account_email})
                return True
                
            except Exception as e:
                self.logger.error(f"Failed to remove account {account_email}: {e}")
                return False
    
    def start_account(self, account_email: str, mode: ProcessingMode = ProcessingMode.STARTUP) -> bool:
        """
        Start processing for an account
        
        Args:
            account_email: Email address of account
            mode: Processing mode to start in
            
        Returns:
            bool: True if started successfully, False otherwise
        """
        processor = self._get_processor(account_email)
        if not processor:
            return False
        
        try:
            result = processor.start(mode)
            if result:
                self._log_task("service_started", {
                    "account": account_email,
                    "mode": mode.value
                })
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to start account {account_email}: {e}")
            return False
    
    def stop_account(self, account_email: str) -> bool:
        """
        Stop processing for an account
        
        Args:
            account_email: Email address of account
            
        Returns:
            bool: True if stopped successfully, False otherwise
        """
        processor = self._get_processor(account_email)
        if not processor:
            return False
        
        try:
            result = processor.stop()
            if result:
                self._log_task("service_stopped", {"account": account_email})
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to stop account {account_email}: {e}")
            return False
    
    def restart_account(self, account_email: str) -> bool:
        """
        Restart processing for an account
        
        Args:
            account_email: Email address of account
            
        Returns:
            bool: True if restarted successfully, False otherwise
        """
        processor = self._get_processor(account_email)
        if not processor:
            return False
        
        try:
            result = processor.restart()
            if result:
                self._log_task("service_restarted", {"account": account_email})
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to restart account {account_email}: {e}")
            return False
    
    def switch_mode(self, account_email: str, new_mode: ProcessingMode) -> bool:
        """
        Switch processing mode for an account
        
        Args:
            account_email: Email address of account
            new_mode: New processing mode
            
        Returns:
            bool: True if switched successfully, False otherwise
        """
        processor = self._get_processor(account_email)
        if not processor:
            return False
        
        try:
            result = processor.switch_mode(new_mode)
            if result:
                self._log_task("mode_switched", {
                    "account": account_email,
                    "new_mode": new_mode.value
                })
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to switch mode for account {account_email}: {e}")
            return False
    
    def get_account_status(self, account_email: str) -> Optional[Dict[str, Any]]:
        """
        Get status for a specific account
        
        Args:
            account_email: Email address of account
            
        Returns:
            dict: Account status or None if not found
        """
        processor = self._get_processor(account_email)
        if not processor:
            return None
        
        return processor.get_status()
    
    def get_all_status(self) -> Dict[str, Any]:
        """
        Get status for all accounts and task manager
        
        Returns:
            dict: Complete system status
        """
        with self._lock:
            accounts_status = {}
            
            for email, processor in self.processors.items():
                accounts_status[email] = processor.get_status()
            
            # Check for auto-transitions
            self._check_auto_transitions()
            
            return {
                'task_manager': {
                    'startup_time': self.startup_time.isoformat(),
                    'total_accounts': len(self.processors),
                    'running_accounts': len([p for p in self.processors.values() 
                                           if p.state in [ServiceState.RUNNING_STARTUP, ServiceState.RUNNING_MAINTENANCE]]),
                    'error_accounts': len([p for p in self.processors.values() 
                                         if p.state == ServiceState.ERROR]),
                    'last_transition_check': self.last_transition_check.isoformat()
                },
                'accounts': accounts_status
            }
    
    def get_aggregate_stats(self) -> Dict[str, Any]:
        """
        Get aggregated statistics across all accounts
        
        Returns:
            dict: Aggregated statistics
        """
        # Return minimal stats if not yet initialized, but still show account count
        if not self._initialized:
            self.logger.debug("Stats requested before initialization complete, returning minimal stats")
            return {
                'total_accounts': len(self.processors),  # Show actual account count even during init
                'running_accounts': 0,  # Conservative - no running accounts during init
                'startup_mode_accounts': 0,
                'maintenance_mode_accounts': 0,
                'total_emails_processed': 0,
                'total_emails_pending': 0, 
                'total_errors': 0,
                'avg_processing_time': 0.0,
                'error_rate': 0.0
            }
            
        with self._lock:
            # Create atomic snapshots of all processor stats
            processor_snapshots = {}
            for email, processor in self.processors.items():
                try:
                    processor_snapshots[email] = processor.get_stats_snapshot()
                except Exception as e:
                    self.logger.warning(f"Failed to get stats snapshot for {email}: {e}")
                    # Skip this processor if snapshot fails
                    continue
            
            # Calculate aggregates from snapshots (immune to concurrent changes)
            total_processed = 0
            total_pending = 0
            total_errors = 0
            avg_processing_times = []
            
            running_count = 0
            startup_count = 0
            maintenance_count = 0
            
            for snapshot in processor_snapshots.values():
                total_processed += snapshot.get('emails_processed', 0)
                total_pending += snapshot.get('emails_pending', 0)
                total_errors += snapshot.get('error_count', 0)
                
                avg_time = snapshot.get('avg_processing_time', 0)
                if avg_time > 0:
                    avg_processing_times.append(avg_time)
                
                # Count by state and mode from snapshot
                state = snapshot.get('state', '')
                mode = snapshot.get('mode', '')
                
                if state in ['RUNNING_STARTUP', 'RUNNING_MAINTENANCE']:
                    running_count += 1
                    
                if mode == 'STARTUP':
                    startup_count += 1
                else:
                    maintenance_count += 1
            
            return {
                'total_accounts': len(self.processors),
                'running_accounts': running_count,
                'startup_mode_accounts': startup_count,
                'maintenance_mode_accounts': maintenance_count,
                'total_emails_processed': total_processed,
                'total_emails_pending': total_pending,
                'total_errors': total_errors,
                'avg_processing_time': sum(avg_processing_times) / len(avg_processing_times) if avg_processing_times else 0,
                'error_rate': total_errors / max(1, total_processed)
            }
    
    def start_all(self) -> Dict[str, bool]:
        """
        Start processing for all accounts
        
        Returns:
            dict: Results for each account
        """
        results = {}
        
        for email in list(self.processors.keys()):
            results[email] = self.start_account(email)
        
        self.logger.info(f"Started all accounts: {sum(results.values())}/{len(results)} successful")
        return results
    
    def stop_all(self) -> Dict[str, bool]:
        """
        Stop processing for all accounts
        
        Returns:
            dict: Results for each account
        """
        results = {}
        
        for email in list(self.processors.keys()):
            results[email] = self.stop_account(email)
        
        self.logger.info(f"Stopped all accounts: {sum(results.values())}/{len(results)} successful")
        return results
    
    def shutdown(self):
        """Shutdown task manager and all processors"""
        self.logger.info("Shutting down task manager")
        
        # Stop all processors
        self.stop_all()
        
        # Shutdown executor
        self.executor.shutdown(wait=True)
        
        self.logger.info("Task manager shutdown complete")
    
    def _get_processor(self, account_email: str) -> Optional[EmailProcessor]:
        """Get processor for account, with auto-recovery if missing"""
        processor = self.processors.get(account_email)
        if not processor:
            # Auto-recovery: try to reload account from config
            self.logger.warning(f"Account {account_email} not found in registry, attempting recovery")
            try:
                self.refresh_accounts_from_config()
                processor = self.processors.get(account_email)
                if processor:
                    self.logger.info(f"Successfully recovered account {account_email}")
                else:
                    self.logger.error(f"Account {account_email} recovery failed - not in configuration")
            except Exception as e:
                self.logger.error(f"Account {account_email} recovery error: {e}")
        return processor
    
    def _log_task(self, task_type: str, details: Dict[str, Any]):
        """Log task activity for monitoring"""
        task_entry = {
            'timestamp': datetime.now().isoformat(),
            'type': task_type,
            'details': details
        }
        
        self.task_history.append(task_entry)
        
        # Trim history if too large
        if len(self.task_history) > self.max_history_size:
            self.task_history = self.task_history[-self.max_history_size:]
    
    def _check_auto_transitions(self):
        """Check for accounts ready for auto-transition to maintenance mode"""
        now = datetime.now()
        
        # Only check periodically
        if (now - self.last_transition_check).seconds < self.transition_check_interval:
            return
        
        self.last_transition_check = now
        
        for email, processor in self.processors.items():
            if processor.should_transition_to_maintenance():
                self.logger.info(f"Auto-transitioning {email} to maintenance mode")
                if self.switch_mode(email, ProcessingMode.MAINTENANCE):
                    self._log_task("auto_transition", {
                        "account": email,
                        "from_mode": "startup",
                        "to_mode": "maintenance"
                    })
    
    def load_accounts_from_config(self):
        """Load all accounts from configuration (always reload from file)"""
        try:
            # Force reload of config from file to get latest saved accounts
            from config import Config
            self.logger.info(f"Reloading config from file: {self.config.base_dir}/{self.config.config_file}")
            fresh_config = Config(self.config.base_dir, self.config.config_file, self.config.use_encryption)
            self.config = fresh_config
            
            self.logger.info(f"Config reloaded, found {len(self.config.accounts)} accounts in file")
            
            for account_config in self.config.accounts:
                self.add_account(account_config)
            
            self.logger.info(f"Loaded {len(self.config.accounts)} accounts from configuration")
            self._initialized = True  # Mark as fully initialized
            
        except Exception as e:
            self.logger.error(f"Failed to load accounts from config: {e}")
            self._initialized = True  # Still mark as initialized even on error
    
    def refresh_accounts_from_config(self):
        """Refresh accounts from current configuration (reload config and sync accounts)"""
        try:
            # Force reload of config by creating a new instance
            from config import Config
            self.logger.info(f"Refreshing config from file: {self.config.base_dir}/{self.config.config_file}")
            fresh_config = Config(self.config.base_dir, self.config.config_file, self.config.use_encryption)
            
            # Update our config reference
            self.config = fresh_config
            self.logger.info(f"Config refreshed, found {len(self.config.accounts)} accounts in file")
            
            # Get current account emails
            current_emails = set(self.processors.keys())
            config_emails = set(account.email for account in self.config.accounts)
            
            self.logger.info(f"Current accounts in task manager: {current_emails}")
            self.logger.info(f"Accounts in config: {config_emails}")
            
            # Remove accounts no longer in config
            to_remove = current_emails - config_emails
            for email in to_remove:
                self.remove_account(email)
                self.logger.info(f"Removed account {email} (no longer in config)")
            
            # Add new accounts from config
            to_add = config_emails - current_emails
            for account_config in self.config.accounts:
                if account_config.email in to_add:
                    self.add_account(account_config)
                    self.logger.info(f"Added account {account_config.email} from config")
            
            self.logger.info(f"Refreshed accounts: {len(to_add)} added, {len(to_remove)} removed, total now: {len(self.processors)}")
            
        except Exception as e:
            self.logger.error(f"Failed to refresh accounts from config: {e}")
    
    def get_task_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent task history
        
        Args:
            limit: Maximum number of entries to return
            
        Returns:
            list: Recent task history entries
        """
        with self._lock:
            return self.task_history[-limit:] if self.task_history else []


# Global task manager instance
_task_manager: Optional[TaskManager] = None
_task_manager_lock = threading.Lock()


def get_task_manager() -> TaskManager:
    """
    Get global task manager instance (singleton)
    
    Returns:
        TaskManager: Global task manager instance
    """
    global _task_manager
    
    with _task_manager_lock:
        if _task_manager is None:
            _task_manager = TaskManager()
            # Load accounts from configuration
            _task_manager.load_accounts_from_config()
        
        return _task_manager


def shutdown_task_manager():
    """Shutdown global task manager"""
    global _task_manager
    
    with _task_manager_lock:
        if _task_manager is not None:
            _task_manager.shutdown()
            _task_manager = None