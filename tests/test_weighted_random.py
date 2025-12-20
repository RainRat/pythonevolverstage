import sys
import os
import unittest
from unittest import mock

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestWeightedRandomNumber(unittest.TestCase):
    @mock.patch('random.randint')
    def test_major_branch(self, mock_randint):
        """Test the 1/4 chance branch where it returns range [-size, size]."""
        # The logic is:
        # if random.randint(1,4) == 1:
        #    return random.randint(-size, size)

        # We need mock_randint to return 1 first, then return some value (e.g. 42).
        mock_randint.side_effect = [1, 42]

        size = 8000
        length = 100

        result = evolverstage.weighted_random_number(size, length)

        self.assertEqual(result, 42)

        # Verify calls
        # Call 1: random.randint(1, 4)
        # Call 2: random.randint(-size, size)
        self.assertEqual(mock_randint.call_count, 2)

        # Check arguments of the second call
        args, _ = mock_randint.call_args_list[1]
        self.assertEqual(args, (-size, size))

    @mock.patch('random.randint')
    def test_minor_branch(self, mock_randint):
        """Test the 3/4 chance branch where it returns range [-length, length]."""
        # The logic is:
        # if random.randint(1,4) == 1: ...
        # else: return random.randint(-length, length)

        # We need mock_randint to return something other than 1 first (e.g. 2),
        # then return some value (e.g. 7).
        mock_randint.side_effect = [2, 7]

        size = 8000
        length = 100

        result = evolverstage.weighted_random_number(size, length)

        self.assertEqual(result, 7)

        # Verify calls
        # Call 1: random.randint(1, 4)
        # Call 2: random.randint(-length, length)
        self.assertEqual(mock_randint.call_count, 2)

        # Check arguments of the second call
        args, _ = mock_randint.call_args_list[1]
        self.assertEqual(args, (-length, length))
