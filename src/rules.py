"""
Rules Engine for Mail-Rulez

Provides flexible rule-based email processing with conditions and actions.
Supports sender-based, subject-based, and content-based rules.
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, asdict
from enum import Enum


class ConditionType(Enum):
    """Types of rule conditions"""
    SENDER_CONTAINS = "sender_contains"
    SENDER_DOMAIN = "sender_domain"
    SENDER_EXACT = "sender_exact"
    SUBJECT_CONTAINS = "subject_contains"
    SUBJECT_EXACT = "subject_exact"
    SUBJECT_REGEX = "subject_regex"
    CONTENT_CONTAINS = "content_contains"
    SENDER_IN_LIST = "sender_in_list"


class ActionType(Enum):
    """Types of rule actions"""
    MOVE_TO_FOLDER = "move_to_folder"
    ADD_TO_LIST = "add_to_list"
    CREATE_LIST = "create_list"
    FORWARD = "forward"
    MARK_READ = "mark_read"
    SET_RETENTION = "set_retention"


@dataclass
class RuleCondition:
    """A single condition in a rule"""
    type: ConditionType
    value: str
    case_sensitive: bool = False
    
    def matches(self, email_data: Dict[str, Any]) -> bool:
        """Check if this condition matches the email data"""
        if self.type == ConditionType.SENDER_CONTAINS:
            sender = email_data.get('from', '').lower() if not self.case_sensitive else email_data.get('from', '')
            value = self.value.lower() if not self.case_sensitive else self.value
            return value in sender
            
        elif self.type == ConditionType.SENDER_DOMAIN:
            sender = email_data.get('from', '')
            # Extract domain from email address
            if '@' in sender:
                domain = sender.split('@')[-1].strip('>')
                return domain.lower() == self.value.lower()
            return False
            
        elif self.type == ConditionType.SENDER_EXACT:
            sender = email_data.get('from', '')
            if not self.case_sensitive:
                return sender.lower() == self.value.lower()
            return sender == self.value
            
        elif self.type == ConditionType.SUBJECT_CONTAINS:
            subject = email_data.get('subject', '').lower() if not self.case_sensitive else email_data.get('subject', '')
            value = self.value.lower() if not self.case_sensitive else self.value
            return value in subject
            
        elif self.type == ConditionType.SUBJECT_EXACT:
            subject = email_data.get('subject', '')
            if not self.case_sensitive:
                return subject.lower() == self.value.lower()
            return subject == self.value
            
        elif self.type == ConditionType.SUBJECT_REGEX:
            subject = email_data.get('subject', '')
            flags = 0 if self.case_sensitive else re.IGNORECASE
            try:
                return bool(re.search(self.value, subject, flags))
            except re.error:
                return False
                
        elif self.type == ConditionType.CONTENT_CONTAINS:
            content = email_data.get('content', '').lower() if not self.case_sensitive else email_data.get('content', '')
            value = self.value.lower() if not self.case_sensitive else self.value
            return value in content
            
        elif self.type == ConditionType.SENDER_IN_LIST:
            sender = email_data.get('from', '')
            
            # Extract email address from sender (handle "Name <email@domain.com>" format)
            if '<' in sender and '>' in sender:
                sender_email = sender.split('<')[1].split('>')[0].strip()
            else:
                sender_email = sender.strip()
            
            # Load the specified list and check if sender is in it
            try:
                import functions as pf
                list_entries = pf.open_read(self.value)  # self.value contains list name/path
                # Case-insensitive email matching for reliability
                sender_email_lower = sender_email.lower()
                return sender_email_lower in [entry.lower() for entry in list_entries]
            except Exception as e:
                import logging
                logging.warning(f"Failed to check sender against list {self.value}: {e}")
                return False
            
        return False


@dataclass
class RuleAction:
    """A single action in a rule"""
    type: ActionType
    target: str
    parameters: Dict[str, Any] = None
    # Retention-specific parameters
    retention_days: Optional[int] = None
    trash_retention_days: Optional[int] = None
    skip_trash: bool = False
    
    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}
        
        # Ensure retention parameters are properly typed
        if self.retention_days is not None:
            self.retention_days = int(self.retention_days)
        if self.trash_retention_days is not None:
            self.trash_retention_days = int(self.trash_retention_days)
    
    def has_retention_settings(self) -> bool:
        """Check if this action has retention settings"""
        return (self.type == ActionType.SET_RETENTION or 
                self.retention_days is not None or 
                self.trash_retention_days is not None)


@dataclass
class EmailRule:
    """A complete email processing rule"""
    id: str
    name: str
    description: str
    conditions: List[RuleCondition]
    actions: List[RuleAction]
    account_email: str = ""  # Email account this rule applies to
    condition_logic: str = "AND"  # "AND" or "OR"
    active: bool = True
    priority: int = 100
    created_at: str = ""
    updated_at: str = ""
    
    def matches(self, email_data: Dict[str, Any]) -> bool:
        """Check if this rule matches the given email data"""
        if not self.active or not self.conditions:
            return False
            
        if self.condition_logic == "AND":
            return all(condition.matches(email_data) for condition in self.conditions)
        elif self.condition_logic == "OR":
            return any(condition.matches(email_data) for condition in self.conditions)
        else:
            # Default to AND logic
            return all(condition.matches(email_data) for condition in self.conditions)
    
    def has_retention_actions(self) -> bool:
        """Check if this rule has any retention-related actions"""
        return any(action.has_retention_settings() for action in self.actions)
    
    def get_retention_settings(self) -> Optional[Dict[str, Any]]:
        """Extract retention settings from rule actions"""
        for action in self.actions:
            if action.has_retention_settings():
                return {
                    'retention_days': action.retention_days,
                    'trash_retention_days': action.trash_retention_days or 7,
                    'skip_trash': action.skip_trash,
                    'target_folder': action.target if action.type == ActionType.MOVE_TO_FOLDER else None
                }
        return None

    def process_emails(self, account, folder="INBOX", limit=None):
        """
        Process emails in the specified folder against this rule
        
        Args:
            account: Account object with IMAP connection
            folder: IMAP folder to process (default: INBOX)  
            limit: Maximum number of emails to process
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Connect to IMAP
            mb = account.login()
            if not mb:
                logger.error(f"Failed to connect to IMAP for account {account.email}")
                return 0
                
            mb.folder.set(folder)
            
            # Fetch emails using existing function
            import functions as pf
            mail_list = pf.fetch_class(mb, folder=folder, limit=limit)
            
            processed_count = 0
            logger.info(f"Rule '{self.name}' processing {len(mail_list)} emails from {folder}")
            
            # Process each email
            for mail_item in mail_list:
                # Convert to format expected by rule conditions
                email_data = {
                    'from': mail_item.from_,
                    'subject': mail_item.subject,
                    'content': '',  # Would need full body for content rules
                    'date': mail_item.date
                }
                
                # Check if rule matches
                if self.matches(email_data):
                    logger.info(f"Rule '{self.name}' matched email from {mail_item.from_} with subject '{mail_item.subject}'")
                    # Execute all actions for this rule
                    for action in self.actions:
                        self._execute_action(action, mail_item, mb, account)
                    processed_count += 1
            
            mb.logout()
            logger.info(f"Rule '{self.name}' processed {processed_count} matching emails")
            return processed_count
            
        except Exception as e:
            logger.error(f"Error processing emails for rule {self.id}: {e}")
            if 'mb' in locals() and mb:
                try:
                    mb.logout()
                except:
                    pass
            return 0

    def _execute_action(self, action, mail_item, mailbox, account):
        """Execute a single rule action on an email"""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            if action.type == ActionType.MOVE_TO_FOLDER:
                logger.info(f"Moving email UID {mail_item.uid} to folder {action.target}")
                # Use existing move logic with Gmail support
                import functions as pf
                if pf.is_gmail_account(account.email):
                    pf.gmail_aware_move(mailbox, [mail_item.uid], action.target)
                else:
                    mailbox.move([mail_item.uid], action.target)
                    
            elif action.type == ActionType.ADD_TO_LIST:
                # Extract email address and add to list
                sender_email = mail_item.from_
                if '<' in sender_email and '>' in sender_email:
                    sender_email = sender_email.split('<')[1].split('>')[0].strip()
                
                logger.info(f"Adding {sender_email} to {action.target} list")
                import functions as pf
                # Add to specified list file
                pf.new_entries(action.target, [sender_email])
                
            elif action.type == ActionType.MARK_READ:
                logger.info(f"Marking email UID {mail_item.uid} as read")
                # Mark email as read
                mailbox.flag([mail_item.uid], ['\\Seen'], True)
                
            elif action.type == ActionType.SET_RETENTION:
                logger.info(f"Setting retention for email UID {mail_item.uid}: {action.retention_days} days")
                # Retention is handled separately during email processing
                # This action type is primarily for policy creation
                pass
                
            # Additional action types would be implemented here
            
        except Exception as e:
            logger.error(f"Error executing action {action.type} for rule {self.id}: {e}")


