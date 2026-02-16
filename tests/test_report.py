import sys
import os
import unittest
import csv
import tempfile
import shutil
from unittest import mock

# Add the root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestReport(unittest.TestCase):
    def setUp(self):
        # Temp dir for arenas
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

        # Temp log file
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
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)
        evolverstage.BATTLE_LOG_FILE = self.original_log_file
        if os.path.exists(self.log_path):
            os.remove(self.log_path)

    def test_get_population_diversity_basic(self):
        """Test diversity calculation with unique and duplicate warriors."""
        os.makedirs("arena0", exist_ok=True)
        # Unique warrior 1
        with open("arena0/1.red", "w") as f:
            f.write("MOV.I $0,$1\n")
        # Unique warrior 2
        with open("arena0/2.red", "w") as f:
            f.write("ADD.AB #4,$1\n")
        # Duplicate of warrior 1
        with open("arena0/3.red", "w") as f:
            f.write("MOV.I $0,$1\n")

        # 2 unique out of 3 total = 66.66%
        diversity = evolverstage.get_population_diversity(0)
        self.assertAlmostEqual(diversity, 66.6666666, places=5)

    def test_get_lifetime_rankings_basic(self):
        """Test win rate calculation and sorting."""
        # W1: 2 wins, 1 loss (66.6% win rate, 3 battles)
        # W2: 1 win, 1 loss (50% win rate, 2 battles)
        # W3: 0 wins, 1 loss (0% win rate, 1 battle)

        self.writer.writerow({'era': '0', 'arena': '0', 'winner': '1', 'loser': '2', 'score1': '100', 'score2': '50', 'bred_with': 'x'})
        self.writer.writerow({'era': '0', 'arena': '0', 'winner': '1', 'loser': '3', 'score1': '100', 'score2': '50', 'bred_with': 'x'})
        self.writer.writerow({'era': '0', 'arena': '0', 'winner': '2', 'loser': '1', 'score1': '100', 'score2': '50', 'bred_with': 'x'})
        self.test_log.flush()

        rankings = evolverstage.get_lifetime_rankings(arena_idx=0, min_battles=1)

        self.assertIn(0, rankings)
        # Should be ordered by win rate
        self.assertEqual(rankings[0][0][0], '1') # W1
        self.assertAlmostEqual(rankings[0][0][1], 66.666666, places=5)
        self.assertEqual(rankings[0][1][0], '2') # W2
        self.assertEqual(rankings[0][1][1], 50.0)

    def test_run_report_smoke(self):
        """Smoke test for run_report to ensure it runs without error."""
        os.makedirs("arena0", exist_ok=True)
        with open("arena0/1.red", "w") as f:
            f.write("MOV.I $0,$1\n")

        with mock.patch('evolverstage.LAST_ARENA', 0), \
             mock.patch('evolverstage.CORESIZE_LIST', [8000]), \
             mock.patch('evolverstage.CYCLES_LIST', [80000]), \
             mock.patch('evolverstage.PROCESSES_LIST', [8000]), \
             mock.patch('evolverstage.WARLEN_LIST', [100]):
            evolverstage.run_report(0)

if __name__ == '__main__':
    unittest.main()
