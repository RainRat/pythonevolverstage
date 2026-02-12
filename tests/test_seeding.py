import sys
import os
import unittest
from unittest import mock
import shutil
import tempfile

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestSeeding(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for tests
        self.test_dir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.test_dir)

        # Mock global constants to avoid reading settings.ini
        evolverstage.LAST_ARENA = 1
        evolverstage.NUMWARRIORS = 5
        evolverstage.WARLEN_LIST = [5, 10]
        evolverstage.CORESIZE_LIST = [80, 800]
        evolverstage.SANITIZE_LIST = [80, 800]
        evolverstage.Colors.GREEN = '' # Disable colors for tests
        evolverstage.Colors.ENDC = ''

        # Create a source warrior
        self.source_dir = os.path.join(self.test_dir, 'source')
        os.makedirs(self.source_dir)
        self.warrior_path = os.path.join(self.source_dir, 'warrior1.red')
        with open(self.warrior_path, 'w') as f:
            f.write("MOV.I $0,$1\n")
            f.write("SPL.B $1,$2\n")

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.test_dir)

    def test_run_seeding_single_file(self):
        """Test seeding an arena from a single file."""
        evolverstage.run_seeding([self.warrior_path], arena_idx=0)

        arena_dir = 'arena0'
        self.assertTrue(os.path.exists(arena_dir))
        files = os.listdir(arena_dir)
        self.assertEqual(len(files), 5) # NUMWARRIORS

        # Check one file content
        with open(os.path.join(arena_dir, '1.red'), 'r') as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 5) # WARLEN_LIST[0]
        # normalize_instruction adds .I and standardizes
        self.assertIn("MOV.I $0,$1", lines[0])
        self.assertIn("SPL.B $1,$2", lines[1])
        self.assertIn("DAT.F $0,$0", lines[2]) # Padding

    def test_run_seeding_directory(self):
        """Test seeding from a directory."""
        # Add another warrior
        with open(os.path.join(self.source_dir, 'warrior2.red'), 'w') as f:
            f.write("ADD.AB #5,$0\n")

        evolverstage.run_seeding([self.source_dir], arena_idx=1)

        arena_dir = 'arena1'
        files = sorted(os.listdir(arena_dir), key=lambda x: int(x.split('.')[0]) if x.split('.')[0].isdigit() else 0)
        self.assertEqual(len(files), 5)

        # Check cycling: 1.red from warrior1, 2.red from warrior2, 3.red from warrior1...
        with open(os.path.join(arena_dir, '1.red'), 'r') as f:
            self.assertIn("MOV.I", f.read())
        with open(os.path.join(arena_dir, '2.red'), 'r') as f:
            self.assertIn("ADD.AB", f.read())
        with open(os.path.join(arena_dir, '3.red'), 'r') as f:
            self.assertIn("MOV.I", f.read())

    def test_run_seeding_all_arenas(self):
        """Test seeding all arenas when arena_idx is None."""
        evolverstage.run_seeding([self.warrior_path], arena_idx=None)

        self.assertTrue(os.path.exists('arena0'))
        self.assertTrue(os.path.exists('arena1'))

        with open('arena0/1.red', 'r') as f:
            self.assertEqual(len(f.readlines()), 5)
        with open('arena1/1.red', 'r') as f:
            self.assertEqual(len(f.readlines()), 10)

    def test_run_seeding_with_selector(self):
        """Test seeding using a dynamic selector (mocked)."""
        with mock.patch('evolverstage._resolve_warrior_path') as mock_resolve:
            mock_resolve.return_value = self.warrior_path
            evolverstage.run_seeding(['top'], arena_idx=0)
            mock_resolve.assert_called_with('top', 0)
            self.assertTrue(os.path.exists('arena0/1.red'))

if __name__ == '__main__':
    unittest.main()
