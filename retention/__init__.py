"""
Mail-Rulez Retention Policy System

This package provides comprehensive email lifecycle management with two-stage
retention policies:

1. Stage 1: Move emails to trash after retention period
2. Stage 2: Permanently delete from trash after grace period

Key Components:
- models: Data structures for retention policies and settings
- manager: Core retention policy management and execution
- scheduler: Background service for automated retention operations
- trash_manager: Trash folder operations and recovery
- audit: Comprehensive audit logging for compliance
"""

from .models import (
    RetentionStage,
    RetentionPolicy, 
    RetentionSettings,
    TrashItem,
    RetentionResult
)

from .exceptions import (
    RetentionError,
    PolicyNotFoundError,
    TrashOperationError,
    InvalidRetentionPeriodError,
    PolicyValidationError,
    TrashFolderNotFoundError,
    RetentionExecutionError
)

from .manager import RetentionPolicyManager
from .scheduler import RetentionScheduler
from .audit import RetentionAuditLogger
from .trash_manager import TrashManager

__version__ = "1.0.0"
__all__ = [
    # Data Models
    "RetentionStage",
    "RetentionPolicy", 
    "RetentionSettings",
    "TrashItem",
    "RetentionResult",
    
    # Exceptions
    "RetentionError",
    "PolicyNotFoundError", 
    "TrashOperationError",
    "InvalidRetentionPeriodError",
    "PolicyValidationError",
    "TrashFolderNotFoundError",
    "RetentionExecutionError",
    
    # Core Services
    "RetentionPolicyManager",
    "RetentionScheduler",
    "RetentionAuditLogger",
    "TrashManager"
]