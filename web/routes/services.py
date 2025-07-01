"""
Service Management Routes

Web API endpoints for controlling email processing services.
Provides REST API for starting, stopping, monitoring, and managing
email processing services across multiple accounts.
"""

import logging
from flask import Blueprint, request, jsonify, current_app, redirect, url_for
from werkzeug.exceptions import BadRequest, NotFound
from functools import wraps

from services.task_manager import get_task_manager
from services.email_processor import ProcessingMode, ServiceState

# Create blueprint
services_bp = Blueprint('services', __name__, url_prefix='/api/services')
logger = logging.getLogger(__name__)


def login_required(f):
    """Decorator to require authentication for API routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_app.get_current_user():
            # For API endpoints, return JSON error instead of redirect
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function


@services_bp.before_request
def before_request():
    """Check authentication for all service endpoints"""
    if not current_app.get_current_user():
        return jsonify({'success': False, 'error': 'Authentication required'}), 401


@services_bp.route('/status', methods=['GET'])
def get_system_status():
    """
    Get overall system status
    
    Returns:
        JSON: Complete system status including all accounts
    """
    try:
        task_manager = get_task_manager()
        status = task_manager.get_all_status()
        
        return jsonify({
            'success': True,
            'data': status
        })
        
    except Exception as e:
        logger.error(f"Failed to get system status: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@services_bp.route('/stats', methods=['GET'])
def get_aggregate_stats():
    """
    Get aggregated statistics across all accounts
    
    Returns:
        JSON: Aggregated processing statistics
    """
    try:
        task_manager = get_task_manager()
        stats = task_manager.get_aggregate_stats()
        
        return jsonify({
            'success': True,
            'data': stats
        })
        
    except Exception as e:
        logger.error(f"Failed to get aggregate stats: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@services_bp.route('/accounts/<account_email>/status', methods=['GET'])
def get_account_status(account_email: str):
    """
    Get status for a specific account
    
    Args:
        account_email: Email address of the account
        
    Returns:
        JSON: Account status information
    """
    try:
        task_manager = get_task_manager()
        status = task_manager.get_account_status(account_email)
        
        if status is None:
            return jsonify({
                'success': False,
                'error': f'Account {account_email} not found'
            }), 404
        
        return jsonify({
            'success': True,
            'data': status
        })
        
    except Exception as e:
        logger.error(f"Failed to get status for account {account_email}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@services_bp.route('/accounts/<account_email>/folders/status', methods=['GET'])
def get_account_folder_status(account_email: str):
    """
    Get folder status for an account (what folders exist vs what's needed)
    
    Args:
        account_email: Email address of the account
        
    Returns:
        JSON: Folder status information including missing folders
    """
    try:
        task_manager = get_task_manager()
        processor = task_manager._get_processor(account_email)
        
        if not processor:
            return jsonify({
                'success': False,
                'error': f'Account {account_email} not found'
            }), 404
        
        folder_status = processor.get_folder_status()
        
        return jsonify({
            'success': True,
            'data': folder_status
        })
        
    except Exception as e:
        logger.error(f"Failed to get folder status for account {account_email}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@services_bp.route('/accounts/<account_email>/folders/create', methods=['POST'])
def create_account_folders(account_email: str):
    """
    Create missing folders for an account
    
    Args:
        account_email: Email address of the account
        
    JSON Body:
        confirm: Boolean confirmation that user wants to create folders
        
    Returns:
        JSON: Creation results
    """
    try:
        # Parse request data
        data = request.get_json() or {}
        confirm = data.get('confirm', False)
        
        if not confirm:
            return jsonify({
                'success': False,
                'error': 'Folder creation requires explicit confirmation. Set "confirm": true in request body.'
            }), 400
        
        task_manager = get_task_manager()
        processor = task_manager._get_processor(account_email)
        
        if not processor:
            return jsonify({
                'success': False,
                'error': f'Account {account_email} not found'
            }), 404
        
        # Run folder validation and creation
        result = processor._validate_and_setup_folders()
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': f"Folder setup completed for {account_email}",
                'data': {
                    'created_folders': result['created_folders'],
                    'existing_folders': len(result['existing_folders']),
                    'total_required': len(result['required_folders'])
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': f"Folder setup failed: {result['error']}"
            }), 500
        
    except Exception as e:
        logger.error(f"Failed to create folders for account {account_email}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@services_bp.route('/accounts/<account_email>/start', methods=['POST'])
def start_account(account_email: str):
    """
    Start email processing for an account
    
    Args:
        account_email: Email address of the account
        
    JSON Body:
        mode: Processing mode ('startup' or 'maintenance', defaults to 'startup')
        
    Returns:
        JSON: Success/failure result
    """
    try:
        # Parse request data
        data = request.get_json() or {}
        mode_str = data.get('mode', 'startup').lower()
        
        # Validate mode
        if mode_str == 'startup':
            mode = ProcessingMode.STARTUP
        elif mode_str == 'maintenance':
            mode = ProcessingMode.MAINTENANCE
        else:
            return jsonify({
                'success': False,
                'error': f'Invalid mode: {mode_str}. Must be "startup" or "maintenance"'
            }), 400
        
        # Start the service
        task_manager = get_task_manager()
        result = task_manager.start_account(account_email, mode)
        
        if result:
            return jsonify({
                'success': True,
                'message': f'Started email processing for {account_email} in {mode_str} mode'
            })
        else:
            return jsonify({
                'success': False,
                'error': f'Failed to start email processing for {account_email}'
            }), 500
        
    except Exception as e:
        logger.error(f"Failed to start account {account_email}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@services_bp.route('/accounts/<account_email>/stop', methods=['POST'])
def stop_account(account_email: str):
    """
    Stop email processing for an account
    
    Args:
        account_email: Email address of the account
        
    Returns:
        JSON: Success/failure result
    """
    try:
        task_manager = get_task_manager()
        result = task_manager.stop_account(account_email)
        
        if result:
            return jsonify({
                'success': True,
                'message': f'Stopped email processing for {account_email}'
            })
        else:
            return jsonify({
                'success': False,
                'error': f'Failed to stop email processing for {account_email}'
            }), 500
        
    except Exception as e:
        logger.error(f"Failed to stop account {account_email}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@services_bp.route('/accounts/<account_email>/restart', methods=['POST'])
def restart_account(account_email: str):
    """
    Restart email processing for an account
    
    Args:
        account_email: Email address of the account
        
    Returns:
        JSON: Success/failure result
    """
    try:
        task_manager = get_task_manager()
        result = task_manager.restart_account(account_email)
        
        if result:
            return jsonify({
                'success': True,
                'message': f'Restarted email processing for {account_email}'
            })
        else:
            return jsonify({
                'success': False,
                'error': f'Failed to restart email processing for {account_email}'
            }), 500
        
    except Exception as e:
        logger.error(f"Failed to restart account {account_email}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@services_bp.route('/accounts/<account_email>/mode', methods=['POST'])
def switch_mode(account_email: str):
    """
    Switch processing mode for an account
    
    Args:
        account_email: Email address of the account
        
    JSON Body:
        mode: New processing mode ('startup' or 'maintenance')
        
    Returns:
        JSON: Success/failure result
    """
    try:
        # Parse request data
        data = request.get_json() or {}
        mode_str = data.get('mode', '').lower()
        
        # Validate mode
        if mode_str == 'startup':
            mode = ProcessingMode.STARTUP
        elif mode_str == 'maintenance':
            mode = ProcessingMode.MAINTENANCE
        else:
            return jsonify({
                'success': False,
                'error': f'Invalid mode: {mode_str}. Must be "startup" or "maintenance"'
            }), 400
        
        # Switch mode
        task_manager = get_task_manager()
        result = task_manager.switch_mode(account_email, mode)
        
        if result:
            return jsonify({
                'success': True,
                'message': f'Switched {account_email} to {mode_str} mode'
            })
        else:
            return jsonify({
                'success': False,
                'error': f'Failed to switch mode for {account_email}'
            }), 500
        
    except Exception as e:
        logger.error(f"Failed to switch mode for account {account_email}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@services_bp.route('/accounts/<account_email>/logs', methods=['GET'])
def get_account_logs(account_email: str):
    """
    Get recent logs for an account
    
    Args:
        account_email: Email address of the account
        
    Query Parameters:
        limit: Maximum number of log entries (default 50)
        
    Returns:
        JSON: Recent log entries
    """
    try:
        limit = request.args.get('limit', 50, type=int)
        
        # TODO: Implement log reading functionality
        # For now, return placeholder
        logs = [
            {
                'timestamp': '2025-01-07T12:00:00Z',
                'level': 'INFO',
                'message': f'Email processing active for {account_email}',
                'module': 'email_processor'
            }
        ]
        
        return jsonify({
            'success': True,
            'data': {
                'account_email': account_email,
                'logs': logs[-limit:] if logs else []
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get logs for account {account_email}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@services_bp.route('/bulk/start', methods=['POST'])
def start_all_accounts():
    """
    Start email processing for all accounts
    
    JSON Body:
        mode: Processing mode for all accounts ('startup' or 'maintenance', defaults to 'startup')
        
    Returns:
        JSON: Results for each account
    """
    try:
        # Parse request data
        data = request.get_json() or {}
        mode_str = data.get('mode', 'startup').lower()
        
        # Validate mode
        if mode_str == 'startup':
            mode = ProcessingMode.STARTUP
        elif mode_str == 'maintenance':
            mode = ProcessingMode.MAINTENANCE
        else:
            return jsonify({
                'success': False,
                'error': f'Invalid mode: {mode_str}. Must be "startup" or "maintenance"'
            }), 400
        
        # Start all accounts
        task_manager = get_task_manager()
        results = {}
        
        # Get all account emails and start them
        status = task_manager.get_all_status()
        for account_email in status.get('accounts', {}):
            results[account_email] = task_manager.start_account(account_email, mode)
        
        successful = sum(results.values())
        total = len(results)
        
        return jsonify({
            'success': True,
            'message': f'Started {successful}/{total} accounts in {mode_str} mode',
            'results': results
        })
        
    except Exception as e:
        logger.error(f"Failed to start all accounts: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@services_bp.route('/bulk/stop', methods=['POST'])
def stop_all_accounts():
    """
    Stop email processing for all accounts
    
    Returns:
        JSON: Results for each account
    """
    try:
        task_manager = get_task_manager()
        results = task_manager.stop_all()
        
        successful = sum(results.values())
        total = len(results)
        
        return jsonify({
            'success': True,
            'message': f'Stopped {successful}/{total} accounts',
            'results': results
        })
        
    except Exception as e:
        logger.error(f"Failed to stop all accounts: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@services_bp.route('/task-history', methods=['GET'])
def get_task_history():
    """
    Get recent task history
    
    Query Parameters:
        limit: Maximum number of entries (default 50)
        
    Returns:
        JSON: Recent task history
    """
    try:
        limit = request.args.get('limit', 50, type=int)
        
        task_manager = get_task_manager()
        history = task_manager.get_task_history(limit)
        
        return jsonify({
            'success': True,
            'data': {
                'history': history,
                'count': len(history)
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get task history: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@services_bp.route('/refresh-accounts', methods=['POST'])
def refresh_accounts():
    """
    Refresh accounts from current configuration
    
    This endpoint reloads the configuration and syncs the task manager
    accounts with the current configuration. Useful after accounts
    are added/modified through the web interface.
    
    Returns:
        JSON: Success/failure result with refresh details
    """
    try:
        task_manager = get_task_manager()
        
        # Get current state before refresh
        old_status = task_manager.get_all_status()
        old_count = old_status['task_manager']['total_accounts']
        
        # Refresh accounts from config
        task_manager.refresh_accounts_from_config()
        
        # Get new state after refresh
        new_status = task_manager.get_all_status()
        new_count = new_status['task_manager']['total_accounts']
        
        return jsonify({
            'success': True,
            'message': 'Accounts refreshed from configuration',
            'data': {
                'accounts_before': old_count,
                'accounts_after': new_count,
                'accounts_changed': new_count - old_count
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to refresh accounts: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@services_bp.route('/accounts/<account_email>/process-batch', methods=['POST'])
def process_batch(account_email: str):
    """
    Process next batch of emails for an account in startup mode
    
    Args:
        account_email: Email address of the account
        
    JSON Body:
        limit: Number of emails to process (default 100)
        
    Returns:
        JSON: Detailed batch processing results
    """
    try:
        # Parse request data
        data = request.get_json() or {}
        limit = data.get('limit', 100)
        
        # Validate limit
        if not isinstance(limit, int) or limit < 1 or limit > 500:
            return jsonify({
                'success': False,
                'error': 'Limit must be an integer between 1 and 500'
            }), 400
        
        # Get the processor for this account
        task_manager = get_task_manager()
        processor = task_manager._get_processor(account_email)
        
        if not processor:
            return jsonify({
                'success': False,
                'error': f'Account {account_email} not found'
            }), 404
        
        # Check if account is in startup mode
        account_status = task_manager.get_account_status(account_email)
        if not account_status:
            return jsonify({
                'success': False,
                'error': f'Cannot get status for account {account_email}'
            }), 404
            
        current_mode = account_status.get('mode')
        if current_mode != 'startup':
            return jsonify({
                'success': False,
                'error': f'Batch processing only available in startup mode. Account is in {current_mode} mode.'
            }), 400
        
        # Use the new manual processing method that includes all rule types
        batch_result = processor.process_manual_batch()
        
        return jsonify({
            'success': True,
            'message': f'Processed {batch_result["emails_processed"]} emails for {account_email}',
            'data': batch_result
        })
        
    except Exception as e:
        logger.error(f"Failed to process batch for account {account_email}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@services_bp.route('/accounts/<account_email>/inbox-count', methods=['GET'])
def get_inbox_count(account_email: str):
    """
    Get current inbox count for an account
    
    Args:
        account_email: Email address of the account
        
    Returns:
        JSON: Current inbox count
    """
    try:
        # Get the processor for this account
        task_manager = get_task_manager()
        processor = task_manager._get_processor(account_email)
        
        if not processor:
            return jsonify({
                'success': False,
                'error': f'Account {account_email} not found'
            }), 404
        
        # Get inbox count
        try:
            mb = processor.account.login()
            inbox_count = len(list(mb.fetch('ALL')))
        except Exception as e:
            logger.warning(f"Could not get inbox count for {account_email}: {e}")
            inbox_count = 0
        
        return jsonify({
            'success': True,
            'data': {
                'account_email': account_email,
                'inbox_count': inbox_count
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get inbox count for account {account_email}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# Error handlers
@services_bp.errorhandler(400)
def bad_request(error):
    return jsonify({
        'success': False,
        'error': 'Bad request'
    }), 400


@services_bp.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'error': 'Not found'
    }), 404


@services_bp.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'error': 'Internal server error'
    }), 500