class RulesEngine:
    """Main rules engine for processing emails"""
    
    def __init__(self, rules_file: Path = None):
        if rules_file is None:
            # Store rules in the persistent config directory
            try:
                from config import get_config
                config = get_config()
                self.rules_file = config.config_dir / "rules.json"
            except Exception:
                # Fallback to current directory if config unavailable
                self.rules_file = Path("rules.json")
        else:
            self.rules_file = rules_file
        self.rules: List[EmailRule] = []
        self.load_rules()
    
    def load_rules(self):
        """Load rules from the rules file"""
        if not self.rules_file.exists():
            self.rules = []
            return
            
        try:
            with open(self.rules_file, 'r') as f:
                rules_data = json.load(f)
                
            self.rules = []
            for rule_data in rules_data:
                # Convert conditions
                conditions = []
                for cond_data in rule_data.get('conditions', []):
                    conditions.append(RuleCondition(
                        type=ConditionType(cond_data['type']),
                        value=cond_data['value'],
                        case_sensitive=cond_data.get('case_sensitive', False)
                    ))
                
                # Convert actions
                actions = []
                for action_data in rule_data.get('actions', []):
                    actions.append(RuleAction(
                        type=ActionType(action_data['type']),
                        target=action_data['target'],
                        parameters=action_data.get('parameters', {}),
                        retention_days=action_data.get('retention_days'),
                        trash_retention_days=action_data.get('trash_retention_days'),
                        skip_trash=action_data.get('skip_trash', False)
                    ))
                
                # Create rule
                rule = EmailRule(
                    id=rule_data['id'],
                    name=rule_data['name'],
                    description=rule_data['description'],
                    conditions=conditions,
                    actions=actions,
                    condition_logic=rule_data.get('condition_logic', 'AND'),
                    active=rule_data.get('active', True),
                    priority=rule_data.get('priority', 100),
                    created_at=rule_data.get('created_at', ''),
                    updated_at=rule_data.get('updated_at', '')
                )
                
                self.rules.append(rule)
                
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"Error loading rules: {e}")
            self.rules = []
    
    def save_rules(self):
        """Save rules to the rules file using atomic write"""
        import tempfile
        import os
        
        rules_data = []
        for rule in self.rules:
            rule_dict = asdict(rule)
            # Convert enums to strings
            for condition in rule_dict['conditions']:
                condition['type'] = condition['type'].value
            for action in rule_dict['actions']:
                action['type'] = action['type'].value
            rules_data.append(rule_dict)
        
        # Use atomic write: write to temp file, then rename
        # This prevents other processes from reading a partially written file
        temp_file = None
        try:
            # Create temp file in same directory as target file
            temp_fd, temp_file = tempfile.mkstemp(
                suffix='.tmp',
                prefix='rules_',
                dir=self.rules_file.parent
            )
            
            with os.fdopen(temp_fd, 'w') as f:
                json.dump(rules_data, f, indent=2)
            
            # Atomic rename
            os.rename(temp_file, self.rules_file)
            temp_file = None  # Successfully renamed, don't delete
            
        except Exception as e:
            # Clean up temp file if something went wrong
            if temp_file and os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except:
                    pass
            raise e
    
    def add_rule(self, rule: EmailRule):
        """Add a new rule"""
        self.rules.append(rule)
        self.rules.sort(key=lambda r: r.priority)
        self.save_rules()
    
    def update_rule(self, rule_id: str, updated_rule: EmailRule):
        """Update an existing rule"""
        for i, rule in enumerate(self.rules):
            if rule.id == rule_id:
                self.rules[i] = updated_rule
                self.rules.sort(key=lambda r: r.priority)
                self.save_rules()
                return True
        return False
    
    def delete_rule(self, rule_id: str):
        """Delete a rule"""
        self.rules = [rule for rule in self.rules if rule.id != rule_id]
        self.save_rules()
    
    def get_rule(self, rule_id: str) -> Optional[EmailRule]:
        """Get a rule by ID"""
        for rule in self.rules:
            if rule.id == rule_id:
                return rule
        return None
    
    def get_all_rules(self) -> List[EmailRule]:
        """Get all rules, sorted by priority"""
        return sorted(self.rules, key=lambda r: r.priority)
    
    def process_email(self, email_data: Dict[str, Any]) -> List[RuleAction]:
        """Process an email through all rules and return matching actions"""
        matching_actions = []
        
        for rule in self.get_all_rules():
            if rule.matches(email_data):
                matching_actions.extend(rule.actions)
                
        return matching_actions
    
    def create_retention_policies_from_rules(self, retention_manager=None):
        """
        Create retention policies automatically from rules that have retention settings
        
        Args:
            retention_manager: RetentionPolicyManager instance (optional)
        """
        if retention_manager is None:
            try:
                from retention import RetentionPolicyManager
                from config import get_config
                config = get_config()
                retention_manager = RetentionPolicyManager(config.config_dir)
            except ImportError:
                print("Retention system not available")
                return
        
        import logging
        logger = logging.getLogger(__name__)
        
        created_policies = []
        
        for rule in self.get_all_rules():
            if rule.has_retention_actions():
                try:
                    # Check if a policy already exists for this rule
                    existing_policy = retention_manager.settings.get_policy_by_rule_id(rule.id)
                    if existing_policy:
                        logger.info(f"Retention policy already exists for rule {rule.id}")
                        continue
                    
                    retention_settings = rule.get_retention_settings()
                    if not retention_settings or not retention_settings.get('retention_days'):
                        continue
                    
                    # Create retention policy
                    policy = retention_manager.create_rule_policy(
                        rule_id=rule.id,
                        retention_days=retention_settings['retention_days'],
                        name=f"Auto: {rule.name}",
                        description=f"Automatically created from rule: {rule.description}",
                        trash_retention_days=retention_settings['trash_retention_days']
                    )
                    
                    created_policies.append(policy)
                    logger.info(f"Created retention policy {policy.id} for rule {rule.id}")
                    
                except Exception as e:
                    logger.error(f"Failed to create retention policy for rule {rule.id}: {e}")
        
        return created_policies
    
    def get_rules_with_retention(self) -> List[EmailRule]:
        """Get all rules that have retention settings"""
        return [rule for rule in self.get_all_rules() if rule.has_retention_actions()]


