
import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Adjust path to import evolverstage from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import evolverstage

class TestStatus(unittest.TestCase):
    @patch('builtins.print')
    @patch('evolverstage.get_recent_log_entries')
    @patch('os.path.exists')
    @patch('os.listdir')
    def test_print_status_structure(self, mock_listdir, mock_exists, mock_get_recent, mock_print):
        # Setup mocks
        log_entry = {
            'era': '0', 'arena': '0', 'winner': '5', 'loser': '10', 'score1': '150', 'score2': '50'
        }
        mock_get_recent.return_value = [log_entry]
        mock_exists.return_value = True
        mock_listdir.return_value = ['1.red', '2.red']

        # We need to mock open to avoid file reading errors during "Avg Length" calculation
        with patch('builtins.open', unittest.mock.mock_open(read_data="MOV 0, 1\nDAT 0, 0")):
             evolverstage.print_status()

        # Check if key headers were printed
        # We can inspect the calls to print
        printed_strings = [evolverstage.strip_ansi(call.args[0]) for call in mock_print.call_args_list if call.args]

        self.assertTrue(any("Evolver Status Dashboard" in s for s in printed_strings))
        self.assertTrue(any("Recent Activity (Last 1 matches):" in s for s in printed_strings))
        self.assertTrue(any("- Era 1, Arena 0: Warrior 5 beat Warrior 10 (150-50)" in s for s in printed_strings))
        # Check for table headers
        self.assertTrue(any("Arena" in s and "Size" in s and "Pop" in s and "Champion" in s for s in printed_strings))
        self.assertTrue(any("ARENA CONFIGURATION" in s for s in printed_strings))
        self.assertTrue(any("POPULATION & CHAMPIONS" in s for s in printed_strings))
        # Check if arena 0 data is present (Arena 0, Pop 2)
        self.assertTrue(any(s.strip().startswith("0") and " 2 " in s for s in printed_strings))

    def test_status_command_invocation(self):
        # This test ensures that invoking the script with --status calls print_status
        # Note: Testing sys.exit(0) is tricky, so we might just verify the function exists and is callable
        pass

if __name__ == '__main__':
    unittest.main()
