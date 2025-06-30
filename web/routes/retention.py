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
Retention policy management routes for Mail-Rulez web interface

Handles retention policy configuration, preview, and management.
"""

import sys
import json
from pathlib import Path
from flask import Blueprint, render_template, redirect, url_for, flash, current_app, request, jsonify
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, BooleanField, IntegerField, SubmitField, HiddenField
from wtforms.validators import DataRequired, Length, NumberRange, Optional
from functools import wraps
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import retention system components
from retention import (
    RetentionPolicyManager, 
    RetentionScheduler,
    RetentionPolicy,
    RetentionStage,
    RetentionError,
    PolicyNotFoundError,
    InvalidRetentionPeriodError
)

retention_bp = Blueprint('retention', __name__)


def login_required(f):
    """Decorator to require authentication for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_app.get_current_user():
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def get_retention_manager():
    """Get the retention policy manager instance"""
    config = current_app.mail_config
    return RetentionPolicyManager(config.config_dir)


def get_retention_scheduler():
    """Get the retention scheduler instance"""
    manager = get_retention_manager()
    return RetentionScheduler(manager)


class FolderPolicyForm(FlaskForm):
    """Form for creating/editing folder-level retention policies"""
    name = StringField('Policy Name', validators=[DataRequired(), Length(min=1, max=100)])
    description = TextAreaField('Description', validators=[Optional(), Length(max=500)])
    folder_pattern = StringField('Folder Pattern', validators=[DataRequired(), Length(min=1, max=100)])
    retention_days = IntegerField('Days before moving to trash', validators=[DataRequired(), NumberRange(min=1, max=3650)])
    trash_retention_days = IntegerField('Days to keep in trash', validators=[DataRequired(), NumberRange(min=1, max=365)])
    active = BooleanField('Active', default=True)
    submit = SubmitField('Save Policy')


class RulePolicyForm(FlaskForm):
    """Form for creating/editing rule-based retention policies"""
    name = StringField('Policy Name', validators=[DataRequired(), Length(min=1, max=100)])
    description = TextAreaField('Description', validators=[Optional(), Length(max=500)])
    rule_id = SelectField('Associated Rule', validators=[DataRequired()])
    retention_days = IntegerField('Days before moving to trash', validators=[DataRequired(), NumberRange(min=1, max=3650)])
    trash_retention_days = IntegerField('Days to keep in trash', validators=[DataRequired(), NumberRange(min=1, max=365)])
    active = BooleanField('Active', default=True)
    submit = SubmitField('Save Policy')


class RetentionPreviewForm(FlaskForm):
    """Form for retention preview operations"""
    account_email = SelectField('Account', validators=[Optional()])
    policy_id = SelectField('Policy', validators=[Optional()])
    submit = SubmitField('Generate Preview')


@retention_bp.route('/policies')
@login_required
def policies_overview():
    """Display overview of all retention policies"""
    try:
        manager = get_retention_manager()
        scheduler = get_retention_scheduler()
        
        # Get all policies
        all_policies = manager.settings.get_all_policies()
        folder_policies = [p for p in all_policies if p.folder_pattern]
        rule_policies = [p for p in all_policies if p.rule_id]
        
        # Get scheduler status
        scheduler_status = scheduler.get_scheduler_status()
        
        # Get recent audit activity
        recent_activity = []
        try:
            report = scheduler.generate_retention_report(days_back=7)
            recent_activity = report.get('retention_summary', {})
        except Exception as e:
            current_app.logger.warning(f"Could not load recent activity: {e}")
        
        return render_template('retention/policies_overview.html',
                             folder_policies=folder_policies,
                             rule_policies=rule_policies,
                             scheduler_status=scheduler_status,
                             recent_activity=recent_activity)
        
    except Exception as e:
        current_app.logger.error(f"Error loading retention policies: {e}")
        flash(f"Error loading retention policies: {str(e)}", 'error')
        return redirect(url_for('dashboard.index'))


@retention_bp.route('/policies/create/folder', methods=['GET', 'POST'])
@login_required
def create_folder_policy():
    """Create a new folder-level retention policy"""
    form = FolderPolicyForm()
    
    if form.validate_on_submit():
        try:
            manager = get_retention_manager()
            
            # Create the policy
            policy = manager.create_folder_policy(
                folder_pattern=form.folder_pattern.data,
                retention_days=form.retention_days.data,
                name=form.name.data,
                description=form.description.data,
                trash_retention_days=form.trash_retention_days.data
            )
            
            flash(f"Folder retention policy '{policy.name}' created successfully", 'success')
            return redirect(url_for('retention.policies_overview'))
            
        except InvalidRetentionPeriodError as e:
            flash(f"Invalid retention period: {str(e)}", 'error')
        except Exception as e:
            current_app.logger.error(f"Error creating folder policy: {e}")
            flash(f"Error creating policy: {str(e)}", 'error')
    
    return render_template('retention/create_folder_policy.html', form=form)


