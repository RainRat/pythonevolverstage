import sys
import os
import unittest
from unittest import mock
import shutil
import tempfile

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestExport(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for tests
        self.test_dir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.test_dir)

        # Mock global constants
        self.mock_config = {
            'CORESIZE_LIST': [8000],
            'CYCLES_LIST': [80000],
            'PROCESSES_LIST': [8000],
            'WARLEN_LIST': [100],
            'WARDISTANCE_LIST': [100],
            'SANITIZE_LIST': [8000],
            'LAST_ARENA': 0,
            'Colors': evolverstage.Colors
        }
        self.patchers = []
        for key, value in self.mock_config.items():
            p = mock.patch(f'evolverstage.{key}', value, create=True)
            p.start()
            self.patchers.append(p)

        # Create a source warrior
        os.makedirs('arena0', exist_ok=True)
        self.source_path = os.path.join('arena0', '1.red')
        with open(self.source_path, 'w') as f:
            f.write("MOV.I $0,$1\n")
            f.write("; a comment\n")
            f.write("DAT.F $0,$0\n")

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        os.chdir(self.old_cwd)
        shutil.rmtree(self.test_dir)

    @mock.patch('evolverstage._resolve_warrior_path')
    @mock.patch('evolverstage.get_leaderboard')
    def test_run_export_explicit_path(self, mock_get_leaderboard, mock_resolve):
        """Test exporting a warrior to an explicit file path."""
        mock_resolve.return_value = self.source_path
        mock_get_leaderboard.return_value = {}

        output_path = "my_export.red"
        evolverstage.run_export('1', output_path, 0)

        self.assertTrue(os.path.exists(output_path))
        with open(output_path, 'r') as f:
            lines = f.readlines()

        self.assertIn(";name 1\n", lines)
        self.assertIn(";author Python Core War Evolver\n", lines)
        self.assertIn("MOV.I $0,$1\n", lines)
        self.assertIn("DAT.F $0,$0\n", lines)
        # Comments should be filtered
        self.assertNotIn("; a comment\n", lines)

    @mock.patch('evolverstage._resolve_warrior_path')
    @mock.patch('evolverstage.get_leaderboard')
    def test_run_export_default_path(self, mock_get_leaderboard, mock_resolve):
        """Test exporting a warrior to the default file path."""
        mock_resolve.return_value = self.source_path
        mock_get_leaderboard.return_value = {}

        evolverstage.run_export('1', None, 0)

        expected_path = "exported_1.red"
        self.assertTrue(os.path.exists(expected_path))

    @mock.patch('evolverstage._resolve_warrior_path')
    @mock.patch('evolverstage.get_leaderboard')
    def test_run_export_to_directory(self, mock_get_leaderboard, mock_resolve):
        """Test exporting a warrior to a directory."""
        mock_resolve.return_value = self.source_path
        mock_get_leaderboard.return_value = {}

        export_dir = "exports"
        os.makedirs(export_dir)
        evolverstage.run_export('1', export_dir, 0)

        expected_path = os.path.join(export_dir, "1.red")
        self.assertTrue(os.path.exists(expected_path))

    @mock.patch('evolverstage._resolve_warrior_path')
    @mock.patch('evolverstage.get_leaderboard')
    def test_run_export_champion(self, mock_get_leaderboard, mock_resolve):
        """Test exporting a champion with win-streak info."""
        mock_resolve.return_value = self.source_path
        # Return leaderboard where '1' is champion with 5 wins
        mock_get_leaderboard.return_value = {0: [('1', 5)]}

        # We need to make sure _resolve_warrior_path(str(wid), arena_idx) == path matches in run_export
        # In run_export, it calls _resolve_warrior_path again.
        def resolve_side_effect(selector, arena_idx):
            if selector == 'top' or selector == '1':
                return self.source_path
            return selector
        mock_resolve.side_effect = resolve_side_effect

        output_path = "champ_export.red"
        evolverstage.run_export('top', output_path, 0)

        with open(output_path, 'r') as f:
            content = f.read()

        self.assertIn(";win-streak 5\n", content)
        self.assertIn(";name 1\n", content)

    @mock.patch('evolverstage._resolve_warrior_path')
    def test_run_export_not_found(self, mock_resolve):
        """Test handling of non-existent warrior."""
        mock_resolve.return_value = "non_existent.red"

        with mock.patch('builtins.print') as mock_print:
            evolverstage.run_export('999', 'out.red', 0)
            mock_print.assert_any_call("Error: Warrior '999' not found.")

        self.assertFalse(os.path.exists('out.red'))

    @mock.patch('evolverstage._resolve_warrior_path')
    def test_run_export_normalization(self, mock_resolve):
        """Test that instructions are normalized during export."""
        mock_resolve.return_value = self.source_path

        # Overwrite source with non-normalized code
        with open(self.source_path, 'w') as f:
            f.write("mov $0, $1\n") # lowercase, missing modifier

        output_path = "norm_export.red"
        evolverstage.run_export('1', output_path, 0)

        with open(output_path, 'r') as f:
            content = f.read()
        self.assertIn("MOV.I $0,$1\n", content)

    @mock.patch('evolverstage._resolve_warrior_path')
    def test_run_export_read_error(self, mock_resolve):
        """Test handling of file reading errors."""
        mock_resolve.return_value = self.source_path

        with mock.patch('builtins.open', side_effect=IOError("Disk failure")):
            with mock.patch('builtins.print') as mock_print:
                evolverstage.run_export('1', 'out.red', 0)
                mock_print.assert_any_call("Error reading warrior: Disk failure")

if __name__ == '__main__':
    unittest.main()
