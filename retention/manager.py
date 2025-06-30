"""
Mail-Rulez - Intelligent Email Management System
Copyright (c) 2024 Real Project Management Solutions

This software is dual-licensed:
1. AGPL v3 for open source/self-hosted use
2. Commercial license for hosted services and enterprise use

For commercial licensing, contact: license@mail-rulez.com
See LICENSE-DUAL for complete licensing information.
"""


"""
Retention Policy Manager

Core service for managing and executing retention policies.
Handles policy CRUD operations, evaluation, and two-stage execution.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any

from .models import (
    RetentionPolicy, 
    RetentionSettings, 
    RetentionStage, 
    RetentionResult,
    TrashItem,
    migrate_legacy_retention_settings
)
from .exceptions import (
    RetentionError,
    PolicyNotFoundError,
    TrashOperationError,
    InvalidRetentionPeriodError,
    PolicyValidationError,
    RetentionExecutionError
)
from .audit import RetentionAuditLogger
from .trash_manager import TrashManager


class RetentionPolicyManager:
    """Manages all retention policies and two-stage execution"""
    
    def __init__(self, config_dir: Path):
        self.config_dir = Path(config_dir)
        self.policies_file = self.config_dir / "retention_policies.json"
        self.audit_log_file = self.config_dir / "retention_audit.log"
        
        # Initialize components
        self.audit_logger = RetentionAuditLogger(self.audit_log_file)
        self.trash_manager = TrashManager(self.audit_logger)
        self.logger = logging.getLogger(__name__)
        
        # Load or create retention settings
        self.settings = RetentionSettings()
        self.load_policies()
        
        # Ensure config directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def load_policies(self) -> bool:
        """
        Load retention policies from file
        
        Returns:
            bool: True if policies loaded successfully
        """
        try:
            if not self.policies_file.exists():
                self.logger.info("No retention policies file found, using defaults")
                self._create_default_policies()
                return True
            
            with open(self.policies_file, 'r') as f:
                data = json.load(f)
            
            self.settings = RetentionSettings.from_dict(data)
            self.logger.info(f"Loaded {len(self.settings.get_all_policies())} retention policies")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load retention policies: {e}")
            # Fall back to defaults
            self._create_default_policies()
            return False
    
    def save_policies(self) -> bool:
        """
        Save retention policies to file using atomic write
        
        Returns:
            bool: True if saved successfully
        """
        import tempfile
        import os
        
        try:
            # Use atomic write to prevent corruption
            temp_file = None
            temp_fd, temp_file = tempfile.mkstemp(
                suffix='.tmp',
                prefix='retention_',
                dir=self.config_dir
            )
            
            with os.fdopen(temp_fd, 'w') as f:
                json.dump(self.settings.to_dict(), f, indent=2)
            
            # Atomic rename
            os.rename(temp_file, self.policies_file)
            temp_file = None
            
            self.logger.info(f"Saved {len(self.settings.get_all_policies())} retention policies")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save retention policies: {e}")
            # Clean up temp file if something went wrong
            if temp_file and os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except:
                    pass
            return False
    
    def _create_default_policies(self):
        """Create default retention policies"""
        from .models import create_default_folder_policies
        
        defaults = create_default_folder_policies()
        for policy in defaults.values():
            self.settings.add_policy(policy)
        
        self.logger.info("Created default retention policies")
    
    def migrate_from_legacy_config(self, legacy_retention_settings: Dict[str, int]):
        """
        Migrate from legacy retention_settings format
        
        Args:
            legacy_retention_settings: Dict like {'approved_ads': 30, 'junk': 7}
        """
        try:
            migrated_settings = migrate_legacy_retention_settings(legacy_retention_settings)
            
            # Merge with existing settings (legacy takes precedence for conflicts)
            for policy in migrated_settings.get_all_policies():
                existing = self.settings.get_policy_by_id(policy.id)
                if existing:
                    self.logger.info(f"Updating existing policy {policy.id} with legacy values")
                else:
                    self.logger.info(f"Creating new policy {policy.id} from legacy settings")
                
                self.settings.add_policy(policy)
            
            # Save the migrated settings
            self.save_policies()
            
            self.logger.info(f"Successfully migrated {len(legacy_retention_settings)} legacy retention settings")
            
        except Exception as e:
            self.logger.error(f"Failed to migrate legacy retention settings: {e}")
            raise RetentionError(f"Legacy migration failed: {e}")
    
    def create_folder_policy(self, 
                           folder_pattern: str, 
                           retention_days: int, 
                           name: str = None,
                           description: str = None,
                           trash_retention_days: int = 7,
                           **kwargs) -> RetentionPolicy:
        """Create a new folder-level retention policy"""
        
        if retention_days < self.settings.global_settings.get("min_retention_days", 1):
            raise InvalidRetentionPeriodError(retention_days)
        
        policy_id = f"folder-{folder_pattern}-{int(time.time())}"
        
        policy = RetentionPolicy(
            id=policy_id,
            name=name or f"{folder_pattern.title()} Cleanup",
            description=description or f"Retention policy for {folder_pattern} folder",
            retention_days=retention_days,
            trash_retention_days=trash_retention_days,
            folder_pattern=folder_pattern,
            **kwargs
        )
        
        self.settings.add_policy(policy)
        self.save_policies()
        
        # Log policy creation
        self.audit_logger.log_policy_change('create', policy)
        
        self.logger.info(f"Created folder policy {policy_id} for {folder_pattern}")
        return policy
    
    def create_rule_policy(self, 
                          rule_id: str, 
                          retention_days: int,
                          name: str = None,
                          description: str = None,
                          trash_retention_days: int = 7,
                          **kwargs) -> RetentionPolicy:
        """Create a new rule-based retention policy"""
        
        if retention_days < self.settings.global_settings.get("min_retention_days", 1):
            raise InvalidRetentionPeriodError(retention_days)
        
        policy_id = f"rule-{rule_id}-{int(time.time())}"
        
        policy = RetentionPolicy(
            id=policy_id,
            name=name or f"Rule-based retention for {rule_id}",
            description=description or f"Retention policy for rule {rule_id}",
            retention_days=retention_days,
            trash_retention_days=trash_retention_days,
            rule_id=rule_id,
            **kwargs
        )
        
        self.settings.add_policy(policy)
        self.save_policies()
        
        # Log policy creation
        self.audit_logger.log_policy_change('create', policy)
        
        self.logger.info(f"Created rule policy {policy_id} for rule {rule_id}")
        return policy
    
    def update_policy(self, policy_id: str, **updates) -> bool:
        """Update an existing retention policy"""
        
        policy = self.settings.get_policy_by_id(policy_id)
        if not policy:
            raise PolicyNotFoundError(policy_id)
        
        # Keep copy of old policy for audit
        old_policy = RetentionPolicy.from_dict(policy.to_dict())
        
        # Apply updates
        for key, value in updates.items():
            if hasattr(policy, key):
                setattr(policy, key, value)
        
        # Validate updated policy
        if policy.retention_days < self.settings.global_settings.get("min_retention_days", 1):
            raise InvalidRetentionPeriodError(policy.retention_days)
        
        policy.update_timestamp()
        self.save_policies()
        
        # Log policy update
        self.audit_logger.log_policy_change('update', policy, old_policy)
        
        self.logger.info(f"Updated policy {policy_id}")
        return True
    
    def delete_policy(self, policy_id: str) -> bool:
        """Delete a retention policy"""
        
        policy = self.settings.get_policy_by_id(policy_id)
        if not policy:
            raise PolicyNotFoundError(policy_id)
        
        # Remove from settings
        removed = self.settings.remove_policy(policy_id)
        if removed:
            self.save_policies()
            
            # Log policy deletion
            self.audit_logger.log_policy_change('delete', policy)
            
            self.logger.info(f"Deleted policy {policy_id}")
        
        return removed
    
    def get_applicable_policies(self, folder: str, rule_id: str = None) -> List[RetentionPolicy]:
        """
        Get policies that apply to a specific folder and/or rule
        
        Args:
            folder: Folder name to check
            rule_id: Optional rule ID to check
            
        Returns:
            List of applicable active policies
        """
        applicable = []
        
        # Add folder-level policies
        folder_policies = self.settings.get_applicable_folder_policies(folder)
        applicable.extend([p for p in folder_policies if p.active])
        
        # Add rule-specific policy if provided
        if rule_id:
            rule_policy = None
            for policy in self.settings.rule_policies.values():
                if policy.rule_id == rule_id and policy.active:
                    rule_policy = policy
                    break
            
            if rule_policy:
                applicable.append(rule_policy)
        
        # Sort by priority (not implemented in models yet, use creation order)
        return applicable
    
    def find_emails_older_than(self, mailbox, folder: str, days: int) -> List[str]:
        """
        Find email UIDs older than specified days in a folder
        
        Args:
            mailbox: IMAP mailbox connection
            folder: Folder to search
            days: Age threshold in days
            
        Returns:
            List of message UIDs
        """
        try:
            # Set folder
            mailbox.folder.set(folder)
            
            # Import fetch function
            import functions as pf
            emails = pf.fetch_class(mailbox, folder=folder)
            
            # Find old emails
            cutoff_date = datetime.now() - timedelta(days=days)
            old_uids = []
            
            for email in emails:
                email_date = email.date if hasattr(email, 'date') else datetime.now()
                if email_date < cutoff_date:
                    old_uids.append(email.uid)
            
            self.logger.debug(f"Found {len(old_uids)} emails older than {days} days in {folder}")
            return old_uids
            
        except Exception as e:
            self.logger.error(f"Failed to find old emails in {folder}: {e}")
            return []
    
    def execute_retention_stage_1(self, 
                                 account, 
                                 policy: RetentionPolicy,
                                 folder: str = None,
                                 dry_run: bool = False) -> RetentionResult:
        """
        Execute Stage 1: Move old emails from source folder to Trash
        
        Args:
            account: Account object
            policy: Retention policy to execute
            folder: Optional folder override (uses policy.folder_pattern if not provided)
            dry_run: If True, only simulate the operation
            
        Returns:
            RetentionResult with operation details
        """
        start_time = time.time()
        
        # Determine source folder
        if folder is None:
            if policy.folder_pattern:
                folder = policy.folder_pattern
            else:
                raise RetentionExecutionError(
                    policy.id, 
                    "stage_1", 
                    "No folder specified and policy has no folder_pattern"
                )
        
        result = RetentionResult(
            success=False,
            stage=RetentionStage.MOVE_TO_TRASH,
            policy_id=policy.id,
            folder=folder,
            emails_processed=0,
            emails_affected=0,
            dry_run=dry_run
        )
        
        try:
            # Connect to mailbox
            mailbox = account.login()
            if not mailbox:
                raise RetentionExecutionError(policy.id, "stage_1", "Failed to connect to mailbox")
            
            # Find old emails
            old_uids = self.find_emails_older_than(mailbox, folder, policy.retention_days)
            result.emails_processed = len(old_uids)
            
            if not old_uids:
                result.success = True
                result.execution_time_seconds = time.time() - start_time
                self.logger.info(f"No emails to move for policy {policy.id} in {folder}")
                return result
            
            # Respect max emails per operation limit
            max_emails = self.settings.global_settings.get("max_emails_per_operation", 1000)
            if len(old_uids) > max_emails:
                old_uids = old_uids[:max_emails]
                self.logger.warning(f"Limiting operation to {max_emails} emails for safety")
            
            # Execute or simulate the move
            if not dry_run:
                moved_count = self.trash_manager.move_to_trash(
                    mailbox=mailbox,
                    message_uids=old_uids,
                    source_folder=folder,
                    account=account,
                    policy_id=policy.id
                )
                result.emails_affected = moved_count
                
                # Update policy statistics
                policy.emails_moved_to_trash += moved_count
                policy.mark_applied()
                self.save_policies()
            else:
                result.emails_affected = len(old_uids)
                self.logger.info(f"DRY RUN: Would move {len(old_uids)} emails to trash")
            
            # Cleanup mailbox connection
            mailbox.logout()
            
            result.success = True
            result.execution_time_seconds = time.time() - start_time
            
            # Log the operation
            if not dry_run:
                self.audit_logger.log_retention_operation(
                    stage=RetentionStage.MOVE_TO_TRASH,
                    policy=policy,
                    folder=folder,
                    messages_affected=result.emails_affected,
                    success=True,
                    account_email=account.email,
                    execution_time=result.execution_time_seconds
                )
            
            self.logger.info(f"Stage 1 completed for policy {policy.id}: {result.emails_affected} emails moved")
            return result
            
        except Exception as e:
            result.error_message = str(e)
            result.execution_time_seconds = time.time() - start_time
            
            # Log the failed operation
            self.audit_logger.log_retention_operation(
                stage=RetentionStage.MOVE_TO_TRASH,
                policy=policy,
                folder=folder,
                messages_affected=0,
                success=False,
                account_email=account.email,
                error_message=str(e),
                execution_time=result.execution_time_seconds,
                dry_run=dry_run
            )
            
            self.logger.error(f"Stage 1 failed for policy {policy.id}: {e}")
            
            # Cleanup mailbox if still connected
            if 'mailbox' in locals() and mailbox:
                try:
                    mailbox.logout()
                except:
                    pass
            
            if not dry_run:
                raise RetentionExecutionError(policy.id, "stage_1", str(e))
            
            return result
    
    def execute_retention_stage_2(self, 
                                 account, 
                                 trash_retention_days: int = 7,
                                 dry_run: bool = False) -> RetentionResult:
        """
        Execute Stage 2: Permanently delete old emails from Trash folder
        
        Args:
            account: Account object
            trash_retention_days: Days to keep emails in trash
            dry_run: If True, only simulate the operation
            
        Returns:
            RetentionResult with operation details
        """
        start_time = time.time()
        
        result = RetentionResult(
            success=False,
            stage=RetentionStage.PERMANENT_DELETE,
            policy_id="trash-cleanup",
            folder="trash",
            emails_processed=0,
            emails_affected=0,
            dry_run=dry_run
        )
        
        try:
            # Execute or simulate permanent deletion
            if not dry_run:
                deleted_count = self.trash_manager.cleanup_old_trash(
                    account=account,
                    retention_days=trash_retention_days
                )
                result.emails_affected = deleted_count
            else:
                # For dry run, just count what would be deleted
                mailbox = account.login()
                if mailbox:
                    trash_folder = self.trash_manager.get_trash_folder(account, mailbox)
                    old_uids = self.find_emails_older_than(mailbox, trash_folder, trash_retention_days)
                    result.emails_affected = len(old_uids)
                    mailbox.logout()
                    self.logger.info(f"DRY RUN: Would permanently delete {len(old_uids)} emails from trash")
            
            result.success = True
            result.execution_time_seconds = time.time() - start_time
            
            # Log the operation
            if not dry_run:
                self.audit_logger.log_retention_operation(
                    stage=RetentionStage.PERMANENT_DELETE,
                    policy=None,  # This is a general trash cleanup
                    folder="trash",
                    messages_affected=result.emails_affected,
                    success=True,
                    account_email=account.email,
                    execution_time=result.execution_time_seconds
                )
            
            self.logger.info(f"Stage 2 completed: {result.emails_affected} emails permanently deleted")
            return result
            
        except Exception as e:
            result.error_message = str(e)
            result.execution_time_seconds = time.time() - start_time
            
            # Log the failed operation
            self.audit_logger.log_retention_operation(
                stage=RetentionStage.PERMANENT_DELETE,
                policy=None,
                folder="trash",
                messages_affected=0,
                success=False,
                account_email=account.email,
                error_message=str(e),
                execution_time=result.execution_time_seconds,
                dry_run=dry_run
            )
            
            self.logger.error(f"Stage 2 failed: {e}")
            
            if not dry_run:
                raise RetentionExecutionError("trash-cleanup", "stage_2", str(e))
            
            return result
    
    def execute_policies_for_account(self, 
                                   account, 
                                   stage: RetentionStage = None,
                                   dry_run: bool = False) -> List[RetentionResult]:
        """
        Execute all applicable retention policies for an account
        
        Args:
            account: Account object
            stage: Optional specific stage to execute (both if None)
            dry_run: If True, only simulate operations
            
        Returns:
            List of RetentionResult objects
        """
        results = []
        
        # Get all active policies
        all_policies = [p for p in self.settings.get_all_policies() if p.active]
        
        self.logger.info(f"Executing {len(all_policies)} retention policies for {account.email}")
        
        # Execute Stage 1 for applicable policies
        if stage is None or stage == RetentionStage.MOVE_TO_TRASH:
            for policy in all_policies:
                if policy.folder_pattern:  # Only folder policies for now
                    try:
                        result = self.execute_retention_stage_1(account, policy, dry_run=dry_run)
                        results.append(result)
                    except Exception as e:
                        self.logger.error(f"Failed to execute policy {policy.id}: {e}")
        
        # Execute Stage 2 (trash cleanup)
        if stage is None or stage == RetentionStage.PERMANENT_DELETE:
            try:
                trash_retention = self.settings.global_settings.get("default_trash_retention_days", 7)
                result = self.execute_retention_stage_2(account, trash_retention, dry_run=dry_run)
                results.append(result)
            except Exception as e:
                self.logger.error(f"Failed to execute trash cleanup: {e}")
        
        return results
    
    def get_retention_preview(self, account, policy_id: str = None) -> Dict[str, Any]:
        """
        Generate a preview of what retention operations would do
        
        Args:
            account: Account object
            policy_id: Optional specific policy to preview
            
        Returns:
            Dictionary with preview information
        """
        preview = {
            'account_email': account.email,
            'timestamp': datetime.now().isoformat(),
            'policies': [],
            'summary': {
                'emails_to_trash': 0,
                'emails_to_delete': 0,
                'folders_affected': set()
            }
        }
        
        try:
            # Get policies to preview
            if policy_id:
                policy = self.settings.get_policy_by_id(policy_id)
                if not policy:
                    raise PolicyNotFoundError(policy_id)
                policies = [policy]
            else:
                policies = [p for p in self.settings.get_all_policies() if p.active]
            
            # Preview each policy
            for policy in policies:
                if policy.folder_pattern:
                    try:
                        # Execute dry run
                        result = self.execute_retention_stage_1(account, policy, dry_run=True)
                        
                        policy_preview = {
                            'policy_id': policy.id,
                            'policy_name': policy.name,
                            'folder': result.folder,
                            'emails_to_move': result.emails_affected,
                            'retention_days': policy.retention_days,
                            'total_lifecycle_days': policy.total_lifecycle_days
                        }
                        
                        preview['policies'].append(policy_preview)
                        preview['summary']['emails_to_trash'] += result.emails_affected
                        preview['summary']['folders_affected'].add(result.folder)
                        
                    except Exception as e:
                        self.logger.warning(f"Could not preview policy {policy.id}: {e}")
            
            # Preview trash cleanup
            try:
                trash_retention = self.settings.global_settings.get("default_trash_retention_days", 7)
                trash_result = self.execute_retention_stage_2(account, trash_retention, dry_run=True)
                preview['summary']['emails_to_delete'] = trash_result.emails_affected
            except Exception as e:
                self.logger.warning(f"Could not preview trash cleanup: {e}")
            
            # Convert sets to lists for JSON serialization
            preview['summary']['folders_affected'] = list(preview['summary']['folders_affected'])
            
        except Exception as e:
            self.logger.error(f"Failed to generate retention preview: {e}")
            preview['error'] = str(e)
        
        return preview