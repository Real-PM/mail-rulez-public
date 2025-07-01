"""
Audit logging for retention operations

Provides comprehensive logging of all retention activities for compliance,
debugging, and user transparency.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import asdict

from .models import RetentionStage, RetentionPolicy, RetentionResult


class RetentionAuditLogger:
    """Manages audit logging for all retention operations"""
    
    def __init__(self, audit_log_path: Path):
        self.audit_log_path = audit_log_path
        self.logger = self._setup_logger()
        
        # Ensure audit log directory exists
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    
    def _setup_logger(self) -> logging.Logger:
        """Set up dedicated logger for retention audit"""
        logger = logging.getLogger("retention_audit")
        logger.setLevel(logging.INFO)
        
        # Avoid duplicate handlers
        if not logger.handlers:
            handler = logging.FileHandler(self.audit_log_path)
            formatter = logging.Formatter(
                '%(asctime)s [RETENTION_AUDIT] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def log_retention_operation(self, 
                              stage: RetentionStage,
                              policy: RetentionPolicy, 
                              folder: str,
                              messages_affected: int,
                              success: bool,
                              account_email: str = None,
                              error_message: str = None,
                              execution_time: float = None,
                              dry_run: bool = False) -> str:
        """
        Log a retention operation with full details
        
        Returns:
            str: Unique audit entry ID for reference
        """
        audit_id = f"ret_{int(datetime.now().timestamp())}_{policy.id[:8]}"
        
        audit_entry = {
            'audit_id': audit_id,
            'timestamp': datetime.now().isoformat(),
            'stage': stage.value,
            'policy_id': policy.id,
            'policy_name': policy.name,
            'policy_type': policy.policy_type,
            'folder': folder,
            'account_email': account_email,
            'messages_affected': messages_affected,
            'success': success,
            'error_message': error_message,
            'execution_time_seconds': execution_time,
            'dry_run': dry_run,
            'recovery_window_days': policy.trash_retention_days,
            'total_lifecycle_days': policy.total_lifecycle_days
        }
        
        # Log as JSON for structured parsing
        self.logger.info(json.dumps(audit_entry))
        
        return audit_id
    
    def log_policy_change(self, 
                         operation: str,  # 'create', 'update', 'delete'
                         policy: RetentionPolicy,
                         old_policy: RetentionPolicy = None,
                         user_id: str = None) -> str:
        """Log policy configuration changes"""
        audit_id = f"pol_{int(datetime.now().timestamp())}_{policy.id[:8]}"
        
        audit_entry = {
            'audit_id': audit_id,
            'timestamp': datetime.now().isoformat(),
            'operation_type': 'policy_change',
            'change_operation': operation,
            'policy_id': policy.id,
            'policy_name': policy.name,
            'user_id': user_id,
            'new_policy': policy.to_dict(),
            'old_policy': old_policy.to_dict() if old_policy else None
        }
        
        self.logger.info(json.dumps(audit_entry))
        return audit_id
    
    def log_trash_operation(self,
                           operation: str,  # 'move_to_trash', 'restore_from_trash', 'permanent_delete'
                           account_email: str,
                           folder: str,
                           message_uids: List[str],
                           success: bool,
                           policy_id: str = None,
                           error_message: str = None) -> str:
        """Log trash folder operations"""
        audit_id = f"trash_{int(datetime.now().timestamp())}"
        
        audit_entry = {
            'audit_id': audit_id,
            'timestamp': datetime.now().isoformat(),
            'operation_type': 'trash_operation',
            'trash_operation': operation,
            'account_email': account_email,
            'folder': folder,
            'message_count': len(message_uids),
            'message_uids': message_uids[:10],  # Log first 10 UIDs for reference
            'success': success,
            'policy_id': policy_id,
            'error_message': error_message
        }
        
        self.logger.info(json.dumps(audit_entry))
        return audit_id
    
    def log_retention_result(self, result: RetentionResult) -> str:
        """Log a complete retention operation result"""
        return self.log_retention_operation(
            stage=result.stage,
            policy=None,  # Policy info should be in result
            folder=result.folder,
            messages_affected=result.emails_affected,
            success=result.success,
            error_message=result.error_message,
            execution_time=result.execution_time_seconds,
            dry_run=result.dry_run
        )
    
    def get_audit_entries(self, 
                         start_date: datetime = None,
                         end_date: datetime = None,
                         policy_id: str = None,
                         operation_type: str = None,
                         limit: int = 100) -> List[Dict[str, Any]]:
        """
        Retrieve audit entries matching criteria
        
        Args:
            start_date: Filter entries after this date
            end_date: Filter entries before this date  
            policy_id: Filter by specific policy
            operation_type: Filter by operation type
            limit: Maximum entries to return
        
        Returns:
            List of audit entry dictionaries
        """
        entries = []
        
        try:
            with open(self.audit_log_path, 'r') as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        
                        # Apply filters
                        if start_date:
                            entry_time = datetime.fromisoformat(entry['timestamp'])
                            if entry_time < start_date:
                                continue
                        
                        if end_date:
                            entry_time = datetime.fromisoformat(entry['timestamp'])
                            if entry_time > end_date:
                                continue
                        
                        if policy_id and entry.get('policy_id') != policy_id:
                            continue
                        
                        if operation_type and entry.get('operation_type') != operation_type:
                            continue
                        
                        entries.append(entry)
                        
                        if len(entries) >= limit:
                            break
                    
                    except (json.JSONDecodeError, KeyError):
                        # Skip malformed entries
                        continue
        
        except FileNotFoundError:
            # No audit log exists yet
            pass
        
        # Return newest entries first
        return list(reversed(entries))
    
    def generate_retention_report(self, 
                                 start_date: datetime,
                                 end_date: datetime) -> Dict[str, Any]:
        """
        Generate comprehensive retention activity report
        
        Returns:
            Dictionary with retention statistics and summaries
        """
        entries = self.get_audit_entries(start_date=start_date, end_date=end_date, limit=10000)
        
        report = {
            'report_period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'summary': {
                'total_operations': 0,
                'successful_operations': 0,
                'failed_operations': 0,
                'emails_moved_to_trash': 0,
                'emails_permanently_deleted': 0,
                'policies_applied': set(),
                'accounts_affected': set()
            },
            'by_stage': {
                'move_to_trash': {'count': 0, 'emails': 0},
                'permanent_delete': {'count': 0, 'emails': 0}
            },
            'by_policy': {},
            'errors': []
        }
        
        for entry in entries:
            if entry.get('operation_type') != 'retention_operation':
                continue
            
            report['summary']['total_operations'] += 1
            
            if entry.get('success'):
                report['summary']['successful_operations'] += 1
            else:
                report['summary']['failed_operations'] += 1
                if entry.get('error_message'):
                    report['errors'].append({
                        'timestamp': entry['timestamp'],
                        'policy_id': entry.get('policy_id'),
                        'error': entry['error_message']
                    })
            
            # Track by stage
            stage = entry.get('stage')
            messages_affected = entry.get('messages_affected', 0)
            
            if stage == 'move_to_trash':
                report['summary']['emails_moved_to_trash'] += messages_affected
                report['by_stage']['move_to_trash']['count'] += 1
                report['by_stage']['move_to_trash']['emails'] += messages_affected
            elif stage == 'permanent_delete':
                report['summary']['emails_permanently_deleted'] += messages_affected
                report['by_stage']['permanent_delete']['count'] += 1
                report['by_stage']['permanent_delete']['emails'] += messages_affected
            
            # Track policies and accounts
            policy_id = entry.get('policy_id')
            if policy_id:
                report['summary']['policies_applied'].add(policy_id)
                
                if policy_id not in report['by_policy']:
                    report['by_policy'][policy_id] = {
                        'policy_name': entry.get('policy_name', 'Unknown'),
                        'operations': 0,
                        'emails_affected': 0
                    }
                
                report['by_policy'][policy_id]['operations'] += 1
                report['by_policy'][policy_id]['emails_affected'] += messages_affected
            
            account_email = entry.get('account_email')
            if account_email:
                report['summary']['accounts_affected'].add(account_email)
        
        # Convert sets to lists for JSON serialization
        report['summary']['policies_applied'] = list(report['summary']['policies_applied'])
        report['summary']['accounts_affected'] = list(report['summary']['accounts_affected'])
        
        return report
    
    def cleanup_old_audit_logs(self, retention_days: int = 365):
        """Remove audit log entries older than specified days"""
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        
        if not self.audit_log_path.exists():
            return
        
        temp_file = self.audit_log_path.with_suffix('.tmp')
        entries_kept = 0
        
        try:
            with open(self.audit_log_path, 'r') as infile, \
                 open(temp_file, 'w') as outfile:
                
                for line in infile:
                    try:
                        entry = json.loads(line.strip())
                        entry_time = datetime.fromisoformat(entry['timestamp'])
                        
                        if entry_time >= cutoff_date:
                            outfile.write(line)
                            entries_kept += 1
                    
                    except (json.JSONDecodeError, KeyError):
                        # Keep malformed entries to avoid data loss
                        outfile.write(line)
                        entries_kept += 1
            
            # Replace original file with cleaned version
            temp_file.replace(self.audit_log_path)
            
            # Log the cleanup operation
            self.logger.info(json.dumps({
                'audit_id': f"cleanup_{int(datetime.now().timestamp())}",
                'timestamp': datetime.now().isoformat(),
                'operation_type': 'audit_cleanup',
                'retention_days': retention_days,
                'entries_kept': entries_kept,
                'cutoff_date': cutoff_date.isoformat()
            }))
        
        except Exception as e:
            # Clean up temp file on error
            if temp_file.exists():
                temp_file.unlink()
            raise e