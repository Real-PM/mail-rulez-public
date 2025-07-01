"""
Trash folder management for retention system

Handles all trash folder operations including moving emails to trash,
restoration, and permanent deletion.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from pathlib import Path

from .models import TrashItem, RetentionStage
from .exceptions import TrashOperationError, TrashFolderNotFoundError
from .audit import RetentionAuditLogger


class TrashManager:
    """Manages trash folder operations and recovery"""
    
    def __init__(self, audit_logger: RetentionAuditLogger = None):
        self.logger = logging.getLogger(__name__)
        self.audit_logger = audit_logger
        
        # Common trash folder patterns by provider
        self.trash_patterns = {
            'gmail': ['[Gmail]/Trash', '[Google Mail]/Trash'],
            'outlook': ['Deleted Items', 'INBOX.Deleted Items'],
            'yahoo': ['Trash', 'INBOX.Trash'],
            'icloud': ['INBOX.Trash'],
            'default': ['INBOX.Trash', 'Trash', 'INBOX.Deleted Items']
        }
    
    def get_trash_folder(self, account, mailbox=None) -> str:
        """
        Get configured trash folder for account
        
        Args:
            account: Account object with email and configuration
            mailbox: Optional mailbox connection for folder detection
            
        Returns:
            str: Trash folder name
            
        Raises:
            TrashFolderNotFoundError: If no suitable trash folder found
        """
        # Check if account has explicit trash folder configuration
        if hasattr(account, 'folders') and account.folders:
            trash_folder = account.folders.get('trash')
            if trash_folder:
                return trash_folder
        
        # Try to detect trash folder based on email provider
        provider = self._detect_email_provider(account.email)
        patterns = self.trash_patterns.get(provider, self.trash_patterns['default'])
        
        # If we have a mailbox connection, check which folders exist
        if mailbox:
            try:
                available_folders = [folder.name for folder in mailbox.folder.list()]
                
                # Try provider-specific patterns first
                for pattern in patterns:
                    if pattern in available_folders:
                        self.logger.info(f"Found trash folder '{pattern}' for {account.email}")
                        return pattern
                
                # Try default patterns as fallback
                for pattern in self.trash_patterns['default']:
                    if pattern in available_folders:
                        self.logger.info(f"Using fallback trash folder '{pattern}' for {account.email}")
                        return pattern
                
            except Exception as e:
                self.logger.warning(f"Could not list folders for trash detection: {e}")
        
        # Use first pattern as default if detection fails
        default_folder = patterns[0] if patterns else "INBOX.Trash"
        self.logger.info(f"Using default trash folder '{default_folder}' for {account.email}")
        return default_folder
    
    def _detect_email_provider(self, email: str) -> str:
        """Detect email provider from email address"""
        domain = email.lower().split('@')[-1]
        
        if domain in ['gmail.com', 'googlemail.com']:
            return 'gmail'
        elif domain in ['outlook.com', 'hotmail.com', 'live.com']:
            return 'outlook'
        elif domain in ['yahoo.com', 'yahoo.co.uk']:
            return 'yahoo'
        elif domain in ['icloud.com', 'me.com', 'mac.com']:
            return 'icloud'
        else:
            return 'default'
    
    def move_to_trash(self, 
                     mailbox, 
                     message_uids: List[str], 
                     source_folder: str,
                     account,
                     policy_id: str = None) -> int:
        """
        Move emails to trash folder with Gmail awareness
        
        Args:
            mailbox: IMAP mailbox connection
            message_uids: List of message UIDs to move
            source_folder: Source folder name
            account: Account object
            policy_id: ID of retention policy triggering this move
            
        Returns:
            int: Number of emails successfully moved
            
        Raises:
            TrashOperationError: If trash operation fails
        """
        if not message_uids:
            return 0
        
        try:
            trash_folder = self.get_trash_folder(account, mailbox)
            
            # Ensure we're in the source folder
            mailbox.folder.set(source_folder)
            
            # Use Gmail-aware move if available
            moved_count = 0
            try:
                # Check if we have Gmail-aware functions available
                import functions as pf
                if pf.is_gmail_account(account.email):
                    # Use Gmail-aware move to properly handle labels
                    result = pf.gmail_aware_move(mailbox, message_uids, trash_folder, source_folder)
                    moved_count = len(message_uids) if result else 0
                else:
                    # Standard IMAP move
                    mailbox.move(message_uids, trash_folder)
                    moved_count = len(message_uids)
            except ImportError:
                # Fallback to standard IMAP move if functions module not available
                mailbox.move(message_uids, trash_folder)
                moved_count = len(message_uids)
            
            # Log the operation
            if self.audit_logger:
                self.audit_logger.log_trash_operation(
                    operation='move_to_trash',
                    account_email=account.email,
                    folder=source_folder,
                    message_uids=message_uids,
                    success=True,
                    policy_id=policy_id
                )
            
            self.logger.info(f"Moved {moved_count} emails from {source_folder} to {trash_folder}")
            return moved_count
            
        except Exception as e:
            error_msg = f"Failed to move emails to trash: {str(e)}"
            self.logger.error(error_msg)
            
            # Log the failed operation
            if self.audit_logger:
                self.audit_logger.log_trash_operation(
                    operation='move_to_trash',
                    account_email=account.email,
                    folder=source_folder,
                    message_uids=message_uids,
                    success=False,
                    policy_id=policy_id,
                    error_message=error_msg
                )
            
            raise TrashOperationError('move_to_trash', source_folder, str(e))
    
    def get_trash_contents(self, account, mailbox=None) -> List[TrashItem]:
        """
        List contents of trash folder with age information
        
        Args:
            account: Account object
            mailbox: Optional existing mailbox connection
            
        Returns:
            List[TrashItem]: List of emails in trash with metadata
        """
        items = []
        close_mailbox = False
        
        try:
            # Connect to mailbox if not provided
            if not mailbox:
                mailbox = account.login()
                close_mailbox = True
            
            if not mailbox:
                self.logger.error(f"Could not connect to mailbox for {account.email}")
                return items
            
            trash_folder = self.get_trash_folder(account, mailbox)
            
            # Set trash folder and fetch messages
            mailbox.folder.set(trash_folder)
            
            # Import fetch function
            import functions as pf
            trash_emails = pf.fetch_class(mailbox, folder=trash_folder)
            
            # Convert to TrashItem objects
            for email in trash_emails:
                # Estimate when email was moved to trash (approximate)
                # In a full implementation, we'd track this metadata
                moved_date = email.date if hasattr(email, 'date') else datetime.now()
                
                item = TrashItem(
                    uid=email.uid,
                    account_email=account.email,
                    subject=email.subject or "No Subject",
                    sender=email.from_ or "Unknown Sender", 
                    moved_to_trash_date=moved_date,
                    original_folder=None,  # Would need metadata tracking
                    policy_id=None  # Would need metadata tracking
                )
                items.append(item)
            
            self.logger.info(f"Found {len(items)} items in trash for {account.email}")
            return items
            
        except Exception as e:
            self.logger.error(f"Failed to get trash contents: {str(e)}")
            return items
        
        finally:
            if close_mailbox and mailbox:
                try:
                    mailbox.logout()
                except:
                    pass
    
    def restore_from_trash(self, 
                          account,
                          message_uids: List[str], 
                          target_folder: str,
                          mailbox=None) -> int:
        """
        Restore emails from trash to specified folder
        
        Args:
            account: Account object
            message_uids: List of message UIDs to restore
            target_folder: Destination folder for restored emails
            mailbox: Optional existing mailbox connection
            
        Returns:
            int: Number of emails successfully restored
        """
        if not message_uids:
            return 0
        
        close_mailbox = False
        restored_count = 0
        
        try:
            # Connect to mailbox if not provided
            if not mailbox:
                mailbox = account.login()
                close_mailbox = True
            
            if not mailbox:
                self.logger.error(f"Could not connect to mailbox for {account.email}")
                return 0
            
            trash_folder = self.get_trash_folder(account, mailbox)
            
            # Ensure we're in trash folder
            mailbox.folder.set(trash_folder)
            
            # Move emails from trash to target folder
            try:
                # Check if we have Gmail-aware functions available
                import functions as pf
                if pf.is_gmail_account(account.email):
                    # Use Gmail-aware move
                    result = pf.gmail_aware_move(mailbox, message_uids, target_folder, trash_folder)
                    restored_count = len(message_uids) if result else 0
                else:
                    # Standard IMAP move
                    mailbox.move(message_uids, target_folder)
                    restored_count = len(message_uids)
            except ImportError:
                # Fallback to standard IMAP move
                mailbox.move(message_uids, target_folder)
                restored_count = len(message_uids)
            
            # Log the operation
            if self.audit_logger:
                self.audit_logger.log_trash_operation(
                    operation='restore_from_trash',
                    account_email=account.email,
                    folder=target_folder,
                    message_uids=message_uids,
                    success=True
                )
            
            self.logger.info(f"Restored {restored_count} emails from trash to {target_folder}")
            return restored_count
            
        except Exception as e:
            error_msg = f"Failed to restore emails from trash: {str(e)}"
            self.logger.error(error_msg)
            
            # Log the failed operation
            if self.audit_logger:
                self.audit_logger.log_trash_operation(
                    operation='restore_from_trash',
                    account_email=account.email,
                    folder=target_folder,
                    message_uids=message_uids,
                    success=False,
                    error_message=error_msg
                )
            
            raise TrashOperationError('restore_from_trash', target_folder, str(e))
        
        finally:
            if close_mailbox and mailbox:
                try:
                    mailbox.logout()
                except:
                    pass
    
    def permanent_delete_from_trash(self, 
                                   account,
                                   message_uids: List[str] = None,
                                   days_old: int = None,
                                   mailbox=None) -> int:
        """
        Permanently delete emails from trash folder
        
        Args:
            account: Account object
            message_uids: Specific UIDs to delete (optional)
            days_old: Delete emails older than N days (optional)
            mailbox: Optional existing mailbox connection
            
        Returns:
            int: Number of emails permanently deleted
        """
        close_mailbox = False
        deleted_count = 0
        
        try:
            # Connect to mailbox if not provided
            if not mailbox:
                mailbox = account.login()
                close_mailbox = True
            
            if not mailbox:
                self.logger.error(f"Could not connect to mailbox for {account.email}")
                return 0
            
            trash_folder = self.get_trash_folder(account, mailbox)
            
            # Ensure we're in trash folder
            mailbox.folder.set(trash_folder)
            
            # Determine which emails to delete
            uids_to_delete = []
            
            if message_uids:
                # Delete specific UIDs
                uids_to_delete = message_uids
            elif days_old is not None:
                # Delete emails older than specified days
                import functions as pf
                trash_emails = pf.fetch_class(mailbox, folder=trash_folder)
                cutoff_date = datetime.now() - timedelta(days=days_old)
                
                for email in trash_emails:
                    email_date = email.date if hasattr(email, 'date') else datetime.now()
                    if email_date < cutoff_date:
                        uids_to_delete.append(email.uid)
            
            if not uids_to_delete:
                self.logger.info(f"No emails to delete from trash for {account.email}")
                return 0
            
            # Permanently delete the emails
            mailbox.delete(uids_to_delete)
            deleted_count = len(uids_to_delete)
            
            # Log the operation
            if self.audit_logger:
                self.audit_logger.log_trash_operation(
                    operation='permanent_delete',
                    account_email=account.email,
                    folder=trash_folder,
                    message_uids=uids_to_delete,
                    success=True
                )
            
            self.logger.info(f"Permanently deleted {deleted_count} emails from trash")
            return deleted_count
            
        except Exception as e:
            error_msg = f"Failed to permanently delete emails: {str(e)}"
            self.logger.error(error_msg)
            
            # Log the failed operation
            if self.audit_logger:
                self.audit_logger.log_trash_operation(
                    operation='permanent_delete',
                    account_email=account.email,
                    folder=trash_folder if 'trash_folder' in locals() else 'Unknown',
                    message_uids=uids_to_delete if 'uids_to_delete' in locals() else [],
                    success=False,
                    error_message=error_msg
                )
            
            raise TrashOperationError('permanent_delete', 'trash', str(e))
        
        finally:
            if close_mailbox and mailbox:
                try:
                    mailbox.logout()
                except:
                    pass
    
    def cleanup_old_trash(self, account, retention_days: int = 7, mailbox=None) -> int:
        """
        Clean up old emails from trash based on retention policy
        
        Args:
            account: Account object
            retention_days: Days to keep emails in trash
            mailbox: Optional existing mailbox connection
            
        Returns:
            int: Number of emails permanently deleted
        """
        self.logger.info(f"Starting trash cleanup for {account.email} (retention: {retention_days} days)")
        
        try:
            deleted_count = self.permanent_delete_from_trash(
                account=account,
                days_old=retention_days,
                mailbox=mailbox
            )
            
            self.logger.info(f"Trash cleanup completed: {deleted_count} emails deleted")
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"Trash cleanup failed: {str(e)}")
            raise