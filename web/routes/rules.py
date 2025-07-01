"""
Rules management routes for Mail-Rulez web interface

Handles custom email processing rules configuration.
"""

import sys
import uuid
from pathlib import Path
from flask import Blueprint, render_template, redirect, url_for, flash, current_app, request, jsonify
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, BooleanField, IntegerField, SubmitField, FieldList, FormField
from wtforms.validators import DataRequired, Length, NumberRange
from functools import wraps
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from rules import RulesEngine, EmailRule, RuleCondition, RuleAction, ConditionType, ActionType, RULE_TEMPLATES, create_rule_from_template


rules_bp = Blueprint('rules', __name__)


def login_required(f):
    """Decorator to require authentication for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_app.get_current_user():
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def get_rules_engine():
    """Get the rules engine instance - always reload to ensure fresh data"""
    # Always create a fresh instance to avoid caching stale rules
    # This ensures the web interface always shows the current state
    rules_file = current_app.mail_config.config_dir / 'rules.json'
    return RulesEngine(rules_file)


def ensure_list_files_exist(rule):
    """Ensure list files referenced in rule actions are created"""
    config = current_app.mail_config
    
    for action in rule.actions:
        if action.type == ActionType.ADD_TO_LIST:
            list_filename = action.target
            
            # If target doesn't end with .txt, add it
            if not list_filename.endswith('.txt'):
                list_filename = f"{list_filename}.txt"
            
            # Create the list file if it doesn't exist
            list_path = config.lists_dir / list_filename
            if not list_path.exists():
                try:
                    list_path.touch()
                    current_app.logger.info(f"Created list file: {list_path}")
                except Exception as e:
                    current_app.logger.error(f"Failed to create list file {list_path}: {e}")


def validate_rule(rule, exclude_rule_id=None):
    """
    Validate rule for common issues
    
    Args:
        rule: EmailRule object to validate
        exclude_rule_id: Rule ID to exclude from duplicate name check (for updates)
        
    Returns:
        tuple: (is_valid: bool, errors: list)
    """
    errors = []
    
    # Check for duplicate rule names
    rules_engine = get_rules_engine()
    existing_rules = rules_engine.get_all_rules()
    for existing_rule in existing_rules:
        if existing_rule.id != exclude_rule_id and existing_rule.name.lower() == rule.name.lower():
            errors.append(f"A rule with the name '{rule.name}' already exists")
            break
    
    # Validate folder actions
    config = current_app.mail_config
    accounts = config.accounts
    
    for action in rule.actions:
        if action.type == ActionType.MOVE_TO_FOLDER:
            folder_name = action.target
            
            # Check if folder name is valid (basic validation)
            if not folder_name or folder_name.strip() == "":
                errors.append("Folder name cannot be empty")
                continue
                
            # Check for invalid characters
            invalid_chars = ['<', '>', ':', '"', '|', '?', '*']
            if any(char in folder_name for char in invalid_chars):
                errors.append(f"Folder name '{folder_name}' contains invalid characters")
                continue
            
            # If rule is account-specific, validate folder exists in that account's configuration
            if rule.account_email:
                target_account = None
                for account in accounts:
                    if account.email == rule.account_email:
                        target_account = account
                        break
                
                if target_account and target_account.folders:
                    # Check if folder follows the account's folder structure
                    folder_values = list(target_account.folders.values())
                    folder_pattern_valid = False
                    
                    # Check if it matches existing folder patterns or is a sub-folder
                    for existing_folder in folder_values:
                        if existing_folder and (
                            folder_name == existing_folder or 
                            folder_name.startswith(existing_folder + '.') or
                            folder_name.startswith(existing_folder + '/') or
                            folder_name.startswith('INBOX.')
                        ):
                            folder_pattern_valid = True
                            break
                    
                    if not folder_pattern_valid and not folder_name.startswith('INBOX'):
                        errors.append(f"Folder '{folder_name}' does not follow the account's folder structure. Consider using a folder like 'INBOX.{folder_name.replace('INBOX.', '')}'")
    
    return len(errors) == 0, errors


class ConditionForm(FlaskForm):
    """Form for a single rule condition"""
    type = SelectField('Condition Type', choices=[
        (ConditionType.SENDER_CONTAINS.value, 'Sender Contains'),
        (ConditionType.SENDER_DOMAIN.value, 'Sender Domain'),
        (ConditionType.SENDER_EXACT.value, 'Sender Exact Match'),
        (ConditionType.SUBJECT_CONTAINS.value, 'Subject Contains'),
        (ConditionType.SUBJECT_EXACT.value, 'Subject Exact Match'),
        (ConditionType.SUBJECT_REGEX.value, 'Subject Regex'),
        (ConditionType.CONTENT_CONTAINS.value, 'Content Contains'),
        (ConditionType.SENDER_IN_LIST.value, 'Sender Is In List')
    ])
    value = StringField('Value', validators=[DataRequired()])
    case_sensitive = BooleanField('Case Sensitive')


class ActionForm(FlaskForm):
    """Form for a single rule action"""
    type = SelectField('Action Type', choices=[
        (ActionType.MOVE_TO_FOLDER.value, 'Move to Folder'),
        (ActionType.ADD_TO_LIST.value, 'Add to List'),
        (ActionType.CREATE_LIST.value, 'Create List'),
        (ActionType.SET_RETENTION.value, 'Set Retention Policy')
    ])
    target = StringField('Target', validators=[DataRequired()])
    # Retention-specific fields
    retention_days = IntegerField('Days before moving to trash', validators=[
        NumberRange(min=1, max=3650, message='Must be between 1 and 3650 days')
    ])
    trash_retention_days = IntegerField('Days to keep in trash', validators=[
        NumberRange(min=1, max=365, message='Must be between 1 and 365 days')
    ], default=7)
    skip_trash = BooleanField('Skip trash (immediate deletion)', default=False)


class RuleForm(FlaskForm):
    """Form for creating/editing rules"""
    name = StringField('Rule Name', validators=[
        DataRequired(),
        Length(min=2, max=100, message='Rule name must be between 2 and 100 characters')
    ])
    account_email = SelectField('Apply to Account', validators=[DataRequired()], choices=[])
    description = TextAreaField('Description', validators=[
        Length(max=500, message='Description must be less than 500 characters')
    ])
    condition_logic = SelectField('Condition Logic', choices=[
        ('AND', 'All conditions must match (AND)'),
        ('OR', 'Any condition can match (OR)')
    ], default='AND')
    priority = IntegerField('Priority', validators=[
        NumberRange(min=1, max=1000, message='Priority must be between 1 and 1000')
    ], default=100)
    active = BooleanField('Active', default=True)
    
    conditions = FieldList(FormField(ConditionForm), min_entries=1)
    actions = FieldList(FormField(ActionForm), min_entries=1)
    
    submit = SubmitField('Save Rule')


@rules_bp.route('/')
@login_required
def list_rules():
    """List all configured rules"""
    rules_engine = get_rules_engine()
    rules = rules_engine.get_all_rules()
    return render_template('rules/list.html', rules=rules, templates=RULE_TEMPLATES)


@rules_bp.route('/add')
@login_required
def add_rule():
    """Add a new rule"""
    # Get available accounts for the dropdown using fresh config
    try:
        from config import Config
        fresh_config = Config(current_app.mail_config.base_dir, current_app.mail_config.config_file, current_app.mail_config.use_encryption)
        accounts = fresh_config.accounts
        current_app.logger.info(f"Loaded {len(accounts)} accounts for rule creation")
    except Exception as e:
        current_app.logger.error(f"Error loading accounts for rule creation: {e}")
        accounts = []
    
    account_choices = [('', 'Select an Account')] + [(acc.email, f"{acc.name} ({acc.email})") for acc in accounts]
    
    return render_template('rules/add.html', templates=RULE_TEMPLATES, account_choices=account_choices)


@rules_bp.route('/add', methods=['POST'])
@login_required
def create_rule():
    """Create a new rule"""
    try:
        # Extract basic rule information
        name = request.form.get('name')
        account_email = request.form.get('account_email', '')
        description = request.form.get('description', '')
        condition_logic = request.form.get('condition_logic', 'AND')
        priority = int(request.form.get('priority', 100))
        active = 'active' in request.form
        
        # Extract conditions
        conditions = []
        condition_index = 0
        while f'conditions-{condition_index}-type' in request.form:
            condition_type = request.form.get(f'conditions-{condition_index}-type')
            condition_value = request.form.get(f'conditions-{condition_index}-value')
            case_sensitive = f'conditions-{condition_index}-case_sensitive' in request.form
            
            if condition_type and condition_value:
                conditions.append(RuleCondition(
                    type=ConditionType(condition_type),
                    value=condition_value,
                    case_sensitive=case_sensitive
                ))
            condition_index += 1
        
        # Extract actions
        actions = []
        action_index = 0
        while f'actions-{action_index}-type' in request.form:
            action_type = request.form.get(f'actions-{action_index}-type')
            action_target = request.form.get(f'actions-{action_index}-target')
            
            if action_type and action_target:
                # Extract retention parameters
                retention_days = request.form.get(f'actions-{action_index}-retention_days')
                trash_retention_days = request.form.get(f'actions-{action_index}-trash_retention_days')
                skip_trash = f'actions-{action_index}-skip_trash' in request.form
                
                # Convert retention parameters to integers if provided
                retention_days_int = int(retention_days) if retention_days and retention_days.strip() else None
                trash_retention_days_int = int(trash_retention_days) if trash_retention_days and trash_retention_days.strip() else None
                
                actions.append(RuleAction(
                    type=ActionType(action_type),
                    target=action_target,
                    retention_days=retention_days_int,
                    trash_retention_days=trash_retention_days_int,
                    skip_trash=skip_trash
                ))
            action_index += 1
        
        # Validate required fields
        if not name or not conditions or not actions:
            flash('Rule name, at least one condition, and at least one action are required', 'error')
            return redirect(url_for('rules.add_rule'))
        
        # Create rule for validation
        rule = EmailRule(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            conditions=conditions,
            actions=actions,
            account_email=account_email,
            condition_logic=condition_logic,
            priority=priority,
            active=active,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        
        # Validate rule
        is_valid, validation_errors = validate_rule(rule)
        if not is_valid:
            for error in validation_errors:
                flash(error, 'error')
            return redirect(url_for('rules.add_rule'))
        
        # Save rule
        rules_engine = get_rules_engine()
        rules_engine.add_rule(rule)
        
        # Ensure any list files referenced in actions are created
        ensure_list_files_exist(rule)
        
        flash(f'Rule "{rule.name}" created successfully!', 'success')
        return redirect(url_for('rules.list_rules'))
        
    except Exception as e:
        flash(f'Error creating rule: {str(e)}', 'error')
        return redirect(url_for('rules.add_rule'))


@rules_bp.route('/edit/<rule_id>')
@login_required
def edit_rule(rule_id):
    """Edit an existing rule"""
    rules_engine = get_rules_engine()
    rule = rules_engine.get_rule(rule_id)
    
    if not rule:
        flash('Rule not found', 'error')
        return redirect(url_for('rules.list_rules'))
    
    # Get available accounts for the dropdown using fresh config
    try:
        from config import Config
        fresh_config = Config(current_app.mail_config.base_dir, current_app.mail_config.config_file, current_app.mail_config.use_encryption)
        accounts = fresh_config.accounts
        current_app.logger.info(f"Loaded {len(accounts)} accounts for rule editing")
    except Exception as e:
        current_app.logger.error(f"Error loading accounts for rule editing: {e}")
        accounts = []
    
    account_choices = [('', 'Apply to All Accounts')] + [(acc.email, f"{acc.name} ({acc.email})") for acc in accounts]
    
    return render_template('rules/edit.html', rule=rule, account_choices=account_choices)


@rules_bp.route('/edit/<rule_id>', methods=['POST'])
@login_required
def update_rule(rule_id):
    """Update an existing rule"""
    rules_engine = get_rules_engine()
    existing_rule = rules_engine.get_rule(rule_id)
    
    if not existing_rule:
        flash('Rule not found', 'error')
        return redirect(url_for('rules.list_rules'))
    
    try:
        # Extract basic rule information
        name = request.form.get('name')
        account_email = request.form.get('account_email', '')
        description = request.form.get('description', '')
        condition_logic = request.form.get('condition_logic', 'AND')
        priority = int(request.form.get('priority', 100))
        active = 'active' in request.form
        
        # Extract conditions
        conditions = []
        condition_index = 0
        while f'conditions-{condition_index}-type' in request.form:
            condition_type = request.form.get(f'conditions-{condition_index}-type')
            condition_value = request.form.get(f'conditions-{condition_index}-value')
            case_sensitive = f'conditions-{condition_index}-case_sensitive' in request.form
            
            if condition_type and condition_value:
                conditions.append(RuleCondition(
                    type=ConditionType(condition_type),
                    value=condition_value,
                    case_sensitive=case_sensitive
                ))
            condition_index += 1
        
        # Extract actions
        actions = []
        action_index = 0
        while f'actions-{action_index}-type' in request.form:
            action_type = request.form.get(f'actions-{action_index}-type')
            action_target = request.form.get(f'actions-{action_index}-target')
            
            if action_type and action_target:
                # Extract retention parameters
                retention_days = request.form.get(f'actions-{action_index}-retention_days')
                trash_retention_days = request.form.get(f'actions-{action_index}-trash_retention_days')
                skip_trash = f'actions-{action_index}-skip_trash' in request.form
                
                # Convert retention parameters to integers if provided
                retention_days_int = int(retention_days) if retention_days and retention_days.strip() else None
                trash_retention_days_int = int(trash_retention_days) if trash_retention_days and trash_retention_days.strip() else None
                
                actions.append(RuleAction(
                    type=ActionType(action_type),
                    target=action_target,
                    retention_days=retention_days_int,
                    trash_retention_days=trash_retention_days_int,
                    skip_trash=skip_trash
                ))
            action_index += 1
        
        # Validate required fields
        if not name or not conditions or not actions:
            flash('Rule name, at least one condition, and at least one action are required', 'error')
            return redirect(url_for('rules.edit_rule', rule_id=rule_id))
        
        # Create updated rule for validation
        updated_rule = EmailRule(
            id=rule_id,
            name=name,
            description=description,
            conditions=conditions,
            actions=actions,
            account_email=account_email,
            condition_logic=condition_logic,
            priority=priority,
            active=active,
            created_at=existing_rule.created_at,
            updated_at=datetime.now().isoformat()
        )
        
        # Validate rule (exclude current rule from duplicate name check)
        is_valid, validation_errors = validate_rule(updated_rule, exclude_rule_id=rule_id)
        if not is_valid:
            for error in validation_errors:
                flash(error, 'error')
            return redirect(url_for('rules.edit_rule', rule_id=rule_id))
        
        # Save rule
        rules_engine.update_rule(rule_id, updated_rule)
        
        # Ensure any list files referenced in actions are created
        ensure_list_files_exist(updated_rule)
        
        flash(f'Rule "{updated_rule.name}" updated successfully!', 'success')
        return redirect(url_for('rules.list_rules'))
        
    except Exception as e:
        flash(f'Error updating rule: {str(e)}', 'error')
        return redirect(url_for('rules.edit_rule', rule_id=rule_id))


@rules_bp.route('/delete/<rule_id>', methods=['POST'])
@login_required
def delete_rule(rule_id):
    """Delete a rule"""
    try:
        rules_engine = get_rules_engine()
        rule = rules_engine.get_rule(rule_id)
        
        if not rule:
            flash('Rule not found', 'error')
        else:
            rules_engine.delete_rule(rule_id)
            flash(f'Rule "{rule.name}" deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting rule: {str(e)}', 'error')
    
    return redirect(url_for('rules.list_rules'))


@rules_bp.route('/template/<template_name>')
@login_required
def create_from_template(template_name):
    """Create a rule from a template"""
    try:
        rule = create_rule_from_template(template_name, str(uuid.uuid4()))
        
        if not rule:
            flash('Template not found', 'error')
            return redirect(url_for('rules.list_rules'))
        
        # Set timestamps
        rule.created_at = datetime.now().isoformat()
        rule.updated_at = datetime.now().isoformat()
        
        # Save rule
        rules_engine = get_rules_engine()
        rules_engine.add_rule(rule)
        
        # Ensure any list files referenced in actions are created
        ensure_list_files_exist(rule)
        
        flash(f'Rule "{rule.name}" created from template!', 'success')
        
    except Exception as e:
        flash(f'Error creating rule from template: {str(e)}', 'error')
    
    return redirect(url_for('rules.list_rules'))


@rules_bp.route('/api/test', methods=['POST'])
@login_required
def test_rule():
    """Test a rule against sample email data"""
    try:
        data = request.get_json()
        rule_data = data.get('rule')
        email_data = data.get('email')
        
        # Create temporary rule for testing
        conditions = []
        for cond_data in rule_data.get('conditions', []):
            conditions.append(RuleCondition(
                type=ConditionType(cond_data['type']),
                value=cond_data['value'],
                case_sensitive=cond_data.get('case_sensitive', False)
            ))
        
        actions = []
        for action_data in rule_data.get('actions', []):
            actions.append(RuleAction(
                type=ActionType(action_data['type']),
                target=action_data['target']
            ))
        
        rule = EmailRule(
            id='test',
            name='Test Rule',
            description='',
            conditions=conditions,
            actions=actions,
            condition_logic=rule_data.get('condition_logic', 'AND')
        )
        
        # Test rule
        matches = rule.matches(email_data)
        
        return jsonify({
            'success': True,
            'matches': matches,
            'actions': [{'type': action.type.value, 'target': action.target} for action in actions] if matches else []
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@rules_bp.route('/api/templates')
@login_required
def get_templates():
    """Get available rule templates"""
    return jsonify({
        'success': True,
        'templates': RULE_TEMPLATES
    })