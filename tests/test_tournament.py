import sys
import os
import unittest
from unittest import mock

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestRunTournament(unittest.TestCase):
    def setUp(self):
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
    def test_run_tournament_invalid_arena(self, mock_print):
        """Test tournament with invalid arena index."""
        with mock.patch.multiple(evolverstage, **self.mock_config):
             evolverstage.run_tournament(self.directory, 2)

        mock_print.assert_any_call(f"Error: Arena 2 does not exist (LAST_ARENA=1)")

    @mock.patch('evolverstage._resolve_warrior_path')
    @mock.patch('os.path.exists')
    @mock.patch('builtins.print')
    def test_run_tournament_directory_not_found(self, mock_print, mock_exists, mock_resolve):
        """Test tournament with missing directory."""
        mock_exists.return_value = False
        mock_resolve.return_value = self.directory

        with mock.patch.multiple(evolverstage, **self.mock_config):
             evolverstage.run_tournament(self.directory, self.arena_idx)

        mock_print.assert_any_call(f"Error: Folder or selector '{self.directory}' not found.")

    @mock.patch('os.path.isdir')
    @mock.patch('os.listdir')
    @mock.patch('os.path.exists')
    @mock.patch('builtins.print')
    def test_run_tournament_insufficient_files(self, mock_print, mock_exists, mock_listdir, mock_isdir):
        """Test tournament with fewer than 2 .red files."""
        mock_exists.return_value = True
        mock_isdir.return_value = True
        mock_listdir.return_value = ['one.red'] # Only one file

        with mock.patch.multiple(evolverstage, **self.mock_config):
             evolverstage.run_tournament(self.directory, self.arena_idx)

        mock_print.assert_any_call(f"Error: A tournament requires at least two warriors (.red files) in the '{self.directory}' folder.")

    @mock.patch('evolverstage.run_nmars_subprocess')
    @mock.patch('evolverstage.parse_nmars_output')
    @mock.patch('os.path.isdir')
    @mock.patch('os.listdir')
    @mock.patch('os.path.exists')
    @mock.patch('builtins.print')
    def test_run_tournament_success(self, mock_print, mock_exists, mock_listdir, mock_isdir, mock_parse, mock_run):
        """Test successful tournament execution."""
        mock_exists.return_value = True
        mock_isdir.return_value = True
        files = ['warrior1.red', 'warrior2.red', 'warrior3.red']
        mock_listdir.return_value = files

        # Setup parse_nmars_output to return scores
        # We have 3 files. Pairs: (1,2), (1,3), (2,3)
        # 3 battles total.

        # Mock behaviors
        mock_run.return_value = "Battle Output"

        # Side effect for parse: returns (scores, warriors)
        # Battle 1: 1 vs 2. Let's say 1 wins (100-0)
        # Battle 2: 1 vs 3. 1 wins (100-0)
        # Battle 3: 2 vs 3. 2 wins (100-0)
        # Scores: W1=200, W2=100, W3=0

        def parse_side_effect(output):
            # We can't easily know which battle it is from just the output string in this mock setup
            # unless we inspect call args of run_nmars_subprocess, but parse is called with that result.
            # Simplified: always return [100, 0] for the pair.
            # This means the first warrior in the pair always gets 100, second 0.
            return [100, 0], [1, 2]

        mock_parse.side_effect = parse_side_effect

        with mock.patch.multiple(evolverstage, **self.mock_config):
             with mock.patch('evolverstage.os.name', 'posix'):
                evolverstage.run_tournament(self.directory, self.arena_idx)

        # Verify battles
        # 3 pairs
        self.assertEqual(mock_run.call_count, 3)

        # Verify printing of results
        # We expect a sorted list.
        # W1 was first in (1,2) and (1,3) -> 200 pts
        # W2 was second in (1,2) [0 pts] and first in (2,3) [100 pts] -> 100 pts
        # W3 was second in (1,3) [0 pts] and second in (2,3) [0 pts] -> 0 pts

        # Check that results are printed
        # Note: The function now prints a polished table.
        # Max score is (3-1)*100 = 200.
        # W1 (200 pts): bar is [====================]
        # W2 (100 pts): bar is [==========          ]
        # W3 (0 pts): bar is [                    ]

        bar1 = f"[{evolverstage.Colors.GREEN}{'=' * 20}{''}{evolverstage.Colors.ENDC}]"
        bar2 = f"[{evolverstage.Colors.ENDC}{'=' * 10}{' ' * 10}{evolverstage.Colors.ENDC}]"
        bar3 = f"[{evolverstage.Colors.ENDC}{'=' * 0}{' ' * 20}{evolverstage.Colors.ENDC}]"

        display_name1 = "warrior1.red"
        display_name2 = "warrior2.red"
        display_name3 = "warrior3.red"

        # In the enhanced version, we have a Strategy column between Warrior and Score
        # Strategy will be 'Unknown' because files don't exist in the mock filesystem
        strat = "Unknown"
        mock_print.assert_any_call(f"{1:>2}.  {display_name1:<25} {strat:<20} {evolverstage.Colors.GREEN}{200:>7}{evolverstage.Colors.ENDC}  {bar1}")
        mock_print.assert_any_call(f"{2:>2}.  {display_name2:<25} {strat:<20} {evolverstage.Colors.ENDC}{100:>7}{evolverstage.Colors.ENDC}  {bar2}")
        mock_print.assert_any_call(f"{3:>2}.  {display_name3:<25} {strat:<20} {evolverstage.Colors.ENDC}{0:>7}{evolverstage.Colors.ENDC}  {bar3}")

if __name__ == '__main__':
    unittest.main()
