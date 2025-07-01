"""
Log Management Routes for Mail-Rulez Web Interface

Provides log viewing, management, and monitoring capabilities.
"""

from flask import Blueprint, render_template, jsonify, request, current_app, send_file
from functools import wraps
import os
from pathlib import Path
from datetime import datetime
import json

logs_bp = Blueprint('logs', __name__)


def login_required(f):
    """Decorator to require authentication for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_app.get_current_user():
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


@logs_bp.route('/logs')
@login_required
def logs_overview():
    """Log management overview page"""
    from logging_config import LogManager
    
    manager = LogManager()
    log_files = manager.get_log_files_info()
    total_size_bytes, total_size_human = manager.get_total_log_size()
    
    return render_template('logs/overview.html',
                         log_files=log_files,
                         total_size_bytes=total_size_bytes,
                         total_size_human=total_size_human)


@logs_bp.route('/logs/view/<log_file>')
@login_required
def view_log(log_file):
    """View specific log file contents"""
    from logging_config import LogManager
    
    manager = LogManager()
    log_path = manager.log_dir / log_file
    
    if not log_path.exists() or not log_path.is_file():
        return jsonify({'error': 'Log file not found'}), 404
    
    # Security check - only allow .log files
    if not log_file.endswith('.log') and not '.log.' in log_file:
        return jsonify({'error': 'Invalid log file'}), 400
    
    lines = request.args.get('lines', 100, type=int)
    lines = min(lines, 1000)  # Limit to prevent browser overload
    
    try:
        with open(log_path, 'r') as f:
            all_lines = f.readlines()
            if lines:
                content_lines = all_lines[-lines:]
            else:
                content_lines = all_lines
        
        return render_template('logs/view.html',
                             log_file=log_file,
                             content=content_lines,
                             total_lines=len(all_lines),
                             showing_lines=len(content_lines))
    
    except Exception as e:
        return jsonify({'error': f'Error reading log file: {str(e)}'}), 500


@logs_bp.route('/logs/api/tail/<log_file>')
@login_required
def api_tail_log(log_file):
    """API endpoint to tail log file (real-time updates)"""
    from logging_config import LogManager
    
    manager = LogManager()
    log_path = manager.log_dir / log_file
    
    if not log_path.exists():
        return jsonify({'error': 'Log file not found'}), 404
    
    lines = request.args.get('lines', 50, type=int)
    lines = min(lines, 200)
    
    try:
        with open(log_path, 'r') as f:
            all_lines = f.readlines()
            tail_lines = all_lines[-lines:] if lines else all_lines
        
        return jsonify({
            'lines': [line.rstrip() for line in tail_lines],
            'total_lines': len(all_lines),
            'file_size': log_path.stat().st_size,
            'last_modified': datetime.fromtimestamp(log_path.stat().st_mtime).isoformat()
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@logs_bp.route('/logs/api/search/<log_file>')
@login_required
def api_search_log(log_file):
    """Search within log file"""
    from logging_config import LogManager
    
    manager = LogManager()
    log_path = manager.log_dir / log_file
    
    if not log_path.exists():
        return jsonify({'error': 'Log file not found'}), 404
    
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'error': 'Search query required'}), 400
    
    max_results = request.args.get('limit', 100, type=int)
    max_results = min(max_results, 500)
    
    try:
        results = []
        line_num = 0
        
        with open(log_path, 'r') as f:
            for line in f:
                line_num += 1
                if query.lower() in line.lower():
                    results.append({
                        'line_number': line_num,
                        'content': line.rstrip(),
                        'timestamp': extract_timestamp(line)
                    })
                    
                    if len(results) >= max_results:
                        break
        
        return jsonify({
            'results': results,
            'total_found': len(results),
            'query': query,
            'truncated': len(results) >= max_results
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@logs_bp.route('/logs/api/download/<log_file>')
@login_required
def api_download_log(log_file):
    """Download log file"""
    from logging_config import LogManager
    
    manager = LogManager()
    log_path = manager.log_dir / log_file
    
    if not log_path.exists():
        return jsonify({'error': 'Log file not found'}), 404
    
    # Security check
    if not log_file.endswith('.log') and not '.log.' in log_file:
        return jsonify({'error': 'Invalid log file'}), 400
    
    try:
        return send_file(
            log_path,
            as_attachment=True,
            download_name=f"mail_rulez_{log_file}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@logs_bp.route('/logs/api/cleanup', methods=['POST'])
@login_required
def api_cleanup_logs():
    """Clean up old log files"""
    from logging_config import LogManager
    
    days_to_keep = request.json.get('days_to_keep', 30)
    days_to_keep = max(1, min(days_to_keep, 365))  # Limit between 1-365 days
    
    try:
        manager = LogManager()
        removed_files = manager.cleanup_old_logs(days_to_keep)
        
        return jsonify({
            'success': True,
            'removed_files': removed_files,
            'removed_count': len(removed_files),
            'days_to_keep': days_to_keep
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@logs_bp.route('/logs/api/stats')
@login_required
def api_log_stats():
    """Get log statistics"""
    from logging_config import LogManager
    
    try:
        manager = LogManager()
        log_files = manager.get_log_files_info()
        total_size_bytes, total_size_human = manager.get_total_log_size()
        
        # Calculate growth rate and other metrics
        stats = {
            'total_files': len(log_files),
            'total_size_bytes': total_size_bytes,
            'total_size_human': total_size_human,
            'largest_file': None,
            'oldest_file': None,
            'newest_file': None
        }
        
        if log_files:
            # Find largest file
            largest = max(log_files.items(), key=lambda x: x[1]['size_bytes'])
            stats['largest_file'] = {
                'name': largest[0],
                'size': largest[1]['size_human']
            }
            
            # Find oldest and newest files
            oldest = min(log_files.items(), key=lambda x: x[1]['modified'])
            newest = max(log_files.items(), key=lambda x: x[1]['modified'])
            
            stats['oldest_file'] = {
                'name': oldest[0],
                'modified': oldest[1]['modified']
            }
            stats['newest_file'] = {
                'name': newest[0],
                'modified': newest[1]['modified']
            }
        
        return jsonify(stats)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def extract_timestamp(log_line):
    """Extract timestamp from log line"""
    try:
        # Try to parse different timestamp formats
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S']:
            try:
                timestamp_str = log_line.split(' - ')[0]
                return datetime.strptime(timestamp_str, fmt).isoformat()
            except:
                continue
        return None
    except:
        return None