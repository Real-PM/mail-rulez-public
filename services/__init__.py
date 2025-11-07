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
Services module for Mail-Rulez

Provides email processing service management, background task orchestration,
and centralized scheduling for web-managed email processing.
"""

from .email_processor import EmailProcessor
from .task_manager import TaskManager

__all__ = ['EmailProcessor', 'TaskManager']