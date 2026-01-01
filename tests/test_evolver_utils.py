import sys
import os
import unittest
from unittest import mock

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestEvolverUtils(unittest.TestCase):
    # Tests for coremod
    def test_coremod_positive(self):
        """Test basic modulo with positive numbers."""
        self.assertEqual(evolverstage.coremod(5, 10), 5)
        self.assertEqual(evolverstage.coremod(15, 10), 5)

    def test_coremod_negative(self):
        """Test modulo with negative numbers maintains negative sign."""
        self.assertEqual(evolverstage.coremod(-5, 10), -5)
        self.assertEqual(evolverstage.coremod(-15, 10), -5)

    def test_coremod_zero(self):
        """Test modulo with zero."""
        self.assertEqual(evolverstage.coremod(0, 10), 0)

    def test_coremod_large_numbers(self):
        """Test modulo with numbers larger than modulus."""
        self.assertEqual(evolverstage.coremod(105, 10), 5)
        self.assertEqual(evolverstage.coremod(-105, 10), -5)

    # Tests for corenorm
    def test_corenorm_in_range_positive(self):
        """Test numbers already in positive range."""
        self.assertEqual(evolverstage.corenorm(10, 80), 10)
        self.assertEqual(evolverstage.corenorm(0, 80), 0)

    def test_corenorm_in_range_negative(self):
        """Test numbers already in negative range."""
        self.assertEqual(evolverstage.corenorm(-10, 80), -10)
        self.assertEqual(evolverstage.corenorm(-39, 80), -39)

    def test_corenorm_positive_wraparound(self):
        """Test positive numbers that wrap around to negative."""
        # 41 is > 80 // 2 (40). Should become -(80 - 41) = -39
        self.assertEqual(evolverstage.corenorm(41, 80), -39)
        # 50 > 40. -(80 - 50) = -30
        self.assertEqual(evolverstage.corenorm(50, 80), -30)

    def test_corenorm_negative_wraparound(self):
        """Test negative numbers that wrap around to positive."""
        # -41 <= -(80 // 2) (-40). Should become 80 + -41 = 39
        self.assertEqual(evolverstage.corenorm(-41, 80), 39)
        # -50 <= -40. 80 + -50 = 30
        self.assertEqual(evolverstage.corenorm(-50, 80), 30)

    def test_corenorm_boundary_values(self):
        """Test boundary conditions."""
        # 40 is not > 40, so it stays 40.
        self.assertEqual(evolverstage.corenorm(40, 80), 40)
        # -40 is <= -40, so it wraps up: 80 + -40 = 40.
        self.assertEqual(evolverstage.corenorm(-40, 80), 40)

    # Tests for create_directory_if_not_exists
    @mock.patch('evolverstage.os.path.exists')
    @mock.patch('evolverstage.os.mkdir')
    def test_create_dir_missing(self, mock_mkdir, mock_exists):
        """Test that os.mkdir is called if directory does not exist."""
        mock_exists.return_value = False
        evolverstage.create_directory_if_not_exists("new_dir")
        mock_mkdir.assert_called_once_with("new_dir")

    @mock.patch('evolverstage.os.path.exists')
    @mock.patch('evolverstage.os.mkdir')
    def test_create_dir_exists(self, mock_mkdir, mock_exists):
        """Test that os.mkdir is NOT called if directory exists."""
        mock_exists.return_value = True
        evolverstage.create_directory_if_not_exists("existing_dir")
        mock_mkdir.assert_not_called()
