import sys
import os
import unittest
from unittest import mock

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestPairwiseExtraction(unittest.TestCase):
    def test_extract_no_targets(self):
        """Test extraction when no targets are provided."""
        with mock.patch.object(sys, 'argv', ['evolverstage.py', '--battle']):
            t1, t2 = evolverstage._extract_pairwise_targets(1)
            self.assertEqual(t1, "top1")
            self.assertEqual(t2, "top2")

    def test_extract_one_target_not_top(self):
        """Test extraction when one non-top target is provided."""
        with mock.patch.object(sys, 'argv', ['evolverstage.py', '--battle', 'warrior1.red']):
            t1, t2 = evolverstage._extract_pairwise_targets(1)
            self.assertEqual(t1, "warrior1.red")
            self.assertEqual(t2, "top1")

    def test_extract_one_target_is_top(self):
        """Test extraction when one target 'top' is provided."""
        with mock.patch.object(sys, 'argv', ['evolverstage.py', '--battle', 'top']):
            t1, t2 = evolverstage._extract_pairwise_targets(1)
            self.assertEqual(t1, "top")
            self.assertEqual(t2, "top2")

    def test_extract_one_target_is_top1(self):
        """Test extraction when one target 'top1' is provided."""
        with mock.patch.object(sys, 'argv', ['evolverstage.py', '--battle', 'top1']):
            t1, t2 = evolverstage._extract_pairwise_targets(1)
            self.assertEqual(t1, "top1")
            self.assertEqual(t2, "top2")

    def test_extract_two_targets(self):
        """Test extraction when two targets are provided."""
        with mock.patch.object(sys, 'argv', ['evolverstage.py', '--battle', 'w1.red', 'w2.red']):
            t1, t2 = evolverstage._extract_pairwise_targets(1)
            self.assertEqual(t1, "w1.red")
            self.assertEqual(t2, "w2.red")

    def test_extract_targets_before_next_flag(self):
        """Test that extraction stops at the next flag."""
        with mock.patch.object(sys, 'argv', ['evolverstage.py', '--battle', 'w1.red', '--arena', '2']):
            t1, t2 = evolverstage._extract_pairwise_targets(1)
            self.assertEqual(t1, "w1.red")
            self.assertEqual(t2, "top1")

    def test_extract_zero_targets_before_next_flag(self):
        """Test extraction with no targets before the next flag."""
        with mock.patch.object(sys, 'argv', ['evolverstage.py', '--battle', '--arena', '2']):
            t1, t2 = evolverstage._extract_pairwise_targets(1)
            self.assertEqual(t1, "top1")
            self.assertEqual(t2, "top2")
