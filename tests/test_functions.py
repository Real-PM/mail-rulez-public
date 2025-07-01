import pytest
from unittest.mock import Mock, patch, mock_open
from datetime import datetime, date, timedelta
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from functions import Mail, Account, fetch_class, purge_old, rm_blanks, open_read, remove_entry, new_entries


class TestMail:
    def test_mail_creation(self):
        uid = "123"
        subject = "Test Subject"
        from_ = "test@example.com"
        date_str = "Mon, 01 Jan 2024 12:00:00 +0000"
        date_obj = datetime(2024, 1, 1, 12, 0, 0)
        
        mail = Mail(uid, subject, from_, date_str, date_obj)
        
        assert mail.uid == uid
        assert mail.subject == subject
        assert mail.from_ == from_
        assert mail.date_str == date_str
        assert mail.date == date_obj


class TestAccount:
    def test_account_creation(self):
        server = "imap.example.com"
        email = "test@example.com"
        password = "password123"
        
        account = Account(server, email, password)
        
        assert account.server == server
        assert account.email == email
        assert account.password == password

    @patch('functions.MailBox')
    def test_account_login(self, mock_mailbox):
        mock_mb = Mock()
        mock_mailbox.return_value.login.return_value = mock_mb
        
        account = Account("imap.example.com", "test@example.com", "password123")
        result = account.login()
        
        mock_mailbox.assert_called_once_with("imap.example.com")
        mock_mailbox.return_value.login.assert_called_once_with("test@example.com", "password123")
        assert result == mock_mb


class TestFetchClass:
    @patch('functions.Mail')
    def test_fetch_class(self, mock_mail_class):
        mock_login = Mock()
        mock_login.folder.set = Mock()
        
        mock_msg = Mock()
        mock_msg.uid = "123"
        mock_msg.subject = "Test"
        mock_msg.from_ = "test@example.com"
        mock_msg.date_str = "Mon, 01 Jan 2024 12:00:00 +0000"
        mock_msg.date = datetime(2024, 1, 1, 12, 0, 0)
        
        mock_login.fetch.return_value = [mock_msg]
        
        mock_mail_instance = Mock()
        mock_mail_instance.date = datetime(2024, 1, 1, 12, 0, 0)
        mock_mail_class.return_value = mock_mail_instance
        
        result = fetch_class(mock_login, folder="INBOX")
        
        mock_login.folder.set.assert_called_once_with("INBOX")
        mock_login.fetch.assert_called_once_with(limit=None, mark_seen=False, bulk=True, reverse=True, headers_only=True)
        mock_mail_class.assert_called_once_with("123", "Test", "test@example.com", "Mon, 01 Jan 2024 12:00:00 +0000", datetime(2024, 1, 1, 12, 0, 0))
        assert len(result) == 1
        assert result[0].date == date(2024, 1, 1)


class TestPurgeOld:
    @patch('functions.fetch_class')
    @patch('functions.datetime')
    def test_purge_old(self, mock_datetime, mock_fetch_class):
        mock_login = Mock()
        today = date(2024, 1, 15)
        mock_datetime.now.return_value.date.return_value = today
        
        old_mail = Mock()
        old_mail.uid = "123"
        old_mail.date = date(2024, 1, 1)  # 14 days old
        
        recent_mail = Mock()
        recent_mail.uid = "456"
        recent_mail.date = date(2024, 1, 10)  # 5 days old
        
        mock_fetch_class.return_value = [old_mail, recent_mail]
        
        purge_old(mock_login, "INBOX.Junk", 7)
        
        mock_fetch_class.assert_called_once_with(mock_login, folder="INBOX.Junk", age=7)
        mock_login.delete.assert_called_once_with(["123"])


class TestFileOperations:
    def test_rm_blanks(self):
        file_content = "test1@example.com\n\ntest2@example.com\n\n"
        expected_content = "test1@example.com\ntest2@example.com\n"
        
        with patch("builtins.open", mock_open(read_data=file_content)) as mock_file:
            rm_blanks("test_file.txt")
            
            handle = mock_file()
            handle.seek.assert_called_with(0)
            handle.writelines.assert_any_call("test1@example.com\n")
            handle.writelines.assert_any_call("test2@example.com\n")
            handle.truncate.assert_called_once()

    def test_open_read(self):
        file_content = "test1@example.com\ntest2@example.com\ntest3@example.com"
        expected_list = ["test1@example.com", "test2@example.com", "test3@example.com"]
        
        with patch("builtins.open", mock_open(read_data=file_content)):
            result = open_read("test_file.txt")
            
            assert result == expected_list

    def test_remove_entry(self):
        file_content = "test1@example.com\ntest2@example.com\ntest3@example.com\n"
        
        with patch("builtins.open", mock_open(read_data=file_content)) as mock_file:
            remove_entry("test2@example.com", "test_file.txt")
            
            handle = mock_file()
            handle.write.assert_any_call("test1@example.com\n")
            handle.write.assert_any_call("test3@example.com\n")

    def test_new_entries(self):
        new_list = ["test4@example.com", "test5@example.com"]
        
        with patch("builtins.open", mock_open()) as mock_file:
            new_entries("test_file.txt", new_list)
            
            handle = mock_file()
            handle.write.assert_any_call("test4@example.com\n")
            handle.write.assert_any_call("test5@example.com\n")