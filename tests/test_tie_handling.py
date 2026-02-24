import sys
import os
import unittest
import csv
import tempfile
import shutil

# Add the root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestTieHandling(unittest.TestCase):
    def setUp(self):
        # Temp dir for tests
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

        # Temp log file
        self.test_log = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.csv')
        self.log_path = self.test_log.name
        self.original_log_file = evolverstage.BATTLE_LOG_FILE
        evolverstage.BATTLE_LOG_FILE = self.log_path

        # Write header
        with open(self.log_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['era', 'arena', 'winner', 'loser', 'score1', 'score2', 'bred_with'])
            writer.writeheader()

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)
        evolverstage.BATTLE_LOG_FILE = self.original_log_file
        if os.path.exists(self.log_path):
            os.remove(self.log_path)

    def _write_log_row(self, row):
        with open(self.log_path, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['era', 'arena', 'winner', 'loser', 'score1', 'score2', 'bred_with'])
            writer.writerow(row)

    def test_get_lifetime_rankings_ignores_tie(self):
        """Verify that get_lifetime_rankings excludes 'TIE' from rankings."""
        # W1: 1 win, 0 loss
        self._write_log_row({'era': '0', 'arena': '0', 'winner': '1', 'loser': '2', 'score1': '100', 'score2': '0', 'bred_with': ''})
        # 5 Ties
        for _ in range(5):
            self._write_log_row({'era': '0', 'arena': '0', 'winner': 'TIE', 'loser': 'TIE', 'score1': '50', 'score2': '50', 'bred_with': ''})

        # min_battles=1 to include everyone
        rankings = evolverstage.get_lifetime_rankings(arena_idx=0, min_battles=1)

        # Before fix, 'TIE' will be in rankings[0]
        # We want to ensure 'TIE' is NOT in rankings[0]
        if 0 in rankings:
            warrior_ids = [r[0] for r in rankings[0]]
            self.assertNotIn('TIE', warrior_ids, "Rankings should not include 'TIE' as a warrior")

    def test_get_leaderboard_ignores_tie(self):
        """Verify that get_leaderboard excludes 'TIE' from results."""
        # 5 Ties
        for _ in range(5):
            self._write_log_row({'era': '0', 'arena': '0', 'winner': 'TIE', 'loser': 'TIE', 'score1': '50', 'score2': '50', 'bred_with': ''})

        leaderboard = evolverstage.get_leaderboard(arena_idx=0)

        if 0 in leaderboard:
            warrior_ids = [r[0] for r in leaderboard[0]]
            self.assertNotIn('TIE', warrior_ids, "Leaderboard should not include 'TIE' as a warrior")

if __name__ == '__main__':
    unittest.main()
