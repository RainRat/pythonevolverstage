
import unittest
import os
import shutil
import io
import sys
from unittest.mock import patch
import evolverstage

class TestDiff(unittest.TestCase):
    def setUp(self):
        self.test_dir = "test_arena_diff"
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.makedirs(self.test_dir)

        # Create some warriors
        self.w1 = os.path.join(self.test_dir, "w1.red")
        with open(self.w1, "w") as f:
            f.write("MOV.I $0, $1\n")
            f.write("MOV.I 2, 3\n")

        self.w2 = os.path.join(self.test_dir, "w2.red")
        with open(self.w2, "w") as f:
            f.write("MOV.I $0, $1\n")
            f.write("SPL.B 4, 5\n")

        self.w3 = os.path.join(self.test_dir, "w3.red")
        with open(self.w3, "w") as f:
            f.write("MOV.I $0, $1\n")
            f.write("MOV.I 2, 3\n")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        if os.path.exists("arena99"):
            shutil.rmtree("arena99")

    def test_run_diff_files(self):
        captured_output = io.StringIO()
        sys.stdout = captured_output
        try:
            evolverstage.run_diff(self.w1, self.w2, 0)
        finally:
            sys.stdout = sys.__stdout__

        output = captured_output.getvalue()
        clean_output = evolverstage.strip_ansi(output)

        self.assertIn("Code Diff", clean_output)
        self.assertIn("w1.red vs w2.red", clean_output)
        self.assertIn("-MOV.I 2, 3", clean_output)
        self.assertIn("+SPL.B 4, 5", clean_output)

    def test_run_diff_identical(self):
        captured_output = io.StringIO()
        sys.stdout = captured_output
        try:
            evolverstage.run_diff(self.w1, self.w3, 0)
        finally:
            sys.stdout = sys.__stdout__

        output = captured_output.getvalue()
        clean_output = evolverstage.strip_ansi(output)
        self.assertIn("Warriors are identical", clean_output)

    @patch('evolverstage.get_leaderboard')
    def test_run_diff_selectors(self, mock_leaderboard):
        # Mock leaderboard to return 'champion' as top warrior in arena 99
        mock_leaderboard.return_value = {99: [('champion', 10)]}

        # We need champion.red in arena99
        os.makedirs("arena99", exist_ok=True)
        arena_champ = "arena99/champion.red"
        with open(arena_champ, "w") as f:
            f.write("JMP.I $0, $0\n")

        captured_output = io.StringIO()
        sys.stdout = captured_output
        try:
            # Use top@99 to target the champion
            evolverstage.run_diff("top@99", self.w1, 0)
        finally:
            sys.stdout = sys.__stdout__

        output = captured_output.getvalue()
        clean_output = evolverstage.strip_ansi(output)
        self.assertIn("champion.red vs w1.red", clean_output)
        self.assertIn("-JMP.I $0, $0", clean_output)
        self.assertIn("+MOV.I $0, $1", clean_output)

    def test_run_diff_not_found(self):
        captured_output = io.StringIO()
        sys.stdout = captured_output
        try:
            evolverstage.run_diff("nonexistent.red", self.w1, 0)
        finally:
            sys.stdout = sys.__stdout__

        output = captured_output.getvalue()
        clean_output = evolverstage.strip_ansi(output)
        self.assertIn("Error: Target A 'nonexistent.red' not found", clean_output)

if __name__ == '__main__':
    unittest.main()
