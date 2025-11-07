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
Dashboard routes for Mail-Rulez web interface

Provides overview, statistics, and system status information.
"""

from flask import Blueprint, render_template, jsonify, current_app, redirect, url_for, request
from functools import wraps
import psutil
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path


dashboard_bp = Blueprint('dashboard', __name__)


def login_required(f):
    """Decorator to require authentication for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_app.get_current_user():
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


@dashboard_bp.route('/')
@dashboard_bp.route('/overview')
@login_required
def overview():
    """Main dashboard overview page"""
    # DEPLOYMENT TEST LOG - Build 53 verification
    current_app.logger.info("DEPLOYMENT_TEST: Dashboard overview route accessed - Build 53 is active")
    
    # Get system stats
    stats = get_system_stats()
    
    # Get processing stats
    processing_stats = get_processing_stats()
    
    # Get recent activity
    recent_activity = get_recent_activity()
    
    # Get account stats
    account_stats = get_account_stats()
    
    # Get service mode information
    service_info = get_service_info()

    # Get account details for table
    accounts = get_account_details()

    return render_template('dashboard/overview.html',
                         stats=stats,
                         processing_stats=processing_stats,
                         recent_activity=recent_activity,
                         account_count=account_stats.get('active_accounts', 0),
                         service_info=service_info,
                         accounts=accounts)


@dashboard_bp.route('/api/stats')
@login_required
def api_stats():
    """API endpoint for real-time dashboard data"""
    # DEPLOYMENT TEST LOG - Build 53 verification for API endpoint
    current_app.logger.info("DEPLOYMENT_TEST: Dashboard API stats endpoint called - Build 53 is active")
    
    # Get recent activity and convert datetime objects to strings for JSON
    recent_activity = get_recent_activity()
    activity_json = []
    for activity in recent_activity[:5]:  # Limit to 5 most recent
        activity_json.append({
            'message': activity['message'],
            'timestamp_str': activity['timestamp_str'],
            'status': activity['status']
        })
    
    return jsonify({
        'system': get_system_stats(),
        'processing': get_processing_stats(),
        'lists': get_list_stats(),
        'accounts': get_account_stats(),
        'recent_activity': activity_json
    })


@dashboard_bp.route('/api/logs')
@login_required
def api_logs():
    """API endpoint for recent log entries"""
    logs = get_recent_logs()
    return jsonify({'logs': logs})


def get_system_stats():
    """Get system resource statistics"""
    try:
        return {
            'cpu_percent': psutil.cpu_percent(interval=1),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_usage': psutil.disk_usage('/').percent,
            'uptime': get_uptime(),
            'python_version': f"{sys.version.split()[0]}",
            'processes': len(psutil.pids())
        }
    except Exception as e:
        current_app.logger.error(f"Error getting system stats: {e}")
        return {
            'cpu_percent': 0,
            'memory_percent': 0,
            'disk_usage': 0,
            'uptime': 'Unknown',
            'python_version': 'Unknown',
            'processes': 0
        }


def get_processing_stats():
    """Get email processing statistics"""
    fallback_stats = {
        'total_processed_today': 0,
        'whitelisted_today': 0,
        'blacklisted_today': 0,
        'pending_count': 0,
        'last_run': 'Never',
        'processing_errors': 0,
        'avg_processing_time': 'N/A'
    }
    
    try:
        # Import here to avoid circular imports
        from services.task_manager import get_task_manager
        
        task_manager = get_task_manager()
        if not task_manager:
            current_app.logger.warning("Task manager not available")
            return fallback_stats
            
        aggregate_stats = task_manager.get_aggregate_stats()
        if not aggregate_stats:
            current_app.logger.warning("Aggregate stats not available")
            return fallback_stats
        
        # Get most recent last_run timestamp from all accounts
        from datetime import datetime
        most_recent_run = None
        
        try:
            all_status = task_manager.get_all_status()
            if all_status and 'accounts' in all_status:
                for account_email, account_status in all_status['accounts'].items():
                    if account_status and 'stats' in account_status:
                        last_run_str = account_status['stats'].get('last_run')
                        if last_run_str:
                            try:
                                last_run = datetime.fromisoformat(last_run_str)
                                if most_recent_run is None or last_run > most_recent_run:
                                    most_recent_run = last_run
                            except (ValueError, TypeError):
                                continue
        except Exception as e:
            current_app.logger.warning(f"Error getting last run times: {e}")
        
        # Format last_run for display
        if most_recent_run:
            last_run_display = most_recent_run.strftime('%Y-%m-%d %H:%M:%S')
        elif aggregate_stats.get('running_accounts', 0) > 0:
            last_run_display = 'Active'
        else:
            last_run_display = 'Never'
        
        # Convert to dashboard format with safe defaults
        total_processed = aggregate_stats.get('total_emails_processed', 0)
        
        # Debug logging for zero value troubleshooting
        current_app.logger.debug(f"Processing stats - total_processed: {total_processed}, aggregate_stats keys: {list(aggregate_stats.keys())}")
        
        stats = {
            'total_processed_today': total_processed,
            'whitelisted_today': 0,  # TODO: Implement daily breakdown
            'blacklisted_today': 0,  # TODO: Implement daily breakdown
            'pending_count': aggregate_stats.get('total_emails_pending', 0),
            'last_run': last_run_display,
            'processing_errors': aggregate_stats.get('total_errors', 0),
            'avg_processing_time': f"{aggregate_stats.get('avg_processing_time', 0):.1f}s" if aggregate_stats.get('avg_processing_time', 0) > 0 else 'N/A'
        }
        
        current_app.logger.debug(f"Processing stats retrieved successfully: {stats}")
        return stats
        
    except Exception as e:
        current_app.logger.error(f"Error getting processing stats: {e}", exc_info=True)
        return fallback_stats