# Pre-built rule templates
RULE_TEMPLATES = {
    "package_delivery": {
        "name": "Package Delivery",
        "description": "Automatically organize package delivery notifications with 90-day retention",
        "conditions": [
            {
                "type": ConditionType.SENDER_DOMAIN,
                "value": "fedex.com",
                "case_sensitive": False
            },
            {
                "type": ConditionType.SENDER_DOMAIN,
                "value": "ups.com",
                "case_sensitive": False
            },
            {
                "type": ConditionType.SENDER_DOMAIN,
                "value": "usps.com",
                "case_sensitive": False
            },
            {
                "type": ConditionType.SENDER_DOMAIN,
                "value": "amazon.com",
                "case_sensitive": False
            },
            {
                "type": ConditionType.SENDER_DOMAIN,
                "value": "dhl.com",
                "case_sensitive": False
            }
        ],
        "actions": [
            {
                "type": ActionType.MOVE_TO_FOLDER,
                "target": "INBOX.Packages",
                "retention_days": 90,
                "trash_retention_days": 14
            },
            {
                "type": ActionType.ADD_TO_LIST,
                "target": "packages.txt"
            }
        ],
        "condition_logic": "OR",
        "priority": 50
    },
    
    "receipts_invoices": {
        "name": "Receipts & Invoices",
        "description": "Organize financial documents and receipts",
        "conditions": [
            {
                "type": ConditionType.SUBJECT_CONTAINS,
                "value": "invoice",
                "case_sensitive": False
            },
            {
                "type": ConditionType.SUBJECT_CONTAINS,
                "value": "receipt",
                "case_sensitive": False
            },
            {
                "type": ConditionType.SUBJECT_CONTAINS,
                "value": "bill",
                "case_sensitive": False
            },
            {
                "type": ConditionType.SUBJECT_CONTAINS,
                "value": "statement",
                "case_sensitive": False
            },
            {
                "type": ConditionType.SUBJECT_CONTAINS,
                "value": "payment",
                "case_sensitive": False
            }
        ],
        "actions": [
            {
                "type": ActionType.MOVE_TO_FOLDER,
                "target": "INBOX.Receipts"
            },
            {
                "type": ActionType.ADD_TO_LIST,
                "target": "receipts.txt"
            }
        ],
        "condition_logic": "OR",
        "priority": 60
    },
    
    "linkedin": {
        "name": "LinkedIn Notifications",
        "description": "Organize LinkedIn professional networking emails with 30-day retention",
        "conditions": [
            {
                "type": ConditionType.SENDER_DOMAIN,
                "value": "linkedin.com",
                "case_sensitive": False
            }
        ],
        "actions": [
            {
                "type": ActionType.MOVE_TO_FOLDER,
                "target": "INBOX.LinkedIn",
                "retention_days": 30,
                "trash_retention_days": 7
            },
            {
                "type": ActionType.ADD_TO_LIST,
                "target": "linkedin.txt"
            }
        ],
        "condition_logic": "AND",
        "priority": 70
    },
    
    "head_hunter": {
        "name": "Head Hunter Recruiters - Training Only", 
        "description": "Training folder rule for headhunter emails. Adds sender to head list and moves to HeadHunt folder. Use training folder INBOX._headhunter for manual categorization.",
        "conditions": [],
        "actions": [
            {
                "type": ActionType.ADD_TO_LIST,
                "target": "head.txt"
            },
            {
                "type": ActionType.MOVE_TO_FOLDER,
                "target": "INBOX.HeadHunt"
            }
        ],
        "condition_logic": "AND",
        "priority": 80
    },
    
    "newsletters_retention": {
        "name": "Newsletter Auto-Cleanup",
        "description": "Automatically clean up newsletter emails after 14 days",
        "conditions": [
            {
                "type": ConditionType.SUBJECT_CONTAINS,
                "value": "newsletter",
                "case_sensitive": False
            },
            {
                "type": ConditionType.SUBJECT_CONTAINS,
                "value": "unsubscribe",
                "case_sensitive": False
            },
            {
                "type": ConditionType.SUBJECT_CONTAINS,
                "value": "promotional",
                "case_sensitive": False
            }
        ],
        "actions": [
            {
                "type": ActionType.MOVE_TO_FOLDER,
                "target": "INBOX.Newsletters",
                "retention_days": 14,
                "trash_retention_days": 7
            },
            {
                "type": ActionType.ADD_TO_LIST,
                "target": "newsletters.txt"
            }
        ],
        "condition_logic": "OR",
        "priority": 40
    },
    
    "social_media_retention": {
        "name": "Social Media Notifications Cleanup",
        "description": "Clean up social media notifications after 7 days",
        "conditions": [
            {
                "type": ConditionType.SENDER_DOMAIN,
                "value": "facebook.com",
                "case_sensitive": False
            },
            {
                "type": ConditionType.SENDER_DOMAIN,
                "value": "twitter.com",
                "case_sensitive": False
            },
            {
                "type": ConditionType.SENDER_DOMAIN,
                "value": "instagram.com",
                "case_sensitive": False
            }
        ],
        "actions": [
            {
                "type": ActionType.MOVE_TO_FOLDER,
                "target": "INBOX.Social",
                "retention_days": 7,
                "trash_retention_days": 3
            }
        ],
        "condition_logic": "OR",
        "priority": 30
    }
}


