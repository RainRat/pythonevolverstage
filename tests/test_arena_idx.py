import sys
import unittest
from unittest import mock
import os

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestArenaIdx(unittest.TestCase):
    def test_explicit_flag_long(self):
        """Test --arena flag."""
        with mock.patch.object(sys, 'argv', ['evolverstage.py', '--arena', '5']):
            self.assertEqual(evolverstage._get_arena_idx(), 5)

    def test_explicit_flag_short(self):
        """Test -a flag."""
        with mock.patch.object(sys, 'argv', ['evolverstage.py', '-a', '3']):
            self.assertEqual(evolverstage._get_arena_idx(), 3)

    def test_path_inference_posix(self):
        """Test inference from POSIX path."""
        with mock.patch.object(sys, 'argv', ['evolverstage.py', '--battle', 'arena2/warrior.red', 'arena2/opp.red']):
            self.assertEqual(evolverstage._get_arena_idx(), 2)

    def test_path_inference_windows(self):
        """Test inference from Windows path."""
        with mock.patch.object(sys, 'argv', ['evolverstage.py', '--view', 'arena4\\winner.red']):
            self.assertEqual(evolverstage._get_arena_idx(), 4)

    def test_selector_inference(self):
        """Test inference from @N selector."""
        with mock.patch.object(sys, 'argv', ['evolverstage.py', '--analyze', 'top@7']):
            self.assertEqual(evolverstage._get_arena_idx(), 7)

    def test_explicit_overrides_inference(self):
        """Test that explicit flag takes precedence over inference."""
        with mock.patch.object(sys, 'argv', ['evolverstage.py', '--arena', '0', 'arena5/warrior.red']):
            self.assertEqual(evolverstage._get_arena_idx(), 0)

    def test_default_value(self):
        """Test default value when no arena info is present."""
        with mock.patch.object(sys, 'argv', ['evolverstage.py', '--status']):
            self.assertEqual(evolverstage._get_arena_idx(default=10), 10)

    def test_no_args_uses_default(self):
        """Test that it uses the provided default when no arguments match."""
        with mock.patch.object(sys, 'argv', ['evolverstage.py']):
            self.assertEqual(evolverstage._get_arena_idx(default=0), 0)

if __name__ == '__main__':
    unittest.main()
