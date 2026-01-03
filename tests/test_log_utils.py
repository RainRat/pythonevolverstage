import sys
import os
import unittest
from unittest import mock

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestGetLatestLogEntry(unittest.TestCase):
    def setUp(self):
        # Save original BATTLE_LOG_FILE to restore later
        self.original_log_file = evolverstage.BATTLE_LOG_FILE
        # Set a dummy log file path for testing
        evolverstage.BATTLE_LOG_FILE = "dummy_log.csv"

    def tearDown(self):
        # Restore original log file path
        evolverstage.BATTLE_LOG_FILE = self.original_log_file

    @mock.patch('os.path.exists')
    def test_log_file_not_found(self, mock_exists):
        """Test behavior when the log file does not exist."""
        mock_exists.return_value = False
        result = evolverstage.get_latest_log_entry()
        self.assertEqual(result, "No battle log found.")

    @mock.patch('os.path.exists')
    def test_log_file_not_configured(self, _):
        """Test behavior when BATTLE_LOG_FILE is None or empty."""
        evolverstage.BATTLE_LOG_FILE = None
        result = evolverstage.get_latest_log_entry()
        self.assertEqual(result, "No battle log found.")

    @mock.patch('os.path.exists')
    def test_log_file_empty(self, mock_exists):
        """Test behavior when the log file is empty."""
        mock_exists.return_value = True

        # Mock file opening and deque behavior
        with mock.patch('builtins.open', mock.mock_open(read_data="")):
             result = evolverstage.get_latest_log_entry()

        self.assertEqual(result, "Log file is empty.")

    @mock.patch('os.path.exists')
    def test_log_file_with_content(self, mock_exists):
        """Test retrieving the last line from a populated log file."""
        mock_exists.return_value = True
        log_content = "header1,header2\ndata1,data2\ndata3,data4\n"

        # We need to mock how deque(f, maxlen=1) behaves with a file object.
        # Since mock_open returns a mock file object which is iterable,
        # deque(mock_file) iterates over lines.
        with mock.patch('builtins.open', mock.mock_open(read_data=log_content)):
            result = evolverstage.get_latest_log_entry()

        self.assertEqual(result, "data3,data4")

    @mock.patch('os.path.exists')
    def test_log_file_read_error(self, mock_exists):
        """Test handling of IO exceptions."""
        mock_exists.return_value = True

        with mock.patch('builtins.open', side_effect=IOError("Disk error")):
            result = evolverstage.get_latest_log_entry()

        self.assertTrue(result.startswith("Error reading log:"))
        self.assertIn("Disk error", result)
