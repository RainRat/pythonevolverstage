
import unittest
import os
import shutil
import io
import sys
import json
from unittest.mock import patch
import evolverstage

class TestCompare(unittest.TestCase):
    def setUp(self):
        self.test_dir = "test_arena_compare"
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.makedirs(self.test_dir)

        # Create some warriors
        self.w1 = os.path.join(self.test_dir, "w1.red")
        with open(self.w1, "w") as f:
            f.write("MOV.I $0, $1\n")
            f.write("MOV.I $0, $1\n")

        self.w2 = os.path.join(self.test_dir, "w2.red")
        with open(self.w2, "w") as f:
            f.write("SPL.B $0, $1\n")
            f.write("DAT.F $0, $0\n")

        # Create a directory for population test
        self.pop_dir = os.path.join(self.test_dir, "pop")
        os.makedirs(self.pop_dir)
        for i in range(5):
            with open(os.path.join(self.pop_dir, f"{i}.red"), "w") as f:
                f.write("ADD.AB #5, $0\n")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        if os.path.exists("arena99"):
            shutil.rmtree("arena99")

    def test_run_comparison_files(self):
        captured_output = io.StringIO()
        sys.stdout = captured_output
        try:
            evolverstage.run_comparison(self.w1, self.w2, 0)
        finally:
            sys.stdout = sys.__stdout__

        output = captured_output.getvalue()
        clean_output = evolverstage.strip_ansi(output)

        self.assertIn("Comparison", clean_output)
        self.assertIn(f"Target A: {self.w1}", clean_output)
        self.assertIn(f"Target B: {self.w2}", clean_output)
        self.assertIn("MOV", clean_output)
        self.assertIn("SPL", clean_output)
        self.assertIn("DAT", clean_output)

    def test_run_comparison_json(self):
        captured_output = io.StringIO()
        sys.stdout = captured_output
        try:
            evolverstage.run_comparison(self.w1, self.w2, 0, json_output=True)
        finally:
            sys.stdout = sys.__stdout__

        output = captured_output.getvalue()
        data = json.loads(output)

        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]['file'], self.w1)
        self.assertEqual(data[1]['file'], self.w2)
        self.assertEqual(data[0]['opcodes']['MOV'], 2)
        self.assertEqual(data[1]['opcodes']['SPL'], 1)
        self.assertEqual(data[1]['opcodes']['DAT'], 1)

    def test_run_comparison_directory(self):
        captured_output = io.StringIO()
        sys.stdout = captured_output
        try:
            evolverstage.run_comparison(self.pop_dir, self.w1, 0)
        finally:
            sys.stdout = sys.__stdout__

        output = captured_output.getvalue()
        clean_output = evolverstage.strip_ansi(output)

        self.assertIn(f"Target A: {self.pop_dir} (5 warriors)", clean_output)
        self.assertIn("ADD", clean_output)
        self.assertIn("MOV", clean_output)

    @patch('evolverstage.get_leaderboard')
    def test_run_comparison_selectors(self, mock_leaderboard):
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
            evolverstage.run_comparison("top@99", self.w2, 0)
        finally:
            sys.stdout = sys.__stdout__

        output = captured_output.getvalue()
        self.assertIn("arena99/champion.red", output)
        self.assertIn("JMP", output)

if __name__ == '__main__':
    unittest.main()