def get_list_stats():
    """Get email list statistics"""
    try:
        config = current_app.mail_config
        stats = {}
        
        for list_name, list_path in config.list_files.items():
            try:
                if list_path.exists():
                    with open(list_path, 'r') as f:
                        lines = [line.strip() for line in f.readlines() if line.strip()]
                        stats[list_name] = len(lines)
                else:
                    stats[list_name] = 0
            except Exception:
                stats[list_name] = 0
        
        return stats
    except Exception as e:
        current_app.logger.error(f"Error getting list stats: {e}")
        return {}


def get_account_stats():
    """Get email account statistics"""
    fallback_stats = {
        'total_accounts': 0,
        'active_accounts': 0,
        'inactive_accounts': 0,
        'error_accounts': 0,
        'account_names': []
    }
    
    try:
        # Import here to avoid circular imports
        from services.task_manager import get_task_manager
        
        task_manager = get_task_manager()
        if not task_manager:
            current_app.logger.warning("Task manager not available for account stats")
            return fallback_stats
            
        aggregate_stats = task_manager.get_aggregate_stats()
        system_status = task_manager.get_all_status()
        
        if not aggregate_stats:
            current_app.logger.warning("Aggregate stats not available for account stats")
            return fallback_stats
            
        total_accounts = aggregate_stats.get('total_accounts', 0)
        running_accounts = aggregate_stats.get('running_accounts', 0)
        
        # Count error accounts
        error_accounts = 0
        account_names = []
        
        if system_status and 'accounts' in system_status:
            for account_email, account_status in system_status['accounts'].items():
                account_names.append(account_email)
                if account_status and account_status.get('state') == 'error':
                    error_accounts += 1
        
        # Use config-based count for consistency with template
        from flask import current_app
        config_account_count = len(current_app.mail_config.accounts)
        
        stats = {
            'total_accounts': total_accounts,
            'active_accounts': config_account_count,  # Consistent with template account_count
            'running_accounts': running_accounts,  # Processors currently running
            'inactive_accounts': max(0, config_account_count - running_accounts - error_accounts),
            'error_accounts': error_accounts,
            'account_names': account_names
        }
        
        current_app.logger.debug(f"Account stats retrieved successfully: {stats}")
        return stats
        
    except Exception as e:
        current_app.logger.error(f"Error getting account stats: {e}", exc_info=True)
        return fallback_stats


def get_recent_activity():
    """Get recent system activity"""
    try:
        # Import here to avoid circular imports
        from services.task_manager import get_task_manager
        
        task_manager = get_task_manager()
        if not task_manager:
            current_app.logger.warning("Task manager not available for recent activity")
            return []
            
        task_history = task_manager.get_task_history(limit=10)
        if not task_history:
            current_app.logger.debug("No task history available")
            return []
        
        activities = []
        for task in task_history:
            try:
                # Convert task history to activity format
                timestamp = datetime.fromisoformat(task['timestamp'])
                activity = {
                    'message': get_activity_message(task),
                    'timestamp': timestamp,
                    'timestamp_str': timestamp.strftime('%H:%M:%S'),
                    'status': get_activity_status(task['type'])
                }
                activities.append(activity)
            except (KeyError, ValueError, TypeError) as e:
                current_app.logger.warning(f"Error processing task history item: {e}")
                continue
        
        current_app.logger.debug(f"Retrieved {len(activities)} recent activities")
        return activities
        
    except Exception as e:
        current_app.logger.error(f"Error getting recent activity: {e}", exc_info=True)
        return []


