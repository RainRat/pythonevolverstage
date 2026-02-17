import sys
import os
import unittest
import tempfile
import shutil

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestGetRecentLogEntries(unittest.TestCase):
    def setUp(self):
        # Save original BATTLE_LOG_FILE to restore later
        self.original_log_file = evolverstage.BATTLE_LOG_FILE
        # Create a temporary directory for test logs
        self.test_dir = tempfile.mkdtemp()
        self.log_path = os.path.join(self.test_dir, "test_battle.log")
        evolverstage.BATTLE_LOG_FILE = self.log_path

    def tearDown(self):
        # Restore original log file path
        evolverstage.BATTLE_LOG_FILE = self.original_log_file
        # Remove temporary directory
        shutil.rmtree(self.test_dir)

    def test_log_file_not_found(self):
        """Test behavior when the log file does not exist."""
        # Ensure file doesn't exist
        if os.path.exists(self.log_path):
            os.remove(self.log_path)
        result = evolverstage.get_recent_log_entries(n=1)
        self.assertEqual(result, [])

    def test_log_file_not_configured(self):
        """Test behavior when BATTLE_LOG_FILE is None."""
        evolverstage.BATTLE_LOG_FILE = None
        result = evolverstage.get_recent_log_entries(n=1)
        self.assertEqual(result, [])

    def test_log_file_empty(self):
        """Test behavior when the log file is empty."""
        with open(self.log_path, 'w') as f:
            f.write("")
        result = evolverstage.get_recent_log_entries(n=1)
        self.assertEqual(result, [])

    def test_get_recent_entries(self):
        """Test retrieving multiple recent entries."""
        content = (
            "era,arena,winner,loser,score1,score2,bred_with\n"
            "0,0,1,2,100,50,0\n"
            "0,0,3,4,150,20,0\n"
            "0,0,5,6,80,80,0\n"
        )
        with open(self.log_path, 'w') as f:
            f.write(content)

        # Get last 2
        result = evolverstage.get_recent_log_entries(n=2)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['winner'], '3')
        self.assertEqual(result[1]['winner'], '5')

    def test_filter_by_arena(self):
        """Test filtering log entries by arena index."""
        content = (
            "era,arena,winner,loser,score1,score2,bred_with\n"
            "0,0,1,2,100,50,0\n"
            "0,1,3,4,150,20,0\n"
            "0,0,5,6,80,80,0\n"
        )
        with open(self.log_path, 'w') as f:
            f.write(content)

        # Get last entry for Arena 1
        result = evolverstage.get_recent_log_entries(n=1, arena_idx=1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['arena'], '1')
        self.assertEqual(result[0]['winner'], '3')

        # Get entries for Arena 0
        result = evolverstage.get_recent_log_entries(n=5, arena_idx=0)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['winner'], '1')
        self.assertEqual(result[1]['winner'], '5')

    def test_malformed_lines(self):
        """Test that malformed lines in the log are gracefully skipped."""
        content = (
            "era,arena,winner,loser,score1,score2,bred_with\n"
            "0,0,1,2,100,50,0\n"
            "invalid,line,here\n"
            "0,0,5,6,80,80,0\n"
        )
        with open(self.log_path, 'w') as f:
            f.write(content)

        result = evolverstage.get_recent_log_entries(n=5)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['winner'], '1')
        self.assertEqual(result[1]['winner'], '5')
