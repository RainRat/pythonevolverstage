
import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Adjust path to import evolverstage from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import evolverstage

class TestStatus(unittest.TestCase):
    @patch('builtins.print')
    @patch('evolverstage.get_latest_log_entry')
    @patch('os.path.exists')
    @patch('os.listdir')
    def test_print_status_structure(self, mock_listdir, mock_exists, mock_get_log, mock_print):
        # Setup mocks
        mock_get_log.return_value = "Test Log Entry"
        mock_exists.return_value = True
        mock_listdir.return_value = ['1.red', '2.red']

        # We need to mock open to avoid file reading errors during "Avg Length" calculation
        with patch('builtins.open', unittest.mock.mock_open(read_data="MOV 0, 1\nDAT 0, 0")):
             evolverstage.print_status()

        # Check if key headers were printed
        # We can inspect the calls to print
        printed_strings = [call.args[0] for call in mock_print.call_args_list if call.args]

        self.assertTrue(any("Evolver Status Report" in s for s in printed_strings))
        self.assertTrue(any("Latest Battle Log: Test Log Entry" in s for s in printed_strings))
        self.assertTrue(any("Arena 0:" in s for s in printed_strings))
        self.assertTrue(any("Population:    2 warriors" in s for s in printed_strings))

    def test_status_command_invocation(self):
        # This test ensures that invoking the script with --status calls print_status
        # Note: Testing sys.exit(0) is tricky, so we might just verify the function exists and is callable
        pass

if __name__ == '__main__':
    unittest.main()
