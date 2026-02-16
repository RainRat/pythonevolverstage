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
        # Create a temporary directory for test logs
        self.test_dir = tempfile.mkdtemp()
        self.log_file_path = os.path.join(self.test_dir, "test_log.csv")
        # Save original BATTLE_LOG_FILE to restore later
        self.original_log_file = evolverstage.BATTLE_LOG_FILE
        evolverstage.BATTLE_LOG_FILE = self.log_file_path

    def tearDown(self):
        # Restore original log file path
        evolverstage.BATTLE_LOG_FILE = self.original_log_file
        # Remove the temporary directory
        shutil.rmtree(self.test_dir)

    def test_log_file_not_found(self):
        """Test behavior when the log file does not exist."""
        # Ensure it doesn't exist
        if os.path.exists(self.log_file_path):
            os.remove(self.log_file_path)
        result = evolverstage.get_recent_log_entries()
        self.assertEqual(result, [])

    def test_log_file_not_configured(self):
        """Test behavior when BATTLE_LOG_FILE is None or empty."""
        evolverstage.BATTLE_LOG_FILE = None
        result = evolverstage.get_recent_log_entries()
        self.assertEqual(result, [])

    def test_log_file_empty(self):
        """Test behavior when the log file is empty."""
        open(self.log_file_path, 'w').close()
        result = evolverstage.get_recent_log_entries()
        self.assertEqual(result, [])

    def test_get_recent_log_entries_single(self):
        """Test retrieving a single entry."""
        with open(self.log_file_path, 'w') as f:
            f.write("era,arena,winner,loser,score1,score2,bred_with\n")
            f.write("0,1,5,10,150,50,7\n")

        result = evolverstage.get_recent_log_entries(n=1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['era'], '0')
        self.assertEqual(result[0]['winner'], '5')
        self.assertEqual(result[0]['bred_with'], '7')

    def test_get_recent_log_entries_multiple(self):
        """Test retrieving multiple entries from the end."""
        with open(self.log_file_path, 'w') as f:
            f.write("era,arena,winner,loser,score1,score2,bred_with\n")
            f.write("0,1,5,10,150,50,7\n")
            f.write("1,0,12,3,200,0,random\n")
            f.write("2,1,8,4,100,100,99\n")

        # Get last 2
        result = evolverstage.get_recent_log_entries(n=2)
        self.assertEqual(len(result), 2)
        # Oldest of the last 2 (era 1) should be first
        self.assertEqual(result[0]['era'], '1')
        # Newest (era 2) should be last
        self.assertEqual(result[1]['era'], '2')
        self.assertEqual(result[1]['winner'], '8')
        self.assertEqual(result[0]['bred_with'], 'random')

    def test_get_recent_log_entries_skips_header(self):
        """Test that the header line is correctly identified and skipped."""
        with open(self.log_file_path, 'w') as f:
            f.write("era,arena,winner,loser,score1,score2,bred_with\n")

        result = evolverstage.get_recent_log_entries(n=5)
        self.assertEqual(result, [])

    def test_get_recent_log_entries_malformed_line(self):
        """Test that malformed lines with insufficient fields are skipped."""
        with open(self.log_file_path, 'w') as f:
            f.write("era,arena,winner,loser,score1,score2,bred_with\n")
            f.write("0,1,5,10,150\n") # Too few fields

        result = evolverstage.get_recent_log_entries(n=1)
        self.assertEqual(result, [])

if __name__ == '__main__':
    unittest.main()