def create_rule_from_template(template_name: str, rule_id: str) -> Optional[EmailRule]:
    """Create a rule from a pre-built template"""
    if template_name not in RULE_TEMPLATES:
        return None
        
    template = RULE_TEMPLATES[template_name]
    
    # Convert template conditions
    conditions = []
    for cond_data in template['conditions']:
        conditions.append(RuleCondition(
            type=cond_data['type'],
            value=cond_data['value'],
            case_sensitive=cond_data.get('case_sensitive', False)
        ))
    
    # Convert template actions
    actions = []
    for action_data in template['actions']:
        actions.append(RuleAction(
            type=action_data['type'],
            target=action_data['target'],
            parameters=action_data.get('parameters', {}),
            retention_days=action_data.get('retention_days'),
            trash_retention_days=action_data.get('trash_retention_days'),
            skip_trash=action_data.get('skip_trash', False)
        ))
    
    return EmailRule(
        id=rule_id,
        name=template['name'],
        description=template['description'],
        conditions=conditions,
        actions=actions,
        condition_logic=template.get('condition_logic', 'AND'),
        priority=template.get('priority', 100),
        active=True
    )


def load_active_rules_for_account(account_email: str) -> List[EmailRule]:
    """
    Load active rules for a specific account
    
    Args:
        account_email: Email address of the account
        
    Returns:
        list: List of active Rule objects for the account
    """
    try:
        # Ensure we use the same persistent config directory as the web interface
        rules_file = None
        try:
            from config import get_config
            config = get_config()
            rules_file = config.config_dir / "rules.json"
        except Exception:
            # Fallback if config unavailable
            pass
        
        manager = RulesEngine(rules_file)
        rules = manager.get_all_rules()
        
        # Filter for active rules that apply to this account or all accounts (empty account_email)
        active_rules = [
            rule for rule in rules 
            if rule.active and (rule.account_email == account_email or rule.account_email == "")
        ]
        
        return active_rules
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to load active rules for account {account_email}: {e}")
        return []


# Backward compatibility for old rules system
# The old system used @rule decorators and rules_list
# For now, provide an empty list to prevent crashes
rules_list = []