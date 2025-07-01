"""
Retention-specific exceptions for error handling and debugging
"""


class RetentionError(Exception):
    """Base exception for all retention-related errors"""
    pass


class PolicyNotFoundError(RetentionError):
    """Raised when a retention policy cannot be found"""
    
    def __init__(self, policy_id: str):
        self.policy_id = policy_id
        super().__init__(f"Retention policy not found: {policy_id}")


class TrashOperationError(RetentionError):
    """Raised when trash folder operations fail"""
    
    def __init__(self, operation: str, folder: str, reason: str):
        self.operation = operation
        self.folder = folder
        self.reason = reason
        super().__init__(f"Trash operation '{operation}' failed on folder '{folder}': {reason}")


class InvalidRetentionPeriodError(RetentionError):
    """Raised when retention period is invalid"""
    
    def __init__(self, days: int, min_days: int = 1):
        self.days = days
        self.min_days = min_days
        super().__init__(f"Invalid retention period: {days} days (minimum: {min_days})")


class PolicyValidationError(RetentionError):
    """Raised when retention policy validation fails"""
    
    def __init__(self, policy_id: str, errors: list):
        self.policy_id = policy_id
        self.errors = errors
        error_msg = "; ".join(errors)
        super().__init__(f"Policy validation failed for '{policy_id}': {error_msg}")


class TrashFolderNotFoundError(RetentionError):
    """Raised when trash folder cannot be located or accessed"""
    
    def __init__(self, account_email: str, folder_name: str = None):
        self.account_email = account_email
        self.folder_name = folder_name
        if folder_name:
            super().__init__(f"Trash folder '{folder_name}' not found for account {account_email}")
        else:
            super().__init__(f"No trash folder configured for account {account_email}")


class RetentionExecutionError(RetentionError):
    """Raised when retention policy execution fails"""
    
    def __init__(self, policy_id: str, stage: str, reason: str):
        self.policy_id = policy_id
        self.stage = stage
        self.reason = reason
        super().__init__(f"Retention execution failed for policy '{policy_id}' at stage '{stage}': {reason}")