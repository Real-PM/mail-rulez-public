"""
Data models for retention policy system

Defines the core data structures for email retention policies,
settings, and trash management.
"""

import json
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Any
from enum import Enum
from pathlib import Path


class RetentionStage(Enum):
    """Stages of email retention lifecycle"""
    MOVE_TO_TRASH = "move_to_trash"       # Stage 1: Move to trash folder
    PERMANENT_DELETE = "permanent_delete"  # Stage 2: Delete from trash


@dataclass
class RetentionPolicy:
    """Individual retention policy configuration"""
    id: str
    name: str
    description: str
    retention_days: int                   # Days before moving to trash
    trash_retention_days: int = 7         # Days in trash before permanent deletion
    folder_pattern: Optional[str] = None  # For folder-level policies
    rule_id: Optional[str] = None         # For rule-based policies
    skip_trash: bool = False              # For immediate deletion if needed
    dry_run_mode: bool = False
    active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_applied: Optional[str] = None
    emails_moved_to_trash: int = 0
    emails_permanently_deleted: int = 0
    
    def __post_init__(self):
        """Validate policy after initialization"""
        if self.retention_days < 1:
            raise ValueError("Retention days must be at least 1")
        if self.trash_retention_days < 1:
            raise ValueError("Trash retention days must be at least 1")
        if not self.folder_pattern and not self.rule_id:
            raise ValueError("Policy must specify either folder_pattern or rule_id")
        if self.folder_pattern and self.rule_id:
            raise ValueError("Policy cannot specify both folder_pattern and rule_id")
    
    @property
    def total_lifecycle_days(self) -> int:
        """Total days from creation to permanent deletion"""
        if self.skip_trash:
            return self.retention_days
        return self.retention_days + self.trash_retention_days
    
    @property
    def policy_type(self) -> str:
        """Return whether this is a folder or rule-based policy"""
        return "folder" if self.folder_pattern else "rule"
    
    def update_timestamp(self):
        """Update the updated_at timestamp"""
        self.updated_at = datetime.now().isoformat()
    
    def mark_applied(self):
        """Mark policy as applied with current timestamp"""
        self.last_applied = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RetentionPolicy':
        """Create instance from dictionary"""
        return cls(**data)


@dataclass
class RetentionSettings:
    """Container for all retention policies and global settings"""
    folder_policies: Dict[str, RetentionPolicy] = field(default_factory=dict)
    rule_policies: Dict[str, RetentionPolicy] = field(default_factory=dict)
    global_settings: Dict[str, Any] = field(default_factory=lambda: {
        "min_retention_days": 1,
        "max_emails_per_operation": 1000,
        "default_trash_retention_days": 7,
        "scheduler_enabled": True,
        "scheduler_hour": 2,
        "audit_retention_days": 365
    })
    trash_folders: Dict[str, str] = field(default_factory=lambda: {
        "default": "INBOX.Trash",
        "gmail_pattern": "[Gmail]/Trash",
        "outlook_pattern": "Deleted Items",
        "icloud_pattern": "INBOX.Trash"
    })
    
    def get_all_policies(self) -> List[RetentionPolicy]:
        """Get all policies (folder and rule-based) as a list"""
        all_policies = []
        all_policies.extend(self.folder_policies.values())
        all_policies.extend(self.rule_policies.values())
        return all_policies
    
    def get_policy_by_id(self, policy_id: str) -> Optional[RetentionPolicy]:
        """Get a policy by its ID"""
        # Check folder policies first
        if policy_id in self.folder_policies:
            return self.folder_policies[policy_id]
        # Check rule policies
        if policy_id in self.rule_policies:
            return self.rule_policies[policy_id]
        return None
    
    def get_policy_by_rule_id(self, rule_id: str) -> Optional[RetentionPolicy]:
        """Get a policy by its associated rule ID"""
        for policy in self.rule_policies.values():
            if policy.rule_id == rule_id:
                return policy
        return None
    
    def add_policy(self, policy: RetentionPolicy):
        """Add a new retention policy"""
        if policy.folder_pattern:
            self.folder_policies[policy.id] = policy
        else:
            self.rule_policies[policy.id] = policy
    
    def remove_policy(self, policy_id: str) -> bool:
        """Remove a policy by ID. Returns True if found and removed."""
        if policy_id in self.folder_policies:
            del self.folder_policies[policy_id]
            return True
        if policy_id in self.rule_policies:
            del self.rule_policies[policy_id]
            return True
        return False
    
    def get_applicable_folder_policies(self, folder_name: str) -> List[RetentionPolicy]:
        """Get folder policies that apply to the given folder"""
        applicable = []
        folder_lower = folder_name.lower()
        
        for policy in self.folder_policies.values():
            if not policy.active:
                continue
            
            if policy.folder_pattern:
                pattern_lower = policy.folder_pattern.lower()
                # Simple pattern matching - can be enhanced later
                if pattern_lower in folder_lower or folder_lower.endswith(pattern_lower):
                    applicable.append(policy)
        
        return applicable
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "folder_policies": {k: v.to_dict() for k, v in self.folder_policies.items()},
            "rule_policies": {k: v.to_dict() for k, v in self.rule_policies.items()},
            "global_settings": self.global_settings,
            "trash_folders": self.trash_folders
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RetentionSettings':
        """Create instance from dictionary"""
        folder_policies = {
            k: RetentionPolicy.from_dict(v) 
            for k, v in data.get("folder_policies", {}).items()
        }
        rule_policies = {
            k: RetentionPolicy.from_dict(v) 
            for k, v in data.get("rule_policies", {}).items()
        }
        
        return cls(
            folder_policies=folder_policies,
            rule_policies=rule_policies,
            global_settings=data.get("global_settings", {}),
            trash_folders=data.get("trash_folders", {})
        )


