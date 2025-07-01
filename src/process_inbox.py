import rules as r
import functions as pf
from config import get_config

def process_rules_with_retention(account, folder="INBOX"):
    """
    Process emails through the new rules engine and handle retention policies
    
    Args:
        account: Account object
        folder: Folder to process (default: INBOX)
        
    Returns:
        dict: Processing results including retention operations
    """
    log = {}
    log["process"] = "Rules and Retention Processing"
    
    try:
        # Load active rules for this account
        active_rules = r.load_active_rules_for_account(account.email)
        log["active_rules_count"] = len(active_rules)
        
        if not active_rules:
            log["warning"] = "No active rules found for account"
            return log
        
        # Process each rule
        total_processed = 0
        rules_with_retention = []
        
        for rule in active_rules:
            try:
                processed_count = rule.process_emails(account, folder=folder)
                total_processed += processed_count
                log[f"rule_{rule.id}_processed"] = processed_count
                
                # Check if rule has retention settings
                if rule.has_retention_actions():
                    rules_with_retention.append(rule)
                    log[f"rule_{rule.id}_has_retention"] = True
                
            except Exception as e:
                log[f"rule_{rule.id}_error"] = str(e)
        
        log["total_emails_processed"] = total_processed
        log["rules_with_retention_count"] = len(rules_with_retention)
        
        # Create/update retention policies for rules with retention settings
        if rules_with_retention:
            try:
                from retention import RetentionPolicyManager
                config = get_config()
                retention_manager = RetentionPolicyManager(config.config_dir)
                
                # Auto-create retention policies from rules
                rules_engine = r.RulesEngine()
                created_policies = rules_engine.create_retention_policies_from_rules(retention_manager)
                log["retention_policies_created"] = len(created_policies)
                
                # Execute retention for newly moved emails if any policies were created or updated
                if created_policies:
                    from retention import RetentionScheduler
                    scheduler = RetentionScheduler(retention_manager)
                    
                    # Run manual retention for this account only
                    retention_results = scheduler.run_manual_retention(
                        account_email=account.email,
                        dry_run=False
                    )
                    
                    log["retention_operations"] = len(retention_results)
                    log["retention_results"] = [
                        {
                            "stage": result.stage.value,
                            "policy_id": result.policy_id,
                            "emails_affected": result.emails_affected,
                            "success": result.success
                        }
                        for result in retention_results
                    ]
                
            except ImportError:
                log["retention_warning"] = "Retention system not available"
            except Exception as e:
                log["retention_error"] = str(e)
        
        return log
        
    except Exception as e:
        log["error"] = str(e)
        return log

