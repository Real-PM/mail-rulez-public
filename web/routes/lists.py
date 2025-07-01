"""
List management routes for Mail-Rulez web interface

Handles dynamic list management with drag-and-drop support and conflict resolution.
"""

import os
import sys
from pathlib import Path
from flask import Blueprint, render_template, redirect, url_for, flash, current_app, request, jsonify
from functools import wraps

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import functions as pf


lists_bp = Blueprint('lists', __name__)


@lists_bp.route('/api/test')
def api_test():
    """Simple test endpoint to verify API is working"""
    return jsonify({'success': True, 'message': 'API is working'})


def login_required(f):
    """Decorator to require authentication for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_app.get_current_user():
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


@lists_bp.route('/')
@login_required
def manage_lists():
    """Main list management page"""
    config = current_app.mail_config
    all_lists = config.get_all_lists()
    metadata = config.get_list_metadata()
    
    return render_template('lists/manage.html', 
                         lists=all_lists,
                         metadata=metadata)


@lists_bp.route('/api/data')
@login_required 
def api_get_all_data():
    """API endpoint to get all list data with conflict detection"""
    try:
        config = current_app.mail_config
        all_lists = config.get_all_lists()
        metadata = config.get_list_metadata()
        
        # Load list contents
        list_data = {}
        for list_name, list_path in all_lists.items():
            try:
                entries = pf.open_read(str(list_path))
                # Filter out empty/whitespace-only entries
                filtered_entries = [e.strip() for e in entries if e.strip()]
                list_data[list_name] = {
                    'entries': filtered_entries,
                    'metadata': metadata[list_name]
                }
            except Exception as e:
                current_app.logger.error(f"Error loading list {list_name}: {e}")
                list_data[list_name] = {
                    'entries': [],
                    'metadata': metadata[list_name]
                }
        
        # Detect conflicts
        conflicts = detect_conflicts(list_data)
        
        return jsonify({
            'success': True,
            'lists': list_data,
            'conflicts': conflicts
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in api_get_all_data: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@lists_bp.route('/api/add/<list_name>', methods=['POST'])
@login_required
def api_add_entry(list_name):
    """Add email address to specific list"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        
        if not email:
            return jsonify({'success': False, 'error': 'Email address required'}), 400
        
        # Validate email format (basic)
        if '@' not in email or '.' not in email:
            return jsonify({'success': False, 'error': 'Invalid email format'}), 400
        
        config = current_app.mail_config
        all_lists = config.get_all_lists()
        
        if list_name not in all_lists:
            return jsonify({'success': False, 'error': f'List {list_name} not found'}), 404
        
        # Add to list using existing function
        list_path = str(all_lists[list_name])
        
        # Check if already exists
        existing_entries = pf.open_read(list_path)
        if email in existing_entries:
            return jsonify({'success': False, 'error': 'Email already in list'}), 400
        
        # Add entry
        with open(list_path, 'a') as f:
            f.write(f'{email}\n')
        
        # Clean up blanks
        pf.rm_blanks(list_path)
        
        return jsonify({
            'success': True,
            'message': f'Added {email} to {list_name}'
        })
        
    except Exception as e:
        current_app.logger.error(f"Error adding entry: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@lists_bp.route('/api/remove/<list_name>', methods=['DELETE'])
@login_required
def api_remove_entry(list_name):
    """Remove email address from specific list"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        
        if not email:
            return jsonify({'success': False, 'error': 'Email address required'}), 400
        
        config = current_app.mail_config
        all_lists = config.get_all_lists()
        
        if list_name not in all_lists:
            return jsonify({'success': False, 'error': f'List {list_name} not found'}), 404
        
        # Remove from list using existing function
        pf.remove_entry(email, str(all_lists[list_name]))
        
        return jsonify({
            'success': True,
            'message': f'Removed {email} from {list_name}'
        })
        
    except Exception as e:
        current_app.logger.error(f"Error removing entry: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@lists_bp.route('/api/move', methods=['POST'])
@login_required  
def api_move_entry():
    """Move email address between lists"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        from_list = data.get('from_list')
        to_list = data.get('to_list')
        
        if not all([email, from_list, to_list]):
            return jsonify({'success': False, 'error': 'Email, from_list, and to_list required'}), 400
        
        config = current_app.mail_config
        all_lists = config.get_all_lists()
        
        if from_list not in all_lists or to_list not in all_lists:
            return jsonify({'success': False, 'error': 'Invalid list names'}), 404
        
        # Remove from source list
        pf.remove_entry(email, str(all_lists[from_list]))
        
        # Add to destination list
        with open(str(all_lists[to_list]), 'a') as f:
            f.write(f'{email}\n')
        
        # Clean up both lists
        pf.rm_blanks(str(all_lists[from_list]))
        pf.rm_blanks(str(all_lists[to_list]))
        
        return jsonify({
            'success': True,
            'message': f'Moved {email} from {from_list} to {to_list}'
        })
        
    except Exception as e:
        current_app.logger.error(f"Error moving entry: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@lists_bp.route('/api/conflicts')
@login_required
def api_get_conflicts():
    """Get current conflicts between lists"""
    try:
        config = current_app.mail_config
        all_lists = config.get_all_lists()
        
        # Load list contents
        list_data = {}
        for list_name, list_path in all_lists.items():
            try:
                entries = pf.open_read(str(list_path))
                list_data[list_name] = {'entries': entries}
            except Exception:
                list_data[list_name] = {'entries': []}
        
        conflicts = detect_conflicts(list_data)
        
        return jsonify({
            'success': True,
            'conflicts': conflicts
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting conflicts: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def detect_conflicts(list_data):
    """Detect conflicts between all lists"""
    conflicts = {}
    list_names = list(list_data.keys())
    
    # Compare each pair of lists
    for i, list1 in enumerate(list_names):
        for list2 in list_names[i+1:]:
            entries1 = set(list_data[list1]['entries'])
            entries2 = set(list_data[list2]['entries'])
            
            common = entries1.intersection(entries2)
            if common:
                conflict_key = f"{list1}_vs_{list2}"
                conflicts[conflict_key] = {
                    'lists': [list1, list2],
                    'emails': list(common)
                }
    
    return conflicts