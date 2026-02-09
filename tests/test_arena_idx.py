import sys
import unittest
from unittest import mock
import os

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestGetArenaIdx(unittest.TestCase):

    def test_default_value_when_no_flags_present(self):
        with mock.patch.object(sys, 'argv', ['evolverstage.py']):
            self.assertEqual(evolverstage._get_arena_idx(default=3), 3)

    def test_explicit_arena_long_flag(self):
        with mock.patch.object(sys, 'argv', ['evolverstage.py', '--arena', '5']):
            self.assertEqual(evolverstage._get_arena_idx(), 5)

    def test_explicit_arena_short_flag(self):
        with mock.patch.object(sys, 'argv', ['evolverstage.py', '-a', '2']):
            self.assertEqual(evolverstage._get_arena_idx(), 2)

    def test_smart_arena_inference_with_forward_slash_path(self):
        with mock.patch.object(sys, 'argv', ['evolverstage.py', '--battle', 'arena4/w1.red', 'arena4/w2.red']):
            self.assertEqual(evolverstage._get_arena_idx(), 4)

    def test_smart_arena_inference_with_backslash_path(self):
        with mock.patch.object(sys, 'argv', ['evolverstage.py', '--battle', 'arena7\\w1.red', 'arena7\\w2.red']):
            self.assertEqual(evolverstage._get_arena_idx(), 7)

    def test_explicit_arena_flag_overrides_smart_inference(self):
        with mock.patch.object(sys, 'argv', ['evolverstage.py', '--arena', '2', 'arena5/w1.red']):
            self.assertEqual(evolverstage._get_arena_idx(), 2)

if __name__ == '__main__':
    unittest.main()