def process_inbox(account, folder="INBOX", limit=100):
    """
    Fetches mail from specified server/account and folder.  Compares the from_ attribute against specified sender lists.
    If a sender matches an address in a specified list, message is dispositioned according to defined rules.  If no match,
    mail is sent to Pending folder.
    """
    # Process special rules (legacy system)
    for rule in r.rules_list:
        rule(account)
    
    mail_list = []
    log = {}
    log["process"] = "Process Inbox"
    
    # Process new rules engine with retention
    try:
        rules_log = process_rules_with_retention(account, folder)
        log["rules_processing"] = rules_log
    except Exception as e:
        log["rules_processing_error"] = str(e)
    # Load Lists using configuration
    whitelist = pf.open_read("white")
    blacklist = pf.open_read("black")
    vendorlist = pf.open_read("vendor")

    log["whitelist count"] = len(whitelist)
    log["blacklist count"] = len(blacklist)
    log["vendorlist count"] = len(vendorlist)
    #  Fetch mail
    mb = account.login()
    mail_list = pf.fetch_class(mb, limit=limit)

    log["mail_list count"] = len(mail_list)

    #  Build list of uids to move to defined folders
    whitelisted = [item.uid for item in mail_list if item.from_ in whitelist]
    blacklisted = [item.uid for item in mail_list if item.from_ in blacklist]
    vendorlist = [item.uid for item in mail_list if item.from_ in vendorlist]
    log["uids in whitelist"] = whitelisted
    log["uids in blacklist"] = blacklisted
    log["uids in vendorlist"] = vendorlist
    #  Move email using configured folder names
    config = get_config()
    account_config = None
    for acc in config.accounts:
        if acc.email == account.email:
            account_config = acc
            break
    
    if account_config and hasattr(account_config, 'folders'):
        processed_folder = account_config.folders.get('processed', 'INBOX.Processed')
        junk_folder = account_config.folders.get('junk', 'INBOX.Junk') 
        approved_ads_folder = account_config.folders.get('approved_ads', 'INBOX.Approved_Ads')
        pending_folder = account_config.folders.get('pending', 'INBOX.Pending')
    else:
        # Fallback to hardcoded names
        processed_folder = "INBOX.Processed"
        junk_folder = "INBOX.Junk"
        approved_ads_folder = "INBOX.Approved_Ads"
        pending_folder = "INBOX.Pending"
    
    # Use Gmail-aware processing if Gmail account
    if pf.is_gmail_account(account.email):
        # Gmail-specific processing with label cleanup
        if whitelisted:
            gmail_result = pf.gmail_aware_move(mb, whitelisted, processed_folder, 'INBOX')
            log["gmail_whitelist_result"] = gmail_result
        if blacklisted:
            gmail_result = pf.gmail_aware_move(mb, blacklisted, junk_folder, 'INBOX')
            log["gmail_blacklist_result"] = gmail_result
        if vendorlist:
            gmail_result = pf.gmail_aware_move(mb, vendorlist, approved_ads_folder, 'INBOX')
            log["gmail_vendor_result"] = gmail_result
    else:
        # Standard IMAP processing
        mb.move(whitelisted, processed_folder)
        mb.move(blacklisted, junk_folder)
        mb.move(vendorlist, approved_ads_folder)
    
    # Apply retention policy to approved_ads folder after moving vendor emails
    if vendorlist:  # Only if we moved any vendor emails
        try:
            config = get_config()
            retention_days = config.get_retention_setting('approved_ads')
            if retention_days > 0:
                pf.purge_old(mb, approved_ads_folder, retention_days)
                log["vendor_retention_applied"] = f"Purged vendor emails older than {retention_days} days"
        except Exception as e:
            log["vendor_retention_error"] = f"Could not apply vendor retention policy: {str(e)}"

    if folder == "INBOX":
        #  Build list of uids to move to Pending folder
        pending = [item.uid for item in mail_list if item.from_ not in whitelist if item.from_ not in blacklist if
                   item.from_ not in vendorlist]
        log["uids in pending"] = pending

        # Use Gmail-aware processing for pending messages
        if pf.is_gmail_account(account.email) and pending:
            gmail_result = pf.gmail_aware_move(mb, pending, pending_folder, 'INBOX')
            log["gmail_pending_result"] = gmail_result
        else:
            mb.move(pending, pending_folder)
    else:
        pass

    return log

