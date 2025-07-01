from imap_tools import MailBox
from datetime import datetime, timedelta
import smtplib, ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import os
import logging
from config import get_config
load_dotenv()

class Rule:
    def __init__(self):
        self.registry = []

    def __call__(self, m):
        "This method is called when some method is decorated"
        self.registry.append(m)

class Mail:
    def __init__(self, uid, subject, from_, date_str, date):
        self.uid = uid
        self.subject = subject
        self.from_ = from_
        self.date_str = date_str
        self.date = date


class Account():
    def __init__(self, server, email, password):
        self.server = server
        self.email = email
        self.password = password

    def login(self):
        """Login to server account, return mailbox object"""
        mb = MailBox(self.server).login(self.email, self.password)
        return mb

def fetch_class(login, folder="INBOX", age=None, limit=None):
    """
    Fetches messages from Account, classes them as Mail, changes date to date(), and returns list of those Mail
    :param limit: Maximum number of messages to fetch (None for all)
    :return: list of Mail
    """
    classed_mail = []
    login.folder.set(folder)
    batch = login.fetch(limit=limit, mark_seen=False, bulk=True, reverse=True, headers_only=True)
    for item in batch:
        item = Mail(item.uid, item.subject, item.from_, item.date_str, item.date)
        classed_mail.append(item)
    for item in classed_mail:
        item.date = item.date.date()
    return classed_mail


def purge_old(login, folder, age):
    """Purges all messages in specified folder over a specified age"""
    today = datetime.now().date()
    mail = fetch_class(login, folder=folder, age=age)
    purge = [item.uid for item in mail if today - item.date > timedelta(days=age)]
    login.delete(purge)


def rm_blanks(file):
    """
    Removes blank lines from email list file
    :param file: Can be a list name ('white', 'black', etc.) or full file path
    :return:
    """
    # If it's a list name, get the path from config
    # Check if it's a list name, get the path from config
    config = get_config()
    try:
        file = config.get_list_file_path(file)
    except ValueError:
        # If not a known list name, assume it's already a file path
        pass
    
    with open(file, "r+") as f:
        clean = [line for line in f.readlines() if line != "\n"]
        f.seek(0)
        for item in clean:
            f.writelines(item)
        f.truncate()


def open_read(file):
    """
    Open email list file and read contents into list
    :param file: Can be a list name ('white', 'black', etc.) or full file path
    :return: list of addresses
    """
    # If it's a list name, get the path from config
    if file in ['white', 'black', 'vendor', 'head']:
        config = get_config()
        file = config.get_list_file_path(file)
    
    with open(file, "r") as f:
        list_name = f.read().split("\n")
        f.close()
    return list_name


def remove_entry(item, file):
    """
    Removes a duplicate list entry from user-specified list
    :param item:
    :param file: Can be a list name ('white', 'black', etc.) or full file path
    :return:
    """
    # If it's a list name, get the path from config
    if file in ['white', 'black', 'vendor', 'head']:
        config = get_config()
        file = config.get_list_file_path(file)
    
    with open(file, "r") as f:
        lines = f.readlines()
    with open(file, "w") as g:
        for line in lines:
            if line.strip("\n") != item:
                g.write(line)


def new_entries(file, list):
    """
    Enters new list entries to file
    :param file: Can be a list name ('white', 'black', etc.) or full file path
    :param list:
    :return:
    """
    # If it's a list name, get the path from config
    if file in ['white', 'black', 'vendor', 'head']:
        config = get_config()
        file = config.get_list_file_path(file)
    
    with open(file, "a") as f:
        for entry in list:
            f.write(str(entry) + "\n")

def process_folder(list_file, account, start_folder, dest_folder):
    """
    Processes mail that was manually moved to a sorting folder.  Checks sender against appropriate list.  If sender is
    not in list, sender is added. All mail moved to dest folder.
    :param list_file: email list to check against
    :param server: account imap server
    :param account: account email address
    :param password: account pwd
    :param start_folder: folder to process
    :param dest_folder: dest folder for processed mail
    :return: log
    """
    log = {}
    log["process"] = start_folder
    #  Load List
    file_list = open_read(list_file)

    #  Fetch Mail
    mb = account.login()
    mail_list = fetch_class(mb, start_folder)

    #  New addresses added to list
    new_list_entries = set([item.from_ for item in mail_list if item.from_ not in file_list])
    new_entries(list_file, new_list_entries)
    rm_blanks(list_file)
    log["New entries Number"] = len(new_list_entries)
    log["New Entries Detail"] = new_list_entries

    #  All messages must be moved
    msgs_to_move = [item.uid for item in mail_list]
    
    # Use Gmail-aware move if Gmail account
    if is_gmail_account(account.email):
        gmail_result = gmail_aware_move(mb, msgs_to_move, dest_folder, start_folder)
        log["gmail_move_result"] = gmail_result
    else:
        mb.move(msgs_to_move, dest_folder)
    log["Messages Processed"] = len(msgs_to_move)
    log["Diff"] = len(mail_list) - len(msgs_to_move)

    # Apply retention policy to destination folder
    try:
        config = get_config()
        folder_type = _get_folder_type_from_name(dest_folder)
        if folder_type:
            retention_days = config.get_retention_setting(folder_type)
            if retention_days > 0:
                purge_old(mb, dest_folder, retention_days)
                log["retention_applied"] = f"Purged emails older than {retention_days} days from {dest_folder}"
    except Exception as e:
        log["retention_error"] = f"Could not apply retention policy: {str(e)}"

    now = datetime.now()
    format = "%Y-%m-%d %H:%M:%S"
    event_time = now.strftime(format)
    log["Date"] = event_time

    return log


