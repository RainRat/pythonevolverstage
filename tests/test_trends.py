
import unittest
import os
import shutil
import io
import sys
import csv
from unittest.mock import patch, MagicMock

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestTrends(unittest.TestCase):
    def setUp(self):
        self.arena_dir = "arena0"
        if os.path.exists(self.arena_dir):
            shutil.rmtree(self.arena_dir)
        os.makedirs(self.arena_dir)

        # Create population: 5 warriors total
        # Warriors 3, 4, 5: MOV.I
        for i in range(3, 6):
            with open(os.path.join(self.arena_dir, f"{i}.red"), "w") as f:
                f.write("MOV.I $0, $1\n")

        # Warriors 1, 2: SPL.B (Top performers)
        with open(os.path.join(self.arena_dir, "1.red"), "w") as f:
            f.write("SPL.B $0, $1\n")
        with open(os.path.join(self.arena_dir, "2.red"), "w") as f:
            f.write("SPL.B $0, $1\n")

        # Mock battle log
        self.log_file = "test_battle_log.csv"
        with open(self.log_file, "w", newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['era', 'arena', 'winner', 'loser', 'score1', 'score2', 'bred_with'])
            writer.writeheader()
            # Warrior 1 and 2 have wins
            writer.writerow({'era': '0', 'arena': '0', 'winner': '1', 'loser': '3', 'score1': '100', 'score2': '0', 'bred_with': '4'})
            writer.writerow({'era': '0', 'arena': '0', 'winner': '2', 'loser': '4', 'score1': '100', 'score2': '0', 'bred_with': '5'})

    def tearDown(self):
        if os.path.exists(self.arena_dir):
            shutil.rmtree(self.arena_dir)
        if os.path.exists(self.log_file):
            os.remove(self.log_file)

    @patch('evolverstage.BATTLE_LOG_FILE', "test_battle_log.csv")
    def test_run_trend_analysis(self):
        # Capture stdout
        captured_output = io.StringIO()
        sys.stdout = captured_output

        try:
            evolverstage.run_trend_analysis(0)
        finally:
            sys.stdout = sys.__stdout__

        output = captured_output.getvalue()

        # Verify output contains key sections
        self.assertIn("Trend Analysis: Arena 0", output)
        self.assertIn("Population:    5 warriors", output)
        self.assertIn("Meta:          2 warriors", output)

        # Verify Opcode Trends
        # Population: 3 MOV, 2 SPL -> MOV 60%, SPL 40%
        # Meta: 2 SPL -> SPL 100%
        # Delta: SPL +60%, MOV -60%

        clean_output = evolverstage.strip_ansi(output)
        # Check for values. The formatting might have multiple spaces.
        self.assertTrue("MOV" in clean_output)
        self.assertTrue("SPL" in clean_output)
        self.assertIn("60.0%", clean_output)
        self.assertIn("40.0%", clean_output)
        self.assertIn("100.0%", clean_output)
        self.assertIn("+60.0%", clean_output)
        self.assertIn("-60.0%", clean_output)

    @patch('evolverstage.BATTLE_LOG_FILE', "non_existent_log.csv")
    def test_run_trend_analysis_no_log(self):
        # Capture stdout
        captured_output = io.StringIO()
        sys.stdout = captured_output

        try:
            evolverstage.run_trend_analysis(0)
        finally:
            sys.stdout = sys.__stdout__

        output = captured_output.getvalue()
        self.assertIn("No leaderboard data found for Arena 0", output)

if __name__ == '__main__':
    unittest.main()