@retention_bp.route('/policies/create/rule', methods=['GET', 'POST'])
@login_required
def create_rule_policy():
    """Create a new rule-based retention policy"""
    form = RulePolicyForm()
    
    # Populate rule choices
    try:
        from rules import RulesEngine
        rules_file = current_app.mail_config.config_dir / 'rules.json'
        rules_engine = RulesEngine(rules_file)
        available_rules = rules_engine.get_all_rules()
        form.rule_id.choices = [(rule.id, rule.name) for rule in available_rules]
    except Exception as e:
        current_app.logger.warning(f"Could not load rules for dropdown: {e}")
        form.rule_id.choices = []
    
    if form.validate_on_submit():
        try:
            manager = get_retention_manager()
            
            # Create the policy
            policy = manager.create_rule_policy(
                rule_id=form.rule_id.data,
                retention_days=form.retention_days.data,
                name=form.name.data,
                description=form.description.data,
                trash_retention_days=form.trash_retention_days.data
            )
            
            flash(f"Rule retention policy '{policy.name}' created successfully", 'success')
            return redirect(url_for('retention.policies_overview'))
            
        except InvalidRetentionPeriodError as e:
            flash(f"Invalid retention period: {str(e)}", 'error')
        except Exception as e:
            current_app.logger.error(f"Error creating rule policy: {e}")
            flash(f"Error creating policy: {str(e)}", 'error')
    
    return render_template('retention/create_rule_policy.html', form=form)


@retention_bp.route('/policies/edit/<policy_id>', methods=['GET', 'POST'])
@login_required
def edit_policy(policy_id):
    """Edit an existing retention policy"""
    try:
        manager = get_retention_manager()
        policy = manager.settings.get_policy_by_id(policy_id)
        
        if not policy:
            flash(f"Policy {policy_id} not found", 'error')
            return redirect(url_for('retention.policies_overview'))
        
        # Use appropriate form based on policy type
        if policy.folder_pattern:
            form = FolderPolicyForm(obj=policy)
        else:
            form = RulePolicyForm(obj=policy)
            # Populate rule choices for rule policies
            try:
                from rules import RulesEngine
                rules_file = current_app.mail_config.config_dir / 'rules.json'
                rules_engine = RulesEngine(rules_file)
                available_rules = rules_engine.get_all_rules()
                form.rule_id.choices = [(rule.id, rule.name) for rule in available_rules]
            except Exception as e:
                current_app.logger.warning(f"Could not load rules for dropdown: {e}")
                form.rule_id.choices = []
        
        if form.validate_on_submit():
            try:
                # Prepare updates
                updates = {
                    'name': form.name.data,
                    'description': form.description.data,
                    'retention_days': form.retention_days.data,
                    'trash_retention_days': form.trash_retention_days.data,
                    'active': form.active.data
                }
                
                if hasattr(form, 'folder_pattern'):
                    updates['folder_pattern'] = form.folder_pattern.data
                if hasattr(form, 'rule_id'):
                    updates['rule_id'] = form.rule_id.data
                
                # Update the policy
                manager.update_policy(policy_id, **updates)
                
                flash(f"Policy '{policy.name}' updated successfully", 'success')
                return redirect(url_for('retention.policies_overview'))
                
            except InvalidRetentionPeriodError as e:
                flash(f"Invalid retention period: {str(e)}", 'error')
            except Exception as e:
                current_app.logger.error(f"Error updating policy: {e}")
                flash(f"Error updating policy: {str(e)}", 'error')
        
        return render_template('retention/edit_policy.html', form=form, policy=policy)
        
    except Exception as e:
        current_app.logger.error(f"Error loading policy for editing: {e}")
        flash(f"Error loading policy: {str(e)}", 'error')
        return redirect(url_for('retention.policies_overview'))


