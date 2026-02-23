import sys
import os
import unittest
from unittest import mock

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestRunGauntlet(unittest.TestCase):
    def setUp(self):
        self.target = "my_warrior"
        self.arena_idx = 0

        # Setup common mock configuration
        self.mock_config = {
            'LAST_ARENA': 1, # Two arenas: 0 and 1
            'CORESIZE_LIST': [80, 800],
            'CYCLES_LIST': [800, 8000],
            'PROCESSES_LIST': [80, 800],
            'WARLEN_LIST': [5, 20],
            'WARDISTANCE_LIST': [5, 20],
            'BATTLEROUNDS_LIST': [10, 50, 100],
            'NUMWARRIORS': 50
        }

    @mock.patch('evolverstage.run_nmars_subprocess')
    @mock.patch('evolverstage._resolve_warrior_path')
    @mock.patch('evolverstage.analyze_warrior')
    @mock.patch('evolverstage.identify_strategy')
    @mock.patch('os.path.exists')
    @mock.patch('builtins.print')
    def test_run_gauntlet_success(self, mock_print, mock_exists, mock_strat, mock_analyze, mock_resolve, mock_run):
        """Test successful execution of the gauntlet."""
        # 1. Setup mocks
        mock_exists.return_value = True

        def resolve_side_effect(sel, a_idx):
            if sel == "top":
                return f"arena{a_idx}/top.red"
            return f"arena{a_idx}/{sel}.red"
        mock_resolve.side_effect = resolve_side_effect

        mock_analyze.return_value = {}
        mock_strat.return_value = "Test Strategy"

        # nMars format: "ID name scores Score"
        # First call (Arena 0): Target (ID 1) wins 100-0
        # Second call (Arena 1): Target (ID 1) loses 0-100
        mock_run.side_effect = [
            "1 target scores 100\n2 champ0 scores 0",
            "1 target scores 0\n2 champ1 scores 100"
        ]

        # 2. Run gauntlet
        with mock.patch.multiple(evolverstage, **self.mock_config):
            evolverstage.run_gauntlet(self.target, self.arena_idx)

        # 3. Verify
        # Should be called twice (for Arena 0 and Arena 1)
        self.assertEqual(mock_run.call_count, 2)

        # Check overall performance summary
        # 1 Win, 0 Ties, 1 Loss (50.0% win rate)
        mock_print.assert_any_call(f"{evolverstage.Colors.BOLD}OVERALL PERFORMANCE:{evolverstage.Colors.ENDC} 1 Wins, 0 Ties, 1 Losses (50.0% win rate)")

    @mock.patch('evolverstage.run_nmars_subprocess')
    @mock.patch('evolverstage._resolve_warrior_path')
    @mock.patch('evolverstage.analyze_warrior')
    @mock.patch('evolverstage.identify_strategy')
    @mock.patch('os.path.exists')
    @mock.patch('builtins.print')
    def test_run_gauntlet_tie(self, mock_print, mock_exists, mock_strat, mock_analyze, mock_resolve, mock_run):
        """Test gauntlet with a tie result."""
        mock_exists.return_value = True
        mock_resolve.side_effect = lambda sel, a_idx: f"arena{a_idx}/{sel}.red"
        mock_analyze.return_value = {}
        mock_strat.return_value = "Test Strategy"

        # Two ties
        mock_run.side_effect = [
            "1 target scores 50\n2 champ0 scores 50",
            "1 target scores 50\n2 champ1 scores 50"
        ]

        with mock.patch.multiple(evolverstage, **self.mock_config):
            evolverstage.run_gauntlet(self.target, self.arena_idx)

        # 0 Wins, 2 Ties, 0 Losses (0.0% win rate)
        mock_print.assert_any_call(f"{evolverstage.Colors.BOLD}OVERALL PERFORMANCE:{evolverstage.Colors.ENDC} 0 Wins, 2 Ties, 0 Losses (0.0% win rate)")

    @mock.patch('evolverstage._resolve_warrior_path')
    @mock.patch('os.path.exists')
    @mock.patch('builtins.print')
    def test_run_gauntlet_target_not_found(self, mock_print, mock_exists, mock_resolve):
        """Test gauntlet with missing target warrior."""
        mock_exists.return_value = False
        mock_resolve.return_value = "missing.red"

        with mock.patch.multiple(evolverstage, **self.mock_config):
            evolverstage.run_gauntlet("missing", self.arena_idx)

        mock_print.assert_any_call(f"{evolverstage.Colors.RED}Error: Warrior 'missing' not found.{evolverstage.Colors.ENDC}")

if __name__ == '__main__':
    unittest.main()