def get_activity_message(task):
    """Convert task history entry to human-readable message"""
    task_type = task['type']
    details = task.get('details', {})
    
    if task_type == 'account_added':
        return f"Added account {details.get('account', 'unknown')}"
    elif task_type == 'account_removed':
        return f"Removed account {details.get('account', 'unknown')}"
    elif task_type == 'service_started':
        account = details.get('account', 'unknown')
        mode = details.get('mode', 'unknown')
        return f"Started {mode} processing for {account}"
    elif task_type == 'service_stopped':
        return f"Stopped processing for {details.get('account', 'unknown')}"
    elif task_type == 'service_restarted':
        return f"Restarted processing for {details.get('account', 'unknown')}"
    elif task_type == 'mode_switched':
        account = details.get('account', 'unknown')
        new_mode = details.get('new_mode', 'unknown')
        return f"Switched {account} to {new_mode} mode"
    elif task_type == 'auto_transition':
        account = details.get('account', 'unknown')
        to_mode = details.get('to_mode', 'unknown')
        return f"Auto-transitioned {account} to {to_mode} mode"
    else:
        return f"Task: {task_type}"


def get_activity_status(task_type):
    """Get activity status based on task type"""
    if task_type in ['service_started', 'account_added', 'auto_transition', 'mode_switched']:
        return 'success'
    elif task_type in ['service_stopped', 'account_removed']:
        return 'info'
    elif task_type == 'service_restarted':
        return 'info'
    else:
        return 'info'


def get_recent_logs():
    """Get recent log entries"""
    # TODO: Implement actual log reading
    # Return empty list until real log reading is implemented
    return []


def get_uptime():
    """Get system uptime"""
    try:
        boot_time = psutil.boot_time()
        uptime_seconds = datetime.now().timestamp() - boot_time
        
        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"
    except Exception:
        return "Unknown"


def get_service_info():
    """Get service mode and status information"""
    try:
        from services.task_manager import get_task_manager
        task_manager = get_task_manager()
        status = task_manager.get_all_status()
        
        # Determine overall service mode
        modes = []
        startup_accounts = 0
        maintenance_accounts = 0
        
        # The status structure has accounts directly, not under 'data'
        if status and status.get('accounts'):
            for account_email, account_data in status['accounts'].items():
                if account_data and account_data.get('mode'):
                    mode = account_data['mode']
                    modes.append(mode)
                    if mode == 'startup':
                        startup_accounts += 1
                    elif mode == 'maintenance':
                        maintenance_accounts += 1
        
        # Determine primary mode
        if startup_accounts > 0 and maintenance_accounts == 0:
            primary_mode = "Startup"
            mode_description = "Manual Processing"
        elif maintenance_accounts > 0 and startup_accounts == 0:
            primary_mode = "Maintenance"
            mode_description = "Automatic Processing"
        elif startup_accounts > 0 and maintenance_accounts > 0:
            primary_mode = "Mixed"
            mode_description = f"{startup_accounts} Startup, {maintenance_accounts} Maintenance"
        else:
            primary_mode = "Setup"
            mode_description = "No accounts configured"
        
        return {
            'mode': primary_mode,
            'description': mode_description,
            'startup_accounts': startup_accounts,
            'maintenance_accounts': maintenance_accounts,
            'total_accounts': startup_accounts + maintenance_accounts
        }
        
    except Exception as e:
        current_app.logger.error(f"Error getting service info: {e}")
        return {
            'mode': "Unknown",
            'description': "Status unavailable",
            'startup_accounts': 0,
            'maintenance_accounts': 0,
            'total_accounts': 0
        }


def get_account_details():
    """Get detailed account information for dashboard table"""
    try:
        from services.task_manager import get_task_manager

        task_manager = get_task_manager()
        config = current_app.mail_config

        accounts_list = []

        # Get accounts from config
        for account in config.accounts:
            account_dict = {
                'email': account.email,
                'server': account.server,
                'status': 'stopped',
                'mode': 'unknown',
                'last_run': None
            }

            # Get status from task manager if available
            if task_manager:
                try:
                    status = task_manager.get_all_status()
                    if status and 'accounts' in status and account.email in status['accounts']:
                        account_status = status['accounts'][account.email]
                        if account_status:
                            # Map state to status
                            state = account_status.get('state', 'stopped')
                            if state in ['running_startup', 'running_maintenance', 'starting']:
                                account_dict['status'] = 'running'
                            elif state == 'error':
                                account_dict['status'] = 'error'
                            else:
                                account_dict['status'] = 'stopped'

                            # Get mode
                            account_dict['mode'] = account_status.get('mode', 'unknown')

                            # Get last run time from stats
                            if 'stats' in account_status and account_status['stats']:
                                last_run_str = account_status['stats'].get('last_run')
                                if last_run_str:
                                    try:
                                        last_run = datetime.fromisoformat(last_run_str)
                                        account_dict['last_run'] = last_run.strftime('%Y-%m-%d %H:%M')
                                    except (ValueError, TypeError):
                                        pass
                except Exception as e:
                    current_app.logger.warning(f"Error getting status for {account.email}: {e}")

            accounts_list.append(account_dict)

        return accounts_list

    except Exception as e:
        current_app.logger.error(f"Error getting account details: {e}", exc_info=True)
        return []