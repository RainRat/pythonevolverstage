import sys
import os
import unittest
from unittest import mock

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestComparativeTournament(unittest.TestCase):

    def test_resolve_warrior_path_with_arena_override(self):
        """Test that @N suffix correctly overrides the arena index."""
        # Setup: Arena 0 has warrior 123, Arena 1 has warrior 456
        with mock.patch('evolverstage.get_leaderboard') as mock_lb, \
             mock.patch('os.path.exists') as mock_exists, \
             mock.patch('os.listdir') as mock_listdir:

            mock_lb.return_value = {
                0: [('123', 5)],
                1: [('456', 10)]
            }

            def side_effect_exists(path):
                # Normalize paths for comparison (handle both / and \)
                norm_path = os.path.normpath(path)
                if norm_path == os.path.normpath(os.path.join("arena0", "123.red")): return True
                if norm_path == os.path.normpath(os.path.join("arena1", "456.red")): return True
                if norm_path == "arena1": return True
                if norm_path == os.path.normpath(os.path.join("arena1", "789.red")): return True
                return False

            mock_exists.side_effect = side_effect_exists
            mock_listdir.return_value = ["789.red"]

            # 1. Basic selector without override uses default arena
            path1 = evolverstage._resolve_warrior_path("top", 0)
            self.assertEqual(os.path.normpath(path1), os.path.normpath(os.path.join("arena0", "123.red")))

            # 2. Selector with override uses specified arena
            path2 = evolverstage._resolve_warrior_path("top@1", 0)
            self.assertEqual(os.path.normpath(path2), os.path.normpath(os.path.join("arena1", "456.red")))

            # 3. Random selector with override
            path3 = evolverstage._resolve_warrior_path("random@1", 0)
            self.assertEqual(os.path.normpath(path3), os.path.normpath(os.path.join("arena1", "789.red")))

    @mock.patch('evolverstage._resolve_warrior_path')
    @mock.patch('os.path.isdir')
    @mock.patch('os.path.exists')
    @mock.patch('evolverstage.run_nmars_subprocess')
    @mock.patch('evolverstage.CORESIZE_LIST', [8000, 8000])
    @mock.patch('evolverstage.CYCLES_LIST', [80000, 80000])
    @mock.patch('evolverstage.PROCESSES_LIST', [8000, 8000])
    @mock.patch('evolverstage.WARLEN_LIST', [100, 100])
    @mock.patch('evolverstage.WARDISTANCE_LIST', [100, 100])
    @mock.patch('evolverstage.BATTLEROUNDS_LIST', [100, 100, 100])
    @mock.patch('evolverstage.LAST_ARENA', 1)
    def test_run_tournament_with_multiple_selectors(self, mock_nmars, mock_exists, mock_isdir, mock_resolve):
        """Test run_tournament with a list of selectors."""
        mock_isdir.return_value = False
        mock_exists.return_value = True
        # Need 4 return values: 2 for initial resolution, 2 for strategy identification in standings
        mock_resolve.side_effect = ["arena0/1.red", "arena1/2.red", "arena0/1.red", "arena1/2.red"]
        mock_nmars.return_value = "1 scores 100\n2 scores 50\n"

        # Should run 1 battle for 2 warriors
        evolverstage.run_tournament(["top@0", "top@1"], 0)

        self.assertEqual(mock_nmars.call_count, 1)
        # Check that it resolved targets both initially and for strategy
        self.assertEqual(mock_resolve.call_count, 4)

    @mock.patch('evolverstage._resolve_warrior_path')
    @mock.patch('os.path.isdir')
    @mock.patch('os.path.exists')
    def test_run_tournament_directory_fallback(self, mock_exists, mock_isdir, mock_resolve):
        """Test that it still supports directory-based tournaments (backward compatibility)."""
        mock_isdir.return_value = True
        mock_exists.return_value = True
        mock_resolve.side_effect = ["w2.red", "w1.red"]

        with mock.patch('os.listdir') as mock_listdir:
            mock_listdir.return_value = ["w1.red", "w2.red"]
            with mock.patch('evolverstage.construct_battle_command'), \
                 mock.patch('evolverstage.run_nmars_subprocess') as mock_nmars:
                mock_nmars.return_value = "1 scores 10\n2 scores 20\n"

                evolverstage.run_tournament(["my_dir"], 0)

                # Should have found 2 files and run 1 battle
                self.assertEqual(mock_nmars.call_count, 1)
                # Now calls _resolve_warrior_path for strategy identification in results
                self.assertEqual(mock_resolve.call_count, 2)

if __name__ == '__main__':
    unittest.main()
