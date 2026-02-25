import sys
import os
import unittest
from unittest import mock

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestRunCustomBattle(unittest.TestCase):
    def setUp(self):
        self.file1 = "warrior1.red"
        self.file2 = "warrior2.red"
        self.arena_idx = 0

        # Setup common mock configuration
        self.mock_config = {
            'LAST_ARENA': 1,
            'CORESIZE_LIST': [8000, 8000],
            'CYCLES_LIST': [80000, 80000],
            'PROCESSES_LIST': [8000, 8000],
            'WARLEN_LIST': [100, 100],
            'WARDISTANCE_LIST': [100, 100],
            'BATTLEROUNDS_LIST': [10, 50, 100] # Era 0, 1, 2
        }

    @mock.patch('evolverstage.run_nmars_subprocess')
    @mock.patch('os.path.exists')
    @mock.patch('builtins.print') # Suppress print output
    def test_run_custom_battle_success(self, mock_print, mock_exists, mock_run):
        """Test successful execution of a custom battle."""
        mock_exists.return_value = True
        mock_run.return_value = "Battle Output"

        # Patch config variables
        with mock.patch.multiple(evolverstage, **self.mock_config):
            # Also patch os.name to ensure consistent command name
            with mock.patch('evolverstage.os.name', 'posix'):
                evolverstage.run_custom_battle(self.file1, self.file2, self.arena_idx)

        # Verify run_nmars_subprocess was called
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]

        # Verify command arguments
        expected_cmd = [
            "nmars",
            self.file1,
            self.file2,
            "-s", "8000",
            "-c", "80000",
            "-p", "8000",
            "-l", "100",
            "-d", "100",
            "-r", "100" # Last element of BATTLEROUNDS_LIST
        ]
        self.assertEqual(cmd, expected_cmd)

    @mock.patch('evolverstage.run_nmars_subprocess')
    @mock.patch('os.path.exists')
    @mock.patch('builtins.print')
    def test_run_custom_battle_invalid_arena(self, mock_print, mock_exists, mock_run):
        """Test custom battle with invalid arena index."""
        mock_exists.return_value = True

        with mock.patch.multiple(evolverstage, **self.mock_config):
            # Try to run with arena index > LAST_ARENA (1)
            evolverstage.run_custom_battle(self.file1, self.file2, 2)

        # Verify nmars was NOT run
        mock_run.assert_not_called()

        # Verify error message printed
        mock_print.assert_any_call(f"Error: Arena 2 does not exist (LAST_ARENA=1)")

    @mock.patch('evolverstage.run_nmars_subprocess')
    @mock.patch('os.path.exists')
    @mock.patch('builtins.print')
    def test_run_custom_battle_missing_file1(self, mock_print, mock_exists, mock_run):
        """Test custom battle with missing first file."""
        # Side effect: False for file1, True for file2
        def exists_side_effect(path):
            return path != self.file1
        mock_exists.side_effect = exists_side_effect

        with mock.patch.multiple(evolverstage, **self.mock_config):
            evolverstage.run_custom_battle(self.file1, self.file2, self.arena_idx)

        mock_run.assert_not_called()
        mock_print.assert_any_call(f"Error: File '{self.file1}' not found.")

    @mock.patch('evolverstage.run_nmars_subprocess')
    @mock.patch('os.path.exists')
    @mock.patch('builtins.print')
    def test_run_custom_battle_missing_file2(self, mock_print, mock_exists, mock_run):
        """Test custom battle with missing second file."""
        def exists_side_effect(path):
            return path != self.file2
        mock_exists.side_effect = exists_side_effect

        with mock.patch.multiple(evolverstage, **self.mock_config):
            evolverstage.run_custom_battle(self.file1, self.file2, self.arena_idx)

        mock_run.assert_not_called()
        mock_print.assert_any_call(f"Error: File '{self.file2}' not found.")

    @mock.patch('evolverstage.run_nmars_subprocess')
    @mock.patch('os.path.exists')
    @mock.patch('builtins.print')
    def test_run_custom_battle_no_battlerounds(self, mock_print, mock_exists, mock_run):
        """Test custom battle fallback when BATTLEROUNDS_LIST is empty."""
        mock_exists.return_value = True

        config = self.mock_config.copy()
        config['BATTLEROUNDS_LIST'] = [] # Empty list

        with mock.patch.multiple(evolverstage, **config):
            with mock.patch('evolverstage.os.name', 'posix'):
                evolverstage.run_custom_battle(self.file1, self.file2, self.arena_idx)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]

        # Verify round count is default 100
        self.assertIn("-r", cmd)
        idx = cmd.index("-r")
        self.assertEqual(cmd[idx+1], "100")

    @mock.patch('evolverstage.run_nmars_subprocess')
    @mock.patch('os.path.exists')
    @mock.patch('builtins.print')
    def test_run_custom_battle_nmars_output(self, mock_print, mock_exists, mock_run):
        """Test that formatted battle result is printed when parsing succeeds."""
        mock_exists.return_value = True
        # nMars format: "1 name scores 100"
        mock_run.return_value = "1 warrior1.red scores 100\n2 warrior2.red scores 50"

        with mock.patch.multiple(evolverstage, **self.mock_config):
            with mock.patch('evolverstage.os.name', 'posix'):
                evolverstage.run_custom_battle(self.file1, self.file2, self.arena_idx)

        # Verify formatted output was printed
        # We check for the content, not the exact separator length which is terminal-aware
        found_header = False
        found_winner = False
        for call in mock_print.call_args_list:
            args, _ = call
            if len(args) > 0:
                if f"{evolverstage.Colors.BOLD}BATTLE RESULT (Arena 0){evolverstage.Colors.ENDC}" in args[0]:
                    found_header = True
                if f"  {evolverstage.Colors.BOLD}WINNER: {evolverstage.Colors.GREEN}warrior1.red{evolverstage.Colors.ENDC} (+50)" in args[0]:
                    found_winner = True

        self.assertTrue(found_header, "Battle result header not found in output")
        self.assertTrue(found_winner, "Winner announcement not found in output")

    @mock.patch('evolverstage.run_nmars_subprocess')
    @mock.patch('os.path.exists')
    @mock.patch('builtins.print')
    def test_run_custom_battle_tie(self, mock_print, mock_exists, mock_run):
        """Test that formatted battle result indicates a tie."""
        mock_exists.return_value = True
        mock_run.return_value = "1 warrior1.red scores 100\n2 warrior2.red scores 100"

        with mock.patch.multiple(evolverstage, **self.mock_config):
            with mock.patch('evolverstage.os.name', 'posix'):
                evolverstage.run_custom_battle(self.file1, self.file2, self.arena_idx)

        mock_print.assert_any_call(f"  {evolverstage.Colors.BOLD}{evolverstage.Colors.YELLOW}RESULT: TIE{evolverstage.Colors.ENDC}")

    @mock.patch('evolverstage.run_nmars_subprocess')
    @mock.patch('os.path.exists')
    @mock.patch('builtins.print')
    def test_run_custom_battle_parsing_fallback(self, mock_print, mock_exists, mock_run):
        """Test fallback to raw output if parsing fails."""
        mock_exists.return_value = True
        mock_run.return_value = "Some weird output without scores keyword"

        with mock.patch.multiple(evolverstage, **self.mock_config):
            with mock.patch('evolverstage.os.name', 'posix'):
                evolverstage.run_custom_battle(self.file1, self.file2, self.arena_idx)

        mock_print.assert_any_call("Some weird output without scores keyword")

    @mock.patch('evolverstage.run_nmars_subprocess')
    @mock.patch('os.path.exists')
    @mock.patch('builtins.print')
    def test_run_custom_battle_no_output(self, mock_print, mock_exists, mock_run):
        """Test handling of no output from nmars."""
        mock_exists.return_value = True
        mock_run.return_value = None

        with mock.patch.multiple(evolverstage, **self.mock_config):
            with mock.patch('evolverstage.os.name', 'posix'):
                evolverstage.run_custom_battle(self.file1, self.file2, self.arena_idx)

        mock_print.assert_any_call(f"{evolverstage.Colors.RED}No output received from nMars.{evolverstage.Colors.ENDC}")
