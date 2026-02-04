import sys
import os
import unittest
import csv
import tempfile
from unittest import mock

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestLeaderboard(unittest.TestCase):
    def setUp(self):
        # Use a temporary file for the log
        self.test_log = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.csv')
        self.log_path = self.test_log.name
        self.original_log_file = evolverstage.BATTLE_LOG_FILE
        evolverstage.BATTLE_LOG_FILE = self.log_path

        # Write header
        writer = csv.DictWriter(self.test_log, fieldnames=['era', 'arena', 'winner', 'loser', 'score1', 'score2', 'bred_with'])
        writer.writeheader()
        self.writer = writer
        self.test_log.flush()

    def tearDown(self):
        # Restore original log file path and remove temporary file
        evolverstage.BATTLE_LOG_FILE = self.original_log_file
        if os.path.exists(self.log_path):
            os.remove(self.log_path)

    def test_get_leaderboard_basic(self):
        """Test basic win counting across arenas."""
        # Arena 0: W1 beats W2
        self.writer.writerow({'era': '0', 'arena': '0', 'winner': '1', 'loser': '2', 'score1': '100', 'score2': '50', 'bred_with': '3'})
        # Arena 0: W1 beats W3
        self.writer.writerow({'era': '0', 'arena': '0', 'winner': '1', 'loser': '3', 'score1': '100', 'score2': '50', 'bred_with': '4'})
        # Arena 1: W4 beats W5
        self.writer.writerow({'era': '0', 'arena': '1', 'winner': '4', 'loser': '5', 'score1': '100', 'score2': '50', 'bred_with': '6'})
        self.test_log.flush()

        results = evolverstage.get_leaderboard()

        self.assertIn(0, results)
        self.assertIn(1, results)
        self.assertEqual(results[0], [('1', 2)])
        self.assertEqual(results[1], [('4', 1)])

    def test_get_leaderboard_reset_on_loss(self):
        """Test that a warrior's win count is reset when they lose."""
        # W1 beats W2
        self.writer.writerow({'era': '0', 'arena': '0', 'winner': '1', 'loser': '2', 'score1': '100', 'score2': '50', 'bred_with': '3'})
        # W1 beats W3
        self.writer.writerow({'era': '0', 'arena': '0', 'winner': '1', 'loser': '3', 'score1': '100', 'score2': '50', 'bred_with': '4'})
        # W5 beats W1 (W1 should be reset)
        self.writer.writerow({'era': '0', 'arena': '0', 'winner': '5', 'loser': '1', 'score1': '100', 'score2': '50', 'bred_with': '6'})
        self.test_log.flush()

        results = evolverstage.get_leaderboard(arena_idx=0)

        # Only W5 should have wins > 0
        self.assertEqual(results[0], [('5', 1)])

    def test_get_leaderboard_empty_log(self):
        """Test behavior with an empty log (only header)."""
        # Header is already written in setUp
        results = evolverstage.get_leaderboard()
        self.assertEqual(results, {})

    def test_get_leaderboard_no_file(self):
        """Test behavior when the log file does not exist."""
        evolverstage.BATTLE_LOG_FILE = "non_existent_file.csv"
        results = evolverstage.get_leaderboard()
        self.assertEqual(results, {})

if __name__ == '__main__':
    unittest.main()