@retention_bp.route('/policies/delete/<policy_id>', methods=['POST'])
@login_required
def delete_policy(policy_id):
    """Delete a retention policy"""
    try:
        manager = get_retention_manager()
        policy = manager.settings.get_policy_by_id(policy_id)
        
        if not policy:
            flash(f"Policy {policy_id} not found", 'error')
        else:
            manager.delete_policy(policy_id)
            flash(f"Policy '{policy.name}' deleted successfully", 'success')
        
    except Exception as e:
        current_app.logger.error(f"Error deleting policy: {e}")
        flash(f"Error deleting policy: {str(e)}", 'error')
    
    return redirect(url_for('retention.policies_overview'))


@retention_bp.route('/policies/toggle/<policy_id>', methods=['POST'])
@login_required
def toggle_policy(policy_id):
    """Toggle a policy's active status"""
    try:
        manager = get_retention_manager()
        policy = manager.settings.get_policy_by_id(policy_id)
        
        if not policy:
            return jsonify({'error': 'Policy not found'}), 404
        
        # Toggle active status
        new_status = not policy.active
        manager.update_policy(policy_id, active=new_status)
        
        return jsonify({
            'success': True,
            'active': new_status,
            'message': f"Policy {'enabled' if new_status else 'disabled'}"
        })
        
    except Exception as e:
        current_app.logger.error(f"Error toggling policy: {e}")
        return jsonify({'error': str(e)}), 500


@retention_bp.route('/preview', methods=['GET', 'POST'])
@login_required
def retention_preview():
    """Preview retention operations before execution"""
    form = RetentionPreviewForm()
    
    # Populate account choices
    config = current_app.mail_config
    form.account_email.choices = [('', 'All Accounts')] + [(acc.email, acc.email) for acc in config.accounts]
    
    # Populate policy choices
    try:
        manager = get_retention_manager()
        all_policies = manager.settings.get_all_policies()
        form.policy_id.choices = [('', 'All Policies')] + [(p.id, p.name) for p in all_policies if p.active]
    except Exception as e:
        current_app.logger.warning(f"Could not load policies: {e}")
        form.policy_id.choices = [('', 'All Policies')]
    
    preview_data = None
    
    if form.validate_on_submit():
        try:
            manager = get_retention_manager()
            
            # Get the account to preview
            account_email = form.account_email.data or None
            policy_id = form.policy_id.data or None
            
            if account_email:
                # Find the specific account
                account = None
                for acc in config.accounts:
                    if acc.email == account_email:
                        account = acc
                        break
                
                if account:
                    preview_data = manager.get_retention_preview(account, policy_id)
                else:
                    flash(f"Account {account_email} not found", 'error')
            else:
                # Preview for all accounts
                preview_data = {
                    'accounts': [],
                    'summary': {
                        'total_emails_to_trash': 0,
                        'total_emails_to_delete': 0,
                        'total_folders_affected': set()
                    }
                }
                
                for account in config.accounts:
                    try:
                        account_preview = manager.get_retention_preview(account, policy_id)
                        preview_data['accounts'].append(account_preview)
                        
                        # Aggregate summary
                        summary = account_preview.get('summary', {})
                        preview_data['summary']['total_emails_to_trash'] += summary.get('emails_to_trash', 0)
                        preview_data['summary']['total_emails_to_delete'] += summary.get('emails_to_delete', 0)
                        preview_data['summary']['total_folders_affected'].update(summary.get('folders_affected', []))
                        
                    except Exception as e:
                        current_app.logger.warning(f"Could not preview for account {account.email}: {e}")
                
                # Convert set to list for template
                preview_data['summary']['total_folders_affected'] = list(preview_data['summary']['total_folders_affected'])
            
        except Exception as e:
            current_app.logger.error(f"Error generating retention preview: {e}")
            flash(f"Error generating preview: {str(e)}", 'error')
    
    return render_template('retention/preview.html', form=form, preview_data=preview_data)


@retention_bp.route('/execute', methods=['POST'])
@login_required
def execute_retention():
    """Execute retention policies with confirmation"""
    try:
        data = request.get_json()
        
        if not data or not data.get('confirmed'):
            return jsonify({'error': 'Operation not confirmed'}), 400
        
        account_email = data.get('account_email')
        policy_id = data.get('policy_id')
        dry_run = data.get('dry_run', False)
        
        manager = get_retention_manager()
        scheduler = get_retention_scheduler()
        
        # Execute retention
        results = scheduler.run_manual_retention(
            account_email=account_email,
            policy_id=policy_id,
            dry_run=dry_run
        )
        
        # Prepare response
        response = {
            'success': True,
            'dry_run': dry_run,
            'results': []
        }
        
        for result in results:
            response['results'].append({
                'stage': result.stage.value,
                'policy_id': result.policy_id,
                'folder': result.folder,
                'emails_processed': result.emails_processed,
                'emails_affected': result.emails_affected,
                'success': result.success,
                'error_message': result.error_message,
                'execution_time': result.execution_time_seconds
            })
        
        return jsonify(response)
        
    except Exception as e:
        current_app.logger.error(f"Error executing retention: {e}")
        return jsonify({'error': str(e)}), 500


