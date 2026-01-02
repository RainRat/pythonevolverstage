import unittest
from unittest.mock import patch, MagicMock
import sys
import io
import os
import evolverstage

class TestStatus(unittest.TestCase):
    def setUp(self):
        # Redirect stdout to capture print output
        self.held_stdout = io.StringIO()
        self.original_stdout = sys.stdout
        sys.stdout = self.held_stdout

    def tearDown(self):
        sys.stdout = self.original_stdout

    @patch('evolverstage.LAST_ARENA', 1)
    @patch('evolverstage.CORESIZE_LIST', [8000, 8000])
    @patch('evolverstage.CYCLES_LIST', [80000, 80000])
    @patch('evolverstage.PROCESSES_LIST', [8000, 8000])
    @patch('os.path.exists')
    @patch('os.listdir')
    def test_print_status_with_existing_directories(self, mock_listdir, mock_exists):
        # Setup mocks
        mock_exists.return_value = True
        mock_listdir.return_value = ['1.red', '2.red']

        # We need to mock open() to avoid FileNotFoundError when sampling files
        with patch('builtins.open', unittest.mock.mock_open(read_data="ADD #4, #5\nSUB #4, #5")):
            evolverstage.print_status()

        output = self.held_stdout.getvalue()
        self.assertIn("Evolver Status Report", output)
        self.assertIn("Arena 0:", output)
        self.assertIn("Arena 1:", output)
        self.assertIn("Population:    2 warriors", output)

    @patch('evolverstage.LAST_ARENA', 0)
    @patch('evolverstage.CORESIZE_LIST', [8000])
    @patch('evolverstage.CYCLES_LIST', [80000])
    @patch('evolverstage.PROCESSES_LIST', [8000])
    @patch('os.path.exists')
    def test_print_status_with_missing_directories(self, mock_exists):
        # Setup mocks so directories don't exist
        mock_exists.return_value = False

        evolverstage.print_status()

        output = self.held_stdout.getvalue()
        self.assertIn("Directory 'arena0' not found", output)

if __name__ == '__main__':
    unittest.main()
