"""
Services module for Mail-Rulez

Provides email processing service management, background task orchestration,
and centralized scheduling for web-managed email processing.
"""

from .email_processor import EmailProcessor
from .task_manager import TaskManager
from .scheduler_manager import SchedulerManager

__all__ = ['EmailProcessor', 'TaskManager', 'SchedulerManager']