@dataclass
class TrashItem:
    """Represents an email item in the trash folder"""
    uid: str
    account_email: str
    subject: str
    sender: str
    moved_to_trash_date: datetime
    original_folder: Optional[str] = None
    policy_id: Optional[str] = None
    scheduled_deletion_date: Optional[datetime] = None
    
    @property
    def days_in_trash(self) -> int:
        """Calculate how many days the item has been in trash"""
        return (datetime.now() - self.moved_to_trash_date).days
    
    @property
    def days_until_deletion(self) -> int:
        """Calculate days remaining before permanent deletion"""
        if self.scheduled_deletion_date:
            return max(0, (self.scheduled_deletion_date - datetime.now()).days)
        return 0
    
    @property
    def is_scheduled_for_deletion(self) -> bool:
        """Check if item is scheduled for permanent deletion"""
        if not self.scheduled_deletion_date:
            return False
        return datetime.now() >= self.scheduled_deletion_date
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "uid": self.uid,
            "account_email": self.account_email,
            "subject": self.subject,
            "sender": self.sender,
            "moved_to_trash_date": self.moved_to_trash_date.isoformat(),
            "original_folder": self.original_folder,
            "policy_id": self.policy_id,
            "scheduled_deletion_date": self.scheduled_deletion_date.isoformat() if self.scheduled_deletion_date else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TrashItem':
        """Create instance from dictionary"""
        moved_date = datetime.fromisoformat(data["moved_to_trash_date"])
        scheduled_date = None
        if data.get("scheduled_deletion_date"):
            scheduled_date = datetime.fromisoformat(data["scheduled_deletion_date"])
        
        return cls(
            uid=data["uid"],
            account_email=data["account_email"],
            subject=data["subject"],
            sender=data["sender"],
            moved_to_trash_date=moved_date,
            original_folder=data.get("original_folder"),
            policy_id=data.get("policy_id"),
            scheduled_deletion_date=scheduled_date
        )


@dataclass
class RetentionResult:
    """Result of a retention operation"""
    success: bool
    stage: RetentionStage
    policy_id: str
    folder: str
    emails_processed: int
    emails_affected: int
    error_message: Optional[str] = None
    execution_time_seconds: float = 0.0
    dry_run: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging and reporting"""
        return {
            "success": self.success,
            "stage": self.stage.value,
            "policy_id": self.policy_id,
            "folder": self.folder,
            "emails_processed": self.emails_processed,
            "emails_affected": self.emails_affected,
            "error_message": self.error_message,
            "execution_time_seconds": self.execution_time_seconds,
            "dry_run": self.dry_run,
            "timestamp": datetime.now().isoformat()
        }


def create_default_folder_policies() -> Dict[str, RetentionPolicy]:
    """Create default folder-level retention policies"""
    defaults = {
        "approved_ads": RetentionPolicy(
            id="default-approved-ads",
            name="Vendor Email Cleanup",
            description="Move vendor/marketing emails to trash after 30 days",
            retention_days=30,
            trash_retention_days=7,
            folder_pattern="approved_ads"
        ),
        "junk": RetentionPolicy(
            id="default-junk",
            name="Junk Email Cleanup",
            description="Move junk emails to trash after 7 days",
            retention_days=7,
            trash_retention_days=7,
            folder_pattern="junk"
        ),
        "processed": RetentionPolicy(
            id="default-processed",
            name="Processed Email Cleanup",
            description="Move processed emails to trash after 90 days",
            retention_days=90,
            trash_retention_days=7,
            folder_pattern="processed"
        )
    }
    return defaults


def migrate_legacy_retention_settings(legacy_settings: Dict[str, int]) -> RetentionSettings:
    """
    Migrate from legacy retention_settings format to new policy system
    
    Args:
        legacy_settings: Dict like {'approved_ads': 30, 'junk': 7, ...}
    
    Returns:
        RetentionSettings with equivalent policies
    """
    settings = RetentionSettings()
    
    # Create folder policies from legacy settings
    for folder_type, days in legacy_settings.items():
        policy = RetentionPolicy(
            id=f"migrated-{folder_type}",
            name=f"{folder_type.title()} Cleanup (Migrated)",
            description=f"Migrated policy for {folder_type} folder",
            retention_days=days,
            trash_retention_days=7,  # Default trash retention
            folder_pattern=folder_type
        )
        settings.add_policy(policy)
    
    return settings