def process_inbox_maint(account, folder="INBOX", limit=500):
    """
    Fetches mail from specified server/account and folder.  Compares the from_ attribute against specified sender lists.
    If a sender matches an address in a specified list, message is dispositioned according to defined rules.  If no match,
    mail is sent to Pending folder.
    """
    # Process special rules
    for rule in r.rules_list:
        rule(account)

    mail_list = []
    log = {}
    log["process"] = "Process Inbox"
    # Load Lists using configuration
    whitelist = pf.open_read("white")
    blacklist = pf.open_read("black")
    vendorlist = pf.open_read("vendor")

    log["whitelist count"] = len(whitelist)
    log["blacklist count"] = len(blacklist)
    log["vendorlist count"] = len(vendorlist)
    #  Fetch mail
    mb = account.login()
    mail_list = pf.fetch_class(mb, limit=limit)

    log["mail_list count"] = len(mail_list)

    #  Build list of uids to move to defined folders
    whitelisted = [item.uid for item in mail_list if item.from_ in whitelist]
    blacklisted = [item.uid for item in mail_list if item.from_ in blacklist]
    vendorlist = [item.uid for item in mail_list if item.from_ in vendorlist]
    log["uids in whitelist"] = whitelisted
    log["uids in blacklist"] = blacklisted
    log["uids in vendorlist"] = vendorlist
    #  Move email using configured folder names
    config = get_config()
    account_config = None
    for acc in config.accounts:
        if acc.email == account.email:
            account_config = acc
            break
    
    if account_config and hasattr(account_config, 'folders'):
        junk_folder = account_config.folders.get('junk', 'INBOX.Junk') 
        approved_ads_folder = account_config.folders.get('approved_ads', 'INBOX.Approved_Ads')
        pending_folder = account_config.folders.get('pending', 'INBOX.Pending')
    else:
        # Fallback to hardcoded names
        junk_folder = "INBOX.Junk"
        approved_ads_folder = "INBOX.Approved_Ads"
        pending_folder = "INBOX.Pending"
    
    # In maintenance mode, don't move whitelisted emails to processed
    # Use Gmail-aware processing if Gmail account
    if pf.is_gmail_account(account.email):
        # Gmail-specific processing with label cleanup
        if blacklisted:
            gmail_result = pf.gmail_aware_move(mb, blacklisted, junk_folder, 'INBOX')
            log["gmail_blacklist_result"] = gmail_result
        if vendorlist:
            gmail_result = pf.gmail_aware_move(mb, vendorlist, approved_ads_folder, 'INBOX')
            log["gmail_vendor_result"] = gmail_result
    else:
        # Standard IMAP processing
        mb.move(blacklisted, junk_folder)
        mb.move(vendorlist, approved_ads_folder)
    
    # Apply retention policy to approved_ads folder after moving vendor emails
    if vendorlist:  # Only if we moved any vendor emails
        try:
            retention_days = config.get_retention_setting('approved_ads')
            if retention_days > 0:
                pf.purge_old(mb, approved_ads_folder, retention_days)
                log["vendor_retention_applied"] = f"Purged vendor emails older than {retention_days} days"
        except Exception as e:
            log["vendor_retention_error"] = f"Could not apply vendor retention policy: {str(e)}"

    if folder == "INBOX":
        #  Build list of uids to move to Pending folder
        pending = [item.uid for item in mail_list if item.from_ not in whitelist if item.from_ not in blacklist if
                   item.from_ not in vendorlist]
        log["uids in pending"] = pending

        mb.move(pending, pending_folder)
    else:
        pass

    return log


def process_inbox_batch(account, folder="INBOX", limit=100):
    """
    Enhanced version of process_inbox that returns detailed batch processing results.
    Designed for manual batch processing with UI feedback.
    
    Returns:
        dict: Detailed processing results including counts and inbox status
    """
    # Get inbox count before processing
    mb = account.login()
    
    try:
        # Get total inbox count before processing
        initial_inbox_count = len(mb.fetch('ALL'))
    except Exception as e:
        initial_inbox_count = 0
    
    # Process the batch using existing logic
    log = process_inbox(account, folder, limit)
    
    # Get inbox count after processing
    try:
        mb = account.login()  # Reconnect to get fresh count
        final_inbox_count = len(mb.fetch('ALL'))
    except Exception as e:
        final_inbox_count = initial_inbox_count
    
    # Calculate processed counts from log
    whitelisted_count = len(log.get("uids in whitelist", []))
    blacklisted_count = len(log.get("uids in blacklist", []))
    vendor_count = len(log.get("uids in vendorlist", []))
    pending_count = len(log.get("uids in pending", []))
    
    # Build enhanced response
    batch_result = {
        'success': True,
        'batch_size': limit,
        'emails_processed': log.get("mail_list count", 0),
        'inbox_before': initial_inbox_count,
        'inbox_after': final_inbox_count,
        'inbox_remaining': final_inbox_count,
        'categories': {
            'whitelisted': whitelisted_count,
            'blacklisted': blacklisted_count,
            'vendor': vendor_count,
            'pending': pending_count
        },
        'folders': {
            'processed': whitelisted_count,
            'junk': blacklisted_count,
            'approved_ads': vendor_count,
            'pending': pending_count
        },
        'has_more': final_inbox_count > 0,
        'processing_log': log
    }
    
    return batch_result
