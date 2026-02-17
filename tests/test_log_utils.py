import sys
import os
import unittest
import tempfile
from unittest import mock

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestGetRecentLogEntries(unittest.TestCase):
    def setUp(self):
        # Save original BATTLE_LOG_FILE to restore later
        self.original_log_file = evolverstage.BATTLE_LOG_FILE
        # Create a temporary log file
        self.test_log = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.csv')
        self.log_path = self.test_log.name
        evolverstage.BATTLE_LOG_FILE = self.log_path

        # Write header
        self.header = "era,arena,winner,loser,score1,score2,bred_with\n"
        self.test_log.write(self.header)
        self.test_log.flush()

    def tearDown(self):
        # Restore original log file path
        evolverstage.BATTLE_LOG_FILE = self.original_log_file
        # Close and remove the temporary file
        self.test_log.close()
        if os.path.exists(self.log_path):
            os.remove(self.log_path)

    def _add_log_entry(self, era, arena, winner, loser, score1, score2, bred_with='0'):
        line = f"{era},{arena},{winner},{loser},{score1},{score2},{bred_with}\n"
        self.test_log.write(line)
        self.test_log.flush()

    def test_log_file_not_found(self):
        """Test behavior when the log file does not exist."""
        evolverstage.BATTLE_LOG_FILE = "non_existent_file.csv"
        result = evolverstage.get_recent_log_entries(n=1)
        self.assertEqual(result, [])

    def test_log_file_empty(self):
        """Test behavior when the log file is empty (or only header)."""
        # Already has header from setUp
        result = evolverstage.get_recent_log_entries(n=1)
        self.assertEqual(result, [])

    def test_get_recent_n1(self):
        """Test retrieving the single most recent entry."""
        self._add_log_entry(0, 0, 1, 2, 100, 50)
        self._add_log_entry(0, 1, 3, 4, 120, 40)

        result = evolverstage.get_recent_log_entries(n=1)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['winner'], '3')
        self.assertEqual(result[0]['arena'], '1')

    def test_get_recent_multiple(self):
        """Test retrieving multiple recent entries."""
        for i in range(1, 11):
            self._add_log_entry(0, 0, str(i), str(i+1), 100, 50)

        result = evolverstage.get_recent_log_entries(n=5)

        self.assertEqual(len(result), 5)
        self.assertEqual(result[0]['winner'], '6')
        self.assertEqual(result[-1]['winner'], '10')

    def test_get_recent_with_arena_filter(self):
        """Test filtering by arena index."""
        # Arena 0
        self._add_log_entry(0, 0, '1', '2', 100, 50)
        # Arena 1
        self._add_log_entry(0, 1, '3', '4', 120, 40)
        # Arena 0 again
        self._add_log_entry(0, 0, '5', '6', 110, 60)

        # Filter for arena 0
        result = evolverstage.get_recent_log_entries(n=5, arena_idx=0)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['winner'], '1')
        self.assertEqual(result[1]['winner'], '5')

        # Filter for arena 1
        result = evolverstage.get_recent_log_entries(n=5, arena_idx=1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['winner'], '3')

    def test_heuristic_scan_depth(self):
        """Test that arena filtering works even if targets are buried by other arena entries."""
        # Fill log with 50 entries for Arena 1
        for i in range(50):
            self._add_log_entry(0, 1, '100', '200', 100, 100)

        # Add one entry for Arena 0 at the very end
        self._add_log_entry(0, 0, '7', '8', 150, 50)

        # n=1, arena_idx=0. scan_depth will be 1 * 20 = 20.
        # The Arena 0 entry is the very last one, so it should be found within last 20 lines.
        result = evolverstage.get_recent_log_entries(n=1, arena_idx=0)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['winner'], '7')

        # Now add 30 more entries for Arena 1
        for i in range(30):
            self._add_log_entry(0, 1, '100', '200', 100, 100)

        # n=1, arena_idx=0. scan_depth is 20. The '7' entry is now 31 lines back.
        # It should NOT be found because it's outside the scan depth.
        result = evolverstage.get_recent_log_entries(n=1, arena_idx=0)
        self.assertEqual(len(result), 0)

    def test_malformed_csv_line(self):
        """Test that malformed lines are skipped gracefully."""
        self.test_log.write("not,enough,parts\n")
        self._add_log_entry(0, 0, '1', '2', 100, 50)
        self.test_log.write("bad,arena_not_int,winner,loser,score1,score2,bred_with\n")
        self.test_log.flush()

        result = evolverstage.get_recent_log_entries(n=5)
        # Should only have the one valid entry
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['winner'], '1')

    @mock.patch('builtins.open')
    def test_log_file_read_error(self, mock_open):
        """Test handling of IO exceptions."""
        mock_open.side_effect = IOError("Disk error")
        result = evolverstage.get_recent_log_entries(n=1)
        self.assertEqual(result, [])

if __name__ == '__main__':
    unittest.main()
