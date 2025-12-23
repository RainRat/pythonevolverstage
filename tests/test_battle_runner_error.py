import sys
import unittest
import pathlib
import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import battle_runner

class TestProcessBattleOutput(unittest.TestCase):
    def test_error_handling_start_of_output(self):
        """Test that an error at the start of the output is caught."""
        raw_output = "ERROR: Some error occurred"
        with self.assertRaises(RuntimeError) as cm:
            battle_runner._process_battle_output(raw_output, "test_engine", False, [1, 2])
        self.assertIn("Battle engine reported an error: ERROR: Some error occurred", str(cm.exception))

    def test_error_handling_leading_whitespace(self):
        """Test that an error with leading whitespace is caught."""
        raw_output = "   ERROR: Indented error"
        with self.assertRaises(RuntimeError) as cm:
            battle_runner._process_battle_output(raw_output, "test_engine", False, [1, 2])
        self.assertIn("Battle engine reported an error: ERROR: Indented error", str(cm.exception))

    def test_error_handling_later_in_output(self):
        """Test that an error later in the output is caught."""
        raw_output = "Some log\nERROR: Delayed error"
        with self.assertRaises(RuntimeError) as cm:
            battle_runner._process_battle_output(raw_output, "test_engine", False, [1, 2])
        self.assertIn("Battle engine reported an error: ERROR: Delayed error", str(cm.exception))

if __name__ == "__main__":
    unittest.main()
