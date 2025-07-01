"""
Scheduler Manager

Lightweight centralized management for APScheduler instances.
Provides monitoring and coordination across multiple email processors.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import dataclass

from apscheduler.schedulers.base import BaseScheduler


@dataclass
class SchedulerInfo:
    """Information about a scheduler instance"""
    scheduler_id: str
    account_email: str
    is_running: bool
    job_count: int
    next_run_time: Optional[datetime]
    last_error: Optional[str]


class SchedulerManager:
    """
    Centralized monitoring and coordination for APScheduler instances
    
    Note: Individual EmailProcessor instances manage their own schedulers.
    This class provides monitoring and coordination capabilities.
    """
    
    def __init__(self):
        """Initialize scheduler manager"""
        self.registered_schedulers: Dict[str, BaseScheduler] = {}
        self.scheduler_info: Dict[str, SchedulerInfo] = {}
        self.logger = logging.getLogger('scheduler_manager')
        
        self.logger.info("Scheduler manager initialized")
    
    def register_scheduler(self, scheduler_id: str, scheduler: BaseScheduler, account_email: str):
        """
        Register a scheduler for monitoring
        
        Args:
            scheduler_id: Unique identifier for the scheduler
            scheduler: APScheduler instance
            account_email: Associated account email
        """
        self.registered_schedulers[scheduler_id] = scheduler
        self.scheduler_info[scheduler_id] = SchedulerInfo(
            scheduler_id=scheduler_id,
            account_email=account_email,
            is_running=False,
            job_count=0,
            next_run_time=None,
            last_error=None
        )
        
        self.logger.debug(f"Registered scheduler {scheduler_id} for account {account_email}")
    
    def unregister_scheduler(self, scheduler_id: str):
        """
        Unregister a scheduler
        
        Args:
            scheduler_id: Scheduler identifier to unregister
        """
        if scheduler_id in self.registered_schedulers:
            del self.registered_schedulers[scheduler_id]
        
        if scheduler_id in self.scheduler_info:
            del self.scheduler_info[scheduler_id]
        
        self.logger.debug(f"Unregistered scheduler {scheduler_id}")
    
    def update_scheduler_status(self):
        """Update status information for all registered schedulers"""
        for scheduler_id, scheduler in self.registered_schedulers.items():
            try:
                info = self.scheduler_info.get(scheduler_id)
                if not info:
                    continue
                
                # Update status
                info.is_running = scheduler.running if hasattr(scheduler, 'running') else False
                info.job_count = len(scheduler.get_jobs()) if hasattr(scheduler, 'get_jobs') else 0
                
                # Get next run time
                jobs = scheduler.get_jobs() if hasattr(scheduler, 'get_jobs') else []
                if jobs:
                    next_times = [job.next_run_time for job in jobs if job.next_run_time]
                    info.next_run_time = min(next_times) if next_times else None
                else:
                    info.next_run_time = None
                
                info.last_error = None
                
            except Exception as e:
                if scheduler_id in self.scheduler_info:
                    self.scheduler_info[scheduler_id].last_error = str(e)
                self.logger.error(f"Failed to update status for scheduler {scheduler_id}: {e}")
    
    def get_scheduler_status(self, scheduler_id: str) -> Optional[Dict[str, Any]]:
        """
        Get status for a specific scheduler
        
        Args:
            scheduler_id: Scheduler identifier
            
        Returns:
            dict: Scheduler status or None if not found
        """
        info = self.scheduler_info.get(scheduler_id)
        if not info:
            return None
        
        return {
            'scheduler_id': info.scheduler_id,
            'account_email': info.account_email,
            'is_running': info.is_running,
            'job_count': info.job_count,
            'next_run_time': info.next_run_time.isoformat() if info.next_run_time else None,
            'last_error': info.last_error
        }
    
    def get_all_status(self) -> Dict[str, Any]:
        """
        Get status for all schedulers
        
        Returns:
            dict: Complete scheduler status
        """
        self.update_scheduler_status()
        
        schedulers_status = {}
        for scheduler_id in self.scheduler_info:
            schedulers_status[scheduler_id] = self.get_scheduler_status(scheduler_id)
        
        # Calculate summary statistics
        total_schedulers = len(self.scheduler_info)
        running_schedulers = sum(1 for info in self.scheduler_info.values() if info.is_running)
        total_jobs = sum(info.job_count for info in self.scheduler_info.values())
        error_schedulers = sum(1 for info in self.scheduler_info.values() if info.last_error)
        
        return {
            'summary': {
                'total_schedulers': total_schedulers,
                'running_schedulers': running_schedulers,
                'total_jobs': total_jobs,
                'error_schedulers': error_schedulers,
                'last_updated': datetime.now().isoformat()
            },
            'schedulers': schedulers_status
        }
    
    def get_jobs_summary(self) -> List[Dict[str, Any]]:
        """
        Get summary of all jobs across schedulers
        
        Returns:
            list: Job summary information
        """
        jobs_summary = []
        
        for scheduler_id, scheduler in self.registered_schedulers.items():
            try:
                if hasattr(scheduler, 'get_jobs'):
                    jobs = scheduler.get_jobs()
                    
                    for job in jobs:
                        jobs_summary.append({
                            'scheduler_id': scheduler_id,
                            'account_email': self.scheduler_info[scheduler_id].account_email,
                            'job_id': job.id,
                            'job_name': job.name or job.func.__name__ if hasattr(job, 'func') else 'Unknown',
                            'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
                            'trigger': str(job.trigger) if hasattr(job, 'trigger') else 'Unknown'
                        })
                        
            except Exception as e:
                self.logger.error(f"Failed to get jobs for scheduler {scheduler_id}: {e}")
        
        return jobs_summary
    
    def shutdown_all(self):
        """Shutdown all registered schedulers"""
        self.logger.info("Shutting down all registered schedulers")
        
        for scheduler_id, scheduler in self.registered_schedulers.items():
            try:
                if hasattr(scheduler, 'running') and scheduler.running:
                    scheduler.shutdown(wait=True)
                    self.logger.debug(f"Shutdown scheduler {scheduler_id}")
                    
            except Exception as e:
                self.logger.error(f"Failed to shutdown scheduler {scheduler_id}: {e}")
        
        # Clear registered schedulers
        self.registered_schedulers.clear()
        self.scheduler_info.clear()
        
        self.logger.info("All schedulers shutdown complete")


# Global scheduler manager instance
_scheduler_manager: Optional[SchedulerManager] = None


def get_scheduler_manager() -> SchedulerManager:
    """
    Get global scheduler manager instance (singleton)
    
    Returns:
        SchedulerManager: Global scheduler manager instance
    """
    global _scheduler_manager
    
    if _scheduler_manager is None:
        _scheduler_manager = SchedulerManager()
    
    return _scheduler_manager