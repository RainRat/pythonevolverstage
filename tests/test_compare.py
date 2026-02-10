import unittest
import os
import shutil
import io
import sys
from unittest.mock import patch, MagicMock
import evolverstage

class TestCompare(unittest.TestCase):
    def setUp(self):
        self.test_dir = "test_compare_dir"
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.makedirs(self.test_dir)

        # Create two different warriors
        self.w1 = os.path.join(self.test_dir, "w1.red")
        with open(self.w1, "w") as f:
            f.write("MOV.I $0, $1\n")

        self.w2 = os.path.join(self.test_dir, "w2.red")
        with open(self.w2, "w") as f:
            f.write("SPL.B $0, $1\n")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_run_comparison_files(self):
        captured_output = io.StringIO()
        sys.stdout = captured_output
        try:
            evolverstage.run_comparison(self.w1, self.w2, 0)
        finally:
            sys.stdout = sys.__stdout__

        output = evolverstage.strip_ansi(captured_output.getvalue())
        self.assertIn("Comparison: test_compare_dir/w1.red vs test_compare_dir/w2.red", output)
        self.assertIn("MOV", output)
        self.assertIn("SPL", output)
        self.assertIn("-100.0%", output)
        self.assertIn("+100.0%", output)

    def test_run_comparison_json(self):
        captured_output = io.StringIO()
        sys.stdout = captured_output
        try:
            evolverstage.run_comparison(self.w1, self.w2, 0, json_mode=True)
        finally:
            sys.stdout = sys.__stdout__

        output = captured_output.getvalue()
        self.assertIn('"label": "test_compare_dir/w1.red"', output)
        self.assertIn('"MOV": 1', output)

if __name__ == '__main__':
    unittest.main()
