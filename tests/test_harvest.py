import sys
import os
import unittest
from unittest import mock

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestHarvest(unittest.TestCase):
    @mock.patch('evolverstage.get_leaderboard')
    @mock.patch('os.path.exists')
    @mock.patch('os.makedirs')
    @mock.patch('shutil.copy2')
    def test_run_harvest_success(self, mock_copy, mock_makedirs, mock_exists, mock_get_leaderboard):
        """Test successful harvesting of multiple warriors."""
        # Setup mock leaderboard
        mock_get_leaderboard.return_value = {
            0: [('1', 5), ('2', 3)],
            1: [('10', 8)]
        }
        # Mock battle log existence
        mock_exists.side_effect = lambda x: True

        evolverstage.run_harvest('test_dir', limit=5)

        # Verify makedirs called
        mock_makedirs.assert_called_with('test_dir', exist_ok=True)

        # Verify copies
        self.assertEqual(mock_copy.call_count, 3)

        # Check specific calls (order depends on dict iteration, but here it's sorted by arena ID in run_harvest?)
        # Actually run_harvest iterates over results.items(). In Python 3.7+, order is preserved.

        expected_calls = [
            mock.call(os.path.join('arena0', '1.red'), os.path.join('test_dir', 'arena0_rank1_streak5_id1.red')),
            mock.call(os.path.join('arena0', '2.red'), os.path.join('test_dir', 'arena0_rank2_streak3_id2.red')),
            mock.call(os.path.join('arena1', '10.red'), os.path.join('test_dir', 'arena1_rank1_streak8_id10.red'))
        ]
        mock_copy.assert_has_calls(expected_calls, any_order=True)

    @mock.patch('evolverstage.BATTLE_LOG_FILE', 'non_existent.csv')
    @mock.patch('os.path.exists')
    def test_run_harvest_no_log(self, mock_exists):
        """Test harvest fails gracefully when no log exists."""
        mock_exists.return_value = False

        with mock.patch('builtins.print') as mock_print:
            evolverstage.run_harvest('test_dir')
            mock_print.assert_called_with(mock.ANY)
            self.assertIn('No battle log found', mock_print.call_args[0][0])

    @mock.patch('evolverstage.get_leaderboard')
    @mock.patch('os.path.exists')
    def test_run_harvest_empty_leaderboard(self, mock_exists, mock_get_leaderboard):
        """Test harvest fails gracefully when leaderboard is empty."""
        mock_exists.return_value = True
        mock_get_leaderboard.return_value = {}

        with mock.patch('builtins.print') as mock_print:
            evolverstage.run_harvest('test_dir')
            mock_print.assert_called_with(mock.ANY)
            self.assertIn('No leaderboard data available', mock_print.call_args[0][0])

if __name__ == '__main__':
    unittest.main()
