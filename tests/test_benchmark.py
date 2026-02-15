import sys
import os
import unittest
from unittest import mock

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestRunBenchmark(unittest.TestCase):
    def setUp(self):
        self.warrior_file = "mywarrior.red"
        self.directory = "warriors_dir"
        self.arena_idx = 0

        # Setup common mock configuration
        self.mock_config = {
            'LAST_ARENA': 1,
            'CORESIZE_LIST': [8000, 8000],
            'CYCLES_LIST': [80000, 80000],
            'PROCESSES_LIST': [8000, 8000],
            'WARLEN_LIST': [100, 100],
            'WARDISTANCE_LIST': [100, 100],
            'BATTLEROUNDS_LIST': [10, 50, 100]
        }

    @mock.patch('builtins.print')
    def test_run_benchmark_invalid_arena(self, mock_print):
        """Test benchmark with invalid arena index."""
        with mock.patch.multiple(evolverstage, **self.mock_config):
             evolverstage.run_benchmark(self.warrior_file, self.directory, 2)

        mock_print.assert_any_call(f"Error: Arena 2 does not exist (LAST_ARENA=1)")

    @mock.patch('os.path.exists')
    @mock.patch('builtins.print')
    def test_run_benchmark_missing_warrior(self, mock_print, mock_exists):
        """Test benchmark with missing warrior file."""
        # Side effect: False for warrior_file, True for directory
        def exists_side_effect(path):
            return path != self.warrior_file
        mock_exists.side_effect = exists_side_effect

        with mock.patch.multiple(evolverstage, **self.mock_config):
             evolverstage.run_benchmark(self.warrior_file, self.directory, self.arena_idx)

        mock_print.assert_any_call(f"Error: File '{self.warrior_file}' not found.")

    @mock.patch('os.path.exists')
    @mock.patch('builtins.print')
    def test_run_benchmark_missing_directory(self, mock_print, mock_exists):
        """Test benchmark with missing directory."""
        # Side effect: True for warrior_file, False for directory
        def exists_side_effect(path):
            return path != self.directory
        mock_exists.side_effect = exists_side_effect

        with mock.patch.multiple(evolverstage, **self.mock_config):
             evolverstage.run_benchmark(self.warrior_file, self.directory, self.arena_idx)

        mock_print.assert_any_call(f"Error: Folder '{self.directory}' not found.")

    @mock.patch('os.listdir')
    @mock.patch('os.path.exists')
    @mock.patch('builtins.print')
    def test_run_benchmark_no_opponents(self, mock_print, mock_exists, mock_listdir):
        """Test benchmark when directory has no .red files."""
        mock_exists.return_value = True
        mock_listdir.return_value = [] # No files

        with mock.patch.multiple(evolverstage, **self.mock_config):
             evolverstage.run_benchmark(self.warrior_file, self.directory, self.arena_idx)

        mock_print.assert_any_call(f"Error: No opponents found. Please ensure the folder '{self.directory}' contains .red files.")

    @mock.patch('evolverstage.run_nmars_subprocess')
    @mock.patch('evolverstage.parse_nmars_output')
    @mock.patch('os.listdir')
    @mock.patch('os.path.exists')
    @mock.patch('builtins.print')
    def test_run_benchmark_success(self, mock_print, mock_exists, mock_listdir, mock_parse, mock_run):
        """Test successful benchmark execution with wins, losses, and ties."""
        mock_exists.return_value = True
        # 3 opponents
        opponents = ['opp1.red', 'opp2.red', 'opp3.red']
        mock_listdir.return_value = opponents
        mock_run.return_value = "Battle Output"

        # We need to simulate 3 battles.
        # Battle 1: Win (ID 1 > ID 2)
        # Battle 2: Loss (ID 1 < ID 2)
        # Battle 3: Tie (ID 1 == ID 2)

        # parse_nmars_output returns (scores, warriors)
        # warriors is list of IDs, scores is list of scores
        # run_benchmark assumes warrior_file is ID 1, opponent is ID 2.

        side_effects = [
            ([100, 50], [1, 2]), # Win: 100 > 50
            ([20, 80], [1, 2]),  # Loss: 20 < 80
            ([50, 50], [1, 2])   # Tie: 50 == 50
        ]
        mock_parse.side_effect = side_effects

        with mock.patch.multiple(evolverstage, **self.mock_config):
             with mock.patch('evolverstage.os.name', 'posix'):
                evolverstage.run_benchmark(self.warrior_file, self.directory, self.arena_idx)

        # Verify calls
        self.assertEqual(mock_run.call_count, 3)

        # Verify Results
        # Total Score: 100 + 20 + 50 = 170
        # Wins: 1, Losses: 1, Ties: 1

        # Check printed output
        # Use str() for partial matching if needed, or exact calls

        # Check Win stats
        # "  Wins:   1 (33.3%)"
        mock_print.assert_any_call(f"  {evolverstage.Colors.GREEN}Wins:   1 (33.3%){evolverstage.Colors.ENDC}")

        # Check Loss stats
        mock_print.assert_any_call(f"  {evolverstage.Colors.RED}Losses: 1 (33.3%){evolverstage.Colors.ENDC}")

        # Check Tie stats
        mock_print.assert_any_call(f"  {evolverstage.Colors.YELLOW}Ties:   1 (33.3%){evolverstage.Colors.ENDC}")

        # Check Total Score
        mock_print.assert_any_call("  Total Score: 170")

        # Check Average Score: 170 / 3 = 56.67
        mock_print.assert_any_call("  Average Score: 56.67")