@retention_bp.route('/scheduler/status')
@login_required
def scheduler_status():
    """Get retention scheduler status"""
    try:
        scheduler = get_retention_scheduler()
        status = scheduler.get_scheduler_status()
        return jsonify(status)
        
    except Exception as e:
        current_app.logger.error(f"Error getting scheduler status: {e}")
        return jsonify({'error': str(e)}), 500


@retention_bp.route('/scheduler/start', methods=['POST'])
@login_required
def start_scheduler():
    """Start the retention scheduler"""
    try:
        scheduler = get_retention_scheduler()
        success = scheduler.start_scheduler()
        
        if success:
            return jsonify({'success': True, 'message': 'Scheduler started successfully'})
        else:
            return jsonify({'error': 'Failed to start scheduler'}), 500
        
    except Exception as e:
        current_app.logger.error(f"Error starting scheduler: {e}")
        return jsonify({'error': str(e)}), 500


@retention_bp.route('/scheduler/stop', methods=['POST'])
@login_required
def stop_scheduler():
    """Stop the retention scheduler"""
    try:
        scheduler = get_retention_scheduler()
        success = scheduler.stop_scheduler()
        
        if success:
            return jsonify({'success': True, 'message': 'Scheduler stopped successfully'})
        else:
            return jsonify({'error': 'Failed to stop scheduler'}), 500
        
    except Exception as e:
        current_app.logger.error(f"Error stopping scheduler: {e}")
        return jsonify({'error': str(e)}), 500


@retention_bp.route('/audit')
@login_required
def audit_report():
    """Display retention audit report"""
    try:
        scheduler = get_retention_scheduler()
        days_back = request.args.get('days', 30, type=int)
        
        # Generate comprehensive report
        report = scheduler.generate_retention_report(days_back=days_back)
        
        return render_template('retention/audit_report.html', 
                             report=report, 
                             days_back=days_back)
        
    except Exception as e:
        current_app.logger.error(f"Error generating audit report: {e}")
        flash(f"Error generating audit report: {str(e)}", 'error')
        return redirect(url_for('retention.policies_overview'))


@retention_bp.route('/trash/<account_email>')
@login_required
def trash_contents(account_email):
    """Display trash contents for recovery"""
    try:
        config = current_app.mail_config
        
        # Find the account
        account = None
        for acc in config.accounts:
            if acc.email == account_email:
                account = acc
                break
        
        if not account:
            flash(f"Account {account_email} not found", 'error')
            return redirect(url_for('retention.policies_overview'))
        
        manager = get_retention_manager()
        trash_items = manager.trash_manager.get_trash_contents(account)
        
        return render_template('retention/trash_contents.html', 
                             account=account, 
                             trash_items=trash_items)
        
    except Exception as e:
        current_app.logger.error(f"Error loading trash contents: {e}")
        flash(f"Error loading trash contents: {str(e)}", 'error')
        return redirect(url_for('retention.policies_overview'))


@retention_bp.route('/trash/<account_email>/restore', methods=['POST'])
@login_required
def restore_from_trash(account_email):
    """Restore emails from trash"""
    try:
        data = request.get_json()
        message_uids = data.get('message_uids', [])
        target_folder = data.get('target_folder', 'INBOX')
        
        if not message_uids:
            return jsonify({'error': 'No messages selected'}), 400
        
        config = current_app.mail_config
        
        # Find the account
        account = None
        for acc in config.accounts:
            if acc.email == account_email:
                account = acc
                break
        
        if not account:
            return jsonify({'error': 'Account not found'}), 404
        
        manager = get_retention_manager()
        restored_count = manager.trash_manager.restore_from_trash(
            account=account,
            message_uids=message_uids,
            target_folder=target_folder
        )
        
        return jsonify({
            'success': True,
            'restored_count': restored_count,
            'message': f'Restored {restored_count} emails to {target_folder}'
        })
        
    except Exception as e:
        current_app.logger.error(f"Error restoring from trash: {e}")
        return jsonify({'error': str(e)}), 500