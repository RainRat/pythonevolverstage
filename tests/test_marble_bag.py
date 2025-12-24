import sys
import os
import unittest
from unittest import mock

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage
from evolverstage import Marble

class TestMarbleBag(unittest.TestCase):
    @mock.patch('evolverstage.NOTHING_LIST', [10, 0, 0])
    @mock.patch('evolverstage.RANDOM_LIST', [0, 5, 0])
    @mock.patch('evolverstage.NAB_LIST', [0, 0, 3])
    @mock.patch('evolverstage.MINI_MUT_LIST', [0, 0, 0])
    @mock.patch('evolverstage.MICRO_MUT_LIST', [0, 0, 0])
    @mock.patch('evolverstage.LIBRARY_LIST', [0, 0, 0])
    @mock.patch('evolverstage.MAGIC_NUMBER_LIST', [0, 0, 0])
    def test_construct_marble_bag_era_0(self):
        """Test bag construction for Era 0 (index 0)."""
        bag = evolverstage.construct_marble_bag(0)
        # Should contain 10 DO_NOTHING marbles
        self.assertEqual(len(bag), 10)
        self.assertTrue(all(m == Marble.DO_NOTHING for m in bag))

    @mock.patch('evolverstage.NOTHING_LIST', [10, 0, 0])
    @mock.patch('evolverstage.RANDOM_LIST', [0, 5, 0])
    @mock.patch('evolverstage.NAB_LIST', [0, 0, 3])
    @mock.patch('evolverstage.MINI_MUT_LIST', [0, 0, 0])
    @mock.patch('evolverstage.MICRO_MUT_LIST', [0, 0, 0])
    @mock.patch('evolverstage.LIBRARY_LIST', [0, 0, 0])
    @mock.patch('evolverstage.MAGIC_NUMBER_LIST', [0, 0, 0])
    def test_construct_marble_bag_era_1(self):
        """Test bag construction for Era 1 (index 1)."""
        bag = evolverstage.construct_marble_bag(1)
        # Should contain 5 MAJOR_MUTATION marbles
        self.assertEqual(len(bag), 5)
        self.assertTrue(all(m == Marble.MAJOR_MUTATION for m in bag))

    @mock.patch('evolverstage.NOTHING_LIST', [10, 0, 0])
    @mock.patch('evolverstage.RANDOM_LIST', [0, 5, 0])
    @mock.patch('evolverstage.NAB_LIST', [0, 0, 3])
    @mock.patch('evolverstage.MINI_MUT_LIST', [0, 0, 0])
    @mock.patch('evolverstage.MICRO_MUT_LIST', [0, 0, 0])
    @mock.patch('evolverstage.LIBRARY_LIST', [0, 0, 0])
    @mock.patch('evolverstage.MAGIC_NUMBER_LIST', [0, 0, 0])
    def test_construct_marble_bag_era_2(self):
        """Test bag construction for Era 2 (index 2)."""
        bag = evolverstage.construct_marble_bag(2)
        # Should contain 3 NAB_INSTRUCTION marbles
        self.assertEqual(len(bag), 3)
        self.assertTrue(all(m == Marble.NAB_INSTRUCTION for m in bag))

    @mock.patch('evolverstage.NOTHING_LIST', [1, 1, 1])
    @mock.patch('evolverstage.RANDOM_LIST', [1, 1, 1])
    @mock.patch('evolverstage.NAB_LIST', [1, 1, 1])
    @mock.patch('evolverstage.MINI_MUT_LIST', [1, 1, 1])
    @mock.patch('evolverstage.MICRO_MUT_LIST', [1, 1, 1])
    @mock.patch('evolverstage.LIBRARY_LIST', [1, 1, 1])
    @mock.patch('evolverstage.MAGIC_NUMBER_LIST', [1, 1, 1])
    def test_construct_marble_bag_mixed(self):
        """Test bag construction with mixed marble types."""
        bag = evolverstage.construct_marble_bag(0)
        # Should contain 1 of each (7 total types)
        self.assertEqual(len(bag), 7)
        self.assertEqual(bag.count(Marble.DO_NOTHING), 1)
        self.assertEqual(bag.count(Marble.MAJOR_MUTATION), 1)
        self.assertEqual(bag.count(Marble.NAB_INSTRUCTION), 1)
        self.assertEqual(bag.count(Marble.MINOR_MUTATION), 1)
        self.assertEqual(bag.count(Marble.MICRO_MUTATION), 1)
        self.assertEqual(bag.count(Marble.INSTRUCTION_LIBRARY), 1)
        self.assertEqual(bag.count(Marble.MAGIC_NUMBER_MUTATION), 1)
