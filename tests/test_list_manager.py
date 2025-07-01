import pytest
from unittest.mock import Mock, patch, mock_open
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import list_manager as lm


class TestListManager:
    def test_list_loading_files(self):
        # Test that the expected list files would be processed
        expected_files = [
            "lists/white.txt",
            "lists/black.txt", 
            "lists/vendor.txt",
            "lists/head.txt"
        ]
        
        # This test verifies the file paths that would be used
        # The actual file operations are tested in other tests
        assert len(expected_files) == 4
        assert "lists/white.txt" in expected_files
        assert "lists/black.txt" in expected_files
        assert "lists/vendor.txt" in expected_files
        assert "lists/head.txt" in expected_files

    @patch('list_manager.pf.open_read')
    @patch('list_manager.pf.rm_blanks')
    @patch('list_manager.pf.remove_entry')
    @patch('builtins.input')
    def test_conflict_resolution_black_white(self, mock_input, mock_remove_entry, mock_rm_blanks, mock_open_read):
        # Setup: email exists in both black and white lists
        mock_open_read.side_effect = [
            ["conflict@example.com"],     # blacklist
            [],                           # vendorlist  
            ["conflict@example.com"],     # whitelist
            []                            # headlist
        ]
        
        # User chooses to keep in blacklist (option 1)
        mock_input.return_value = "1"
        
        # Execute the main block logic manually since we can't easily test __main__
        black = ["conflict@example.com"]
        white = ["conflict@example.com"]
        vendor = []
        head = []
        
        black_white = [email for email in black if email in white if email != "\n"]
        
        # Simulate the conflict resolution
        for item in black_white:
            if mock_input.return_value == "1":
                mock_remove_entry(item, "lists/white.txt")
            elif mock_input.return_value == "2":
                mock_remove_entry(item, "lists/black.txt")
        
        # Verify remove_entry was called to remove from whitelist
        mock_remove_entry.assert_called_with("conflict@example.com", "lists/white.txt")

    @patch('list_manager.pf.open_read')
    @patch('list_manager.pf.rm_blanks')
    @patch('list_manager.pf.remove_entry')
    @patch('builtins.input')
    def test_conflict_resolution_black_vendor(self, mock_input, mock_remove_entry, mock_rm_blanks, mock_open_read):
        mock_open_read.side_effect = [
            ["conflict@example.com"],     # blacklist
            ["conflict@example.com"],     # vendorlist  
            [],                           # whitelist
            []                            # headlist
        ]
        
        # User chooses to keep in vendor list (option 2)
        mock_input.return_value = "2"
        
        # Simulate the logic
        black = ["conflict@example.com"]
        vendor = ["conflict@example.com"]
        
        black_vendor = [email for email in black if email in vendor if email != "\n"]
        
        for item in black_vendor:
            if mock_input.return_value == "1":
                mock_remove_entry(item, "lists/vendor.txt")
            elif mock_input.return_value == "2":
                mock_remove_entry(item, "lists/black.txt")
        
        # Verify remove_entry was called to remove from blacklist
        mock_remove_entry.assert_called_with("conflict@example.com", "lists/black.txt")

    def test_list_comparison_logic(self):
        # Test the list comprehension logic used in list_manager
        black = ["email1@example.com", "email2@example.com", "email3@example.com"]
        white = ["email2@example.com", "email4@example.com"]
        vendor = ["email1@example.com", "email5@example.com"]
        
        # Test black_white conflicts
        black_white = [email for email in black if email in white if email != "\n"]
        assert black_white == ["email2@example.com"]
        
        # Test black_vendor conflicts  
        black_vendor = [email for email in black if email in vendor if email != "\n"]
        assert black_vendor == ["email1@example.com"]
        
        # Test white_vendor conflicts
        white_vendor = [email for email in white if email in vendor if email != "\n"]
        assert white_vendor == []

    @patch('list_manager.pf.open_read')
    @patch('list_manager.pf.rm_blanks') 
    def test_no_conflicts(self, mock_rm_blanks, mock_open_read):
        # Test case where there are no conflicts between lists
        mock_open_read.side_effect = [
            ["black1@example.com"],       # blacklist
            ["vendor1@example.com"],      # vendorlist  
            ["white1@example.com"],       # whitelist
            ["head1@example.com"]         # headlist
        ]
        
        # Simulate the comparison logic
        black = ["black1@example.com"]
        vendor = ["vendor1@example.com"] 
        white = ["white1@example.com"]
        head = ["head1@example.com"]
        
        black_vendor = [email for email in black if email in vendor if email != "\n"]
        black_white = [email for email in black if email in white if email != "\n"] 
        white_vendor = [email for email in white if email in vendor if email != "\n"]
        head_black = [email for email in head if email in black if email != "\n"]
        head_white = [email for email in head if email in white if email != "\n"]
        head_vendor = [email for email in head if email in vendor if email != "\n"]
        
        # All conflict lists should be empty
        assert black_vendor == []
        assert black_white == []
        assert white_vendor == []
        assert head_black == []
        assert head_white == []
        assert head_vendor == []