import unittest
import os
import shutil
import tempfile
import sys
from io import StringIO
from evolverstage import run_inspection, Colors

class TestInspection(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.arena0_dir = os.path.join(self.test_dir, "arena0")
        os.makedirs(self.arena0_dir)
        self.warrior_path = os.path.join(self.arena0_dir, "1.red")
        with open(self.warrior_path, "w") as f:
            f.write("MOV.I $0, 1\nSPL.B $0, 1\n")

        self.old_cwd = os.getcwd()
        os.chdir(self.test_dir)

        # Mock battle log
        self.log_file = "battle_log.csv"
        with open(self.log_file, "w") as f:
            f.write("era,arena,winner,loser,score1,score2,bred_with\n")
            f.write("0,0,1,2,100,0,3\n")

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.test_dir)

    def test_run_inspection_basic(self):
        captured_output = StringIO()
        sys.stdout = captured_output
        try:
            run_inspection("1", 0)
        finally:
            sys.stdout = sys.__stdout__

        output = captured_output.getvalue()
        self.assertIn("Warrior Profile: 1.red", strip_ansi(output))
        self.assertIn("Strategy:  Paper (Replicator)", strip_ansi(output))
        self.assertIn("Current Win Streak: 1", strip_ansi(output))
        self.assertIn("MOV.I $0, 1", strip_ansi(output))

    def test_run_inspection_not_found(self):
        captured_output = StringIO()
        sys.stdout = captured_output
        try:
            run_inspection("999", 0)
        finally:
            sys.stdout = sys.__stdout__

        output = captured_output.getvalue()
        self.assertIn("Error: Warrior '999' not found.", strip_ansi(output))

def strip_ansi(text):
    import re
    return re.sub(r'\033\[[0-9;]*m', '', text)

if __name__ == "__main__":
    unittest.main()