def _get_folder_type_from_name(folder_name):
    """
    Determine folder type from folder name for retention policy lookup
    :param folder_name: IMAP folder name
    :return: folder type string or None
    """
    folder_lower = folder_name.lower()
    
    # Common folder name patterns
    folder_mappings = {
        'approved_ads': ['approved_ads', 'approvedads', 'vendor_ads', 'marketing'],
        'processed': ['processed', 'done', 'completed'],
        'pending': ['pending', 'review', 'undecided'],
        'junk': ['junk', 'spam', 'trash', 'deleted']
    }
    
    for folder_type, patterns in folder_mappings.items():
        for pattern in patterns:
            if pattern in folder_lower:
                return folder_type
    
    return None


def is_gmail_account(account_email):
    """
    Detect if account is Gmail-based by checking domain
    :param account_email: Email address string
    :return: True if Gmail account, False otherwise
    """
    if not account_email:
        return False
    
    gmail_domains = ['gmail.com', 'googlemail.com']
    account_domain = account_email.lower().split('@')[-1] if '@' in account_email else ''
    
    return account_domain in gmail_domains


def remove_gmail_label(mailbox, message_uids, label_name):
    """
    Remove specific label from Gmail messages
    :param mailbox: IMAP mailbox connection
    :param message_uids: List of message UIDs to process
    :param label_name: Gmail label/folder name to remove
    :return: Success count and error list
    """
    if not message_uids:
        return 0, []
    
    success_count = 0
    errors = []
    
    try:
        # Convert label name to Gmail format if needed
        gmail_label = label_name.replace('INBOX.', '') if label_name.startswith('INBOX.') else label_name
        
        # Process each message UID
        for uid in message_uids:
            try:
                # Use IMAP STORE command to remove Gmail label
                result = mailbox.client.uid('STORE', uid, '-X-GM-LABELS', f'"{gmail_label}"')
                if result[0] == 'OK':
                    success_count += 1
                else:
                    errors.append(f"UID {uid}: {result[1]}")
            except Exception as e:
                errors.append(f"UID {uid}: {str(e)}")
                logging.warning(f"Failed to remove label {gmail_label} from message {uid}: {e}")
    
    except Exception as e:
        logging.error(f"Error removing Gmail label {label_name}: {e}")
        errors.append(f"General error: {str(e)}")
    
    if errors:
        logging.warning(f"Gmail label removal had {len(errors)} errors out of {len(message_uids)} messages")
    
    return success_count, errors


def gmail_aware_move(mailbox, message_uids, destination_folder, source_folder=None):
    """
    Gmail-specific move that properly handles label cleanup
    
    :param mailbox: IMAP connection
    :param message_uids: List of message UIDs to move
    :param destination_folder: Target label/folder
    :param source_folder: Source label/folder to remove (optional)
    :return: Dict with move results and label cleanup stats
    """
    result = {
        'moved': 0,
        'label_removed': 0,
        'errors': []
    }
    
    if not message_uids:
        return result
    
    try:
        # First, perform the standard move operation (adds destination label)
        mailbox.move(message_uids, destination_folder)
        result['moved'] = len(message_uids)
        logging.info(f"Gmail: Moved {len(message_uids)} messages to {destination_folder}")
        
        # Then remove source label if specified (Gmail-specific cleanup)
        if source_folder and source_folder not in ['INBOX', 'Inbox']:
            success_count, errors = remove_gmail_label(mailbox, message_uids, source_folder)
            result['label_removed'] = success_count
            result['errors'].extend(errors)
            
            if success_count > 0:
                logging.info(f"Gmail: Removed {success_count} source labels '{source_folder}'")
            if errors:
                logging.warning(f"Gmail: Label removal had {len(errors)} errors")
    
    except Exception as e:
        error_msg = f"Gmail move operation failed: {str(e)}"
        result['errors'].append(error_msg)
        logging.error(error_msg)
    
    return result


def forward(account, sndr_to_fwd, fwd_addr, sent_mail):
    """
    This function will forward emails from a list of specified senders to a specified address.
    Messages that have been forwarded are logged as tuples (date, subject) and added to the sent_mail list.
    Messages that meet the sender criteria are checked against the sent_mail list to avoid duplicate sending.
    sent_mail list lives in memory and starts fresh each time mail_rulez_*.py is reloaded.
    It is hardcoded to work with jay@jay-cohen.info account as specified in the .env file.
    :param account: will be called from the mail_rulez_*.py module
    :param sndr_to_fwd: list.  sender addresses whose messages will be forwarded
    :param fwd_addr:  string.  address to which messages will be forwarded
    :param sent_mail:  list of mail already forwarded.  List of tuples (msg.date, msg.subject)
    :return:
    """
    account_email = os.getenv("account_email")
    smtp_server = os.getenv("smtp_server")
    smtp_port = os.getenv("smtp_port")
    password = os.getenv("password")

    login = account.login()
    for msg in login.fetch():
        if msg.from_ in sndr_to_fwd:
            mail_item = (msg.date, msg.subject)
            if mail_item not in sent_mail:
                sent_mail.append((msg.date, msg.subject))
                message = f"""----------------------------------<br>
        From:  {msg.from_}<br>
        To:  {msg.to}<br>
        Subject:  FWD: {msg.subject}<br><br>
    
        {msg.html}"""

                ######  EMAIL  #######

                mail = MIMEMultipart()
                mail["Subject"] = msg.subject
                mail["From"] = account_email
                mail["To"] = fwd_addr
                mail.attach(MIMEText(message, "html"))

                #  Try to connect to mailserver and send
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
                    server.login(account_email, password)
                    server.sendmail(account_email, fwd_addr, mail.as_string())
        else:
            continue