"""
Retention Scheduler Service

Background service for automated retention policy execution.
Runs separately from email processing to avoid performance impact.
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path

from .manager import RetentionPolicyManager
from .models import RetentionStage, RetentionResult
from .exceptions import RetentionError


class RetentionScheduler:
    """Background service for scheduled retention operations"""
    
    def __init__(self, 
                 retention_manager: RetentionPolicyManager,
                 check_interval_hours: int = 24,
                 execution_hour: int = 2):
        """
        Initialize retention scheduler
        
        Args:
            retention_manager: RetentionPolicyManager instance
            check_interval_hours: Hours between retention checks
            execution_hour: Hour of day to run retention (0-23)
        """
        self.retention_manager = retention_manager
        self.check_interval_hours = check_interval_hours
        self.execution_hour = execution_hour
        
        self.logger = logging.getLogger(__name__)
        self.scheduler_thread = None
        self.running = False
        self.last_execution = None
        
        # Statistics
        self.stats = {
            'total_executions': 0,
            'successful_executions': 0,
            'failed_executions': 0,
            'last_execution_time': None,
            'last_execution_duration': None,
            'emails_processed': 0,
            'emails_moved_to_trash': 0,
            'emails_permanently_deleted': 0
        }
    
    def start_scheduler(self) -> bool:
        """
        Start background retention scheduler
        
        Returns:
            bool: True if started successfully
        """
        if self.running:
            self.logger.warning("Retention scheduler is already running")
            return False
        
        try:
            self.running = True
            self.scheduler_thread = threading.Thread(
                target=self._scheduler_loop,
                daemon=True,
                name="RetentionScheduler"
            )
            self.scheduler_thread.start()
            
            self.logger.info(f"Retention scheduler started (interval: {self.check_interval_hours}h, execution hour: {self.execution_hour})")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start retention scheduler: {e}")
            self.running = False
            return False
    
    def stop_scheduler(self) -> bool:
        """
        Stop background retention scheduler
        
        Returns:
            bool: True if stopped successfully
        """
        if not self.running:
            self.logger.warning("Retention scheduler is not running")
            return False
        
        try:
            self.running = False
            
            if self.scheduler_thread and self.scheduler_thread.is_alive():
                self.scheduler_thread.join(timeout=10)
                
                if self.scheduler_thread.is_alive():
                    self.logger.warning("Retention scheduler thread did not stop within timeout")
                    return False
            
            self.logger.info("Retention scheduler stopped")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to stop retention scheduler: {e}")
            return False
    
    def _scheduler_loop(self):
        """Main scheduler loop - runs in background thread"""
        self.logger.info("Retention scheduler loop started")
        
        while self.running:
            try:
                # Check if it's time to run retention
                if self._should_run_retention():
                    self.logger.info("Starting scheduled retention execution")
                    self._execute_scheduled_retention()
                
                # Sleep for check interval or until stop requested
                self._sleep_with_interruption(self.check_interval_hours * 3600)
                
            except Exception as e:
                self.logger.error(f"Error in retention scheduler loop: {e}")
                # Sleep shorter interval on error to avoid tight loop
                self._sleep_with_interruption(300)  # 5 minutes
    
    def _should_run_retention(self) -> bool:
        """Determine if retention should run now"""
        now = datetime.now()
        
        # Check if we're at the right hour
        if now.hour != self.execution_hour:
            return False
        
        # Check if we already ran today
        if self.last_execution:
            # If last execution was today, don't run again
            if self.last_execution.date() == now.date():
                return False
        
        return True
    
    def _sleep_with_interruption(self, seconds: int):
        """Sleep for specified seconds but check for stop signal"""
        end_time = time.time() + seconds
        
        while time.time() < end_time and self.running:
            time.sleep(min(60, end_time - time.time()))  # Check every minute
    
    def _execute_scheduled_retention(self):
        """Execute retention policies for all accounts"""
        execution_start = time.time()
        self.stats['total_executions'] += 1
        
        try:
            # Get accounts from config
            accounts = self._get_configured_accounts()
            
            if not accounts:
                self.logger.warning("No accounts configured for retention processing")
                return
            
            self.logger.info(f"Running retention for {len(accounts)} accounts")
            
            total_results = []
            
            # Process each account
            for account in accounts:
                try:
                    self.logger.info(f"Processing retention for {account.email}")
                    
                    # Execute retention policies
                    results = self.retention_manager.execute_policies_for_account(account)
                    total_results.extend(results)
                    
                    # Update statistics
                    for result in results:
                        if result.success:
                            self.stats['emails_processed'] += result.emails_processed
                            
                            if result.stage == RetentionStage.MOVE_TO_TRASH:
                                self.stats['emails_moved_to_trash'] += result.emails_affected
                            elif result.stage == RetentionStage.PERMANENT_DELETE:
                                self.stats['emails_permanently_deleted'] += result.emails_affected
                    
                    self.logger.info(f"Completed retention for {account.email}")
                    
                except Exception as e:
                    self.logger.error(f"Failed to process retention for {account.email}: {e}")
            
            # Mark execution as successful
            self.stats['successful_executions'] += 1
            self.last_execution = datetime.now()
            
            # Log summary
            self._log_execution_summary(total_results, execution_start)
            
        except Exception as e:
            self.logger.error(f"Scheduled retention execution failed: {e}")
            self.stats['failed_executions'] += 1
        
        finally:
            self.stats['last_execution_time'] = datetime.now().isoformat()
            self.stats['last_execution_duration'] = time.time() - execution_start
    
    def _get_configured_accounts(self) -> List[Any]:
        """Get configured accounts for retention processing"""
        try:
            # Import config to get accounts
            from config import get_config
            config = get_config()
            
            # Filter accounts that should have retention applied
            retention_accounts = []
            for account in config.accounts:
                # Skip environment-based accounts if they're temporary
                if account.name == 'env_account':
                    continue
                retention_accounts.append(account)
            
            return retention_accounts
            
        except Exception as e:
            self.logger.error(f"Failed to get configured accounts: {e}")
            return []
    
    def _log_execution_summary(self, results: List[RetentionResult], start_time: float):
        """Log summary of retention execution"""
        duration = time.time() - start_time
        
        # Aggregate results
        total_processed = sum(r.emails_processed for r in results)
        total_affected = sum(r.emails_affected for r in results)
        successful_operations = len([r for r in results if r.success])
        failed_operations = len([r for r in results if not r.success])
        
        stage_1_results = [r for r in results if r.stage == RetentionStage.MOVE_TO_TRASH]
        stage_2_results = [r for r in results if r.stage == RetentionStage.PERMANENT_DELETE]
        
        emails_to_trash = sum(r.emails_affected for r in stage_1_results if r.success)
        emails_deleted = sum(r.emails_affected for r in stage_2_results if r.success)
        
        summary = {
            'execution_duration': f"{duration:.2f} seconds",
            'total_operations': len(results),
            'successful_operations': successful_operations,
            'failed_operations': failed_operations,
            'emails_processed': total_processed,
            'emails_moved_to_trash': emails_to_trash,
            'emails_permanently_deleted': emails_deleted,
            'total_emails_affected': total_affected
        }
        
        self.logger.info(f"Retention execution completed: {summary}")
        
        # Log to audit as well
        self.retention_manager.audit_logger.logger.info(
            f"SCHEDULED_EXECUTION_SUMMARY: {summary}"
        )
    
    def run_manual_retention(self, 
                           account_email: str = None,
                           policy_id: str = None,
                           stage: RetentionStage = None,
                           dry_run: bool = False) -> List[RetentionResult]:
        """
        Manually trigger retention execution
        
        Args:
            account_email: Optional specific account to process
            policy_id: Optional specific policy to execute
            stage: Optional specific stage to execute
            dry_run: If True, only simulate operations
            
        Returns:
            List of RetentionResult objects
        """
        self.logger.info(f"Manual retention execution requested (account: {account_email}, policy: {policy_id}, dry_run: {dry_run})")
        
        results = []
        
        try:
            accounts = self._get_configured_accounts()
            
            # Filter to specific account if requested
            if account_email:
                accounts = [acc for acc in accounts if acc.email == account_email]
                if not accounts:
                    raise RetentionError(f"Account {account_email} not found")
            
            # Execute for selected accounts
            for account in accounts:
                if policy_id:
                    # Execute specific policy
                    policy = self.retention_manager.settings.get_policy_by_id(policy_id)
                    if not policy:
                        raise RetentionError(f"Policy {policy_id} not found")
                    
                    if stage == RetentionStage.MOVE_TO_TRASH or stage is None:
                        result = self.retention_manager.execute_retention_stage_1(
                            account, policy, dry_run=dry_run
                        )
                        results.append(result)
                    
                    if stage == RetentionStage.PERMANENT_DELETE or stage is None:
                        trash_retention = policy.trash_retention_days
                        result = self.retention_manager.execute_retention_stage_2(
                            account, trash_retention, dry_run=dry_run
                        )
                        results.append(result)
                else:
                    # Execute all policies
                    account_results = self.retention_manager.execute_policies_for_account(
                        account, stage, dry_run=dry_run
                    )
                    results.extend(account_results)
            
            self.logger.info(f"Manual retention execution completed: {len(results)} operations")
            return results
            
        except Exception as e:
            self.logger.error(f"Manual retention execution failed: {e}")
            raise RetentionError(f"Manual execution failed: {e}")
    
    def get_scheduler_status(self) -> Dict[str, Any]:
        """Get current scheduler status and statistics"""
        status = {
            'running': self.running,
            'check_interval_hours': self.check_interval_hours,
            'execution_hour': self.execution_hour,
            'last_execution': self.last_execution.isoformat() if self.last_execution else None,
            'next_execution_estimate': self._estimate_next_execution(),
            'thread_alive': self.scheduler_thread.is_alive() if self.scheduler_thread else False,
            'statistics': self.stats.copy()
        }
        
        return status
    
    def _estimate_next_execution(self) -> Optional[str]:
        """Estimate when next retention execution will occur"""
        if not self.running:
            return None
        
        now = datetime.now()
        
        # Calculate next execution time
        next_execution = now.replace(
            hour=self.execution_hour, 
            minute=0, 
            second=0, 
            microsecond=0
        )
        
        # If we've passed today's execution time, schedule for tomorrow
        if now.hour >= self.execution_hour:
            next_execution += timedelta(days=1)
        
        return next_execution.isoformat()
    
    def generate_retention_report(self, 
                                 days_back: int = 30) -> Dict[str, Any]:
        """
        Generate comprehensive retention activity report
        
        Args:
            days_back: Number of days to include in report
            
        Returns:
            Dictionary with retention statistics and summaries
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        # Get audit report from audit logger
        audit_report = self.retention_manager.audit_logger.generate_retention_report(
            start_date, end_date
        )
        
        # Add scheduler-specific information
        report = {
            'report_period': audit_report['report_period'],
            'scheduler_info': {
                'running': self.running,
                'total_scheduled_executions': self.stats['total_executions'],
                'successful_executions': self.stats['successful_executions'],
                'failed_executions': self.stats['failed_executions'],
                'last_execution': self.stats['last_execution_time'],
                'next_execution_estimate': self._estimate_next_execution()
            },
            'retention_summary': audit_report['summary'],
            'by_stage': audit_report['by_stage'],
            'by_policy': audit_report['by_policy'],
            'errors': audit_report['errors']
        }
        
        return report
    
    def update_schedule(self, 
                       check_interval_hours: int = None,
                       execution_hour: int = None) -> bool:
        """
        Update scheduler configuration
        
        Args:
            check_interval_hours: New check interval
            execution_hour: New execution hour (0-23)
            
        Returns:
            bool: True if updated successfully
        """
        try:
            if check_interval_hours is not None:
                if check_interval_hours < 1:
                    raise ValueError("Check interval must be at least 1 hour")
                self.check_interval_hours = check_interval_hours
            
            if execution_hour is not None:
                if not 0 <= execution_hour <= 23:
                    raise ValueError("Execution hour must be between 0 and 23")
                self.execution_hour = execution_hour
            
            self.logger.info(f"Scheduler configuration updated (interval: {self.check_interval_hours}h, hour: {self.execution_hour})")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update scheduler configuration: {e}")
            return False