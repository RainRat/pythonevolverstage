import sys
import os
import pytest
from unittest import mock

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestCoreMod:
    def test_positive_modulo(self):
        """Test basic modulo with positive numbers."""
        assert evolverstage.coremod(5, 10) == 5
        assert evolverstage.coremod(15, 10) == 5

    def test_negative_modulo(self):
        """Test modulo with negative numbers maintains negative sign."""
        assert evolverstage.coremod(-5, 10) == -5
        assert evolverstage.coremod(-15, 10) == -5

    def test_zero(self):
        """Test modulo with zero."""
        assert evolverstage.coremod(0, 10) == 0

    def test_large_numbers(self):
        """Test modulo with numbers larger than modulus."""
        assert evolverstage.coremod(105, 10) == 5
        assert evolverstage.coremod(-105, 10) == -5

class TestCoreNorm:
    def test_in_range_positive(self):
        """Test numbers already in positive range."""
        assert evolverstage.corenorm(10, 80) == 10
        assert evolverstage.corenorm(0, 80) == 0

    def test_in_range_negative(self):
        """Test numbers already in negative range."""
        assert evolverstage.corenorm(-10, 80) == -10
        assert evolverstage.corenorm(-39, 80) == -39

    def test_positive_wraparound(self):
        """Test positive numbers that wrap around to negative."""
        # 41 is > 80 // 2 (40). Should become -(80 - 41) = -39
        assert evolverstage.corenorm(41, 80) == -39
        # 50 > 40. -(80 - 50) = -30
        assert evolverstage.corenorm(50, 80) == -30

    def test_negative_wraparound(self):
        """Test negative numbers that wrap around to positive."""
        # -41 <= -(80 // 2) (-40). Should become 80 + -41 = 39
        assert evolverstage.corenorm(-41, 80) == 39
        # -50 <= -40. 80 + -50 = 30
        assert evolverstage.corenorm(-50, 80) == 30

    def test_boundary_values(self):
        """Test boundary conditions."""
        # y // 2 = 40
        # The implementation uses (-size/2, size/2] range preference.
        # x > 40 wraps down.
        # x <= -40 wraps up.

        # 40 is not > 40, so it stays 40.
        assert evolverstage.corenorm(40, 80) == 40

        # -40 is <= -40, so it wraps up: 80 + -40 = 40.
        assert evolverstage.corenorm(-40, 80) == 40

class TestCreateDirectory:
    def test_creates_directory_if_missing(self):
        """Test that os.mkdir is called if directory does not exist."""
        with mock.patch('evolverstage.os.path.exists') as mock_exists, \
             mock.patch('evolverstage.os.mkdir') as mock_mkdir:
            mock_exists.return_value = False
            evolverstage.create_directory_if_not_exists("new_dir")
            mock_mkdir.assert_called_once_with("new_dir")

    def test_does_not_create_if_exists(self):
        """Test that os.mkdir is NOT called if directory exists."""
        with mock.patch('evolverstage.os.path.exists') as mock_exists, \
             mock.patch('evolverstage.os.mkdir') as mock_mkdir:
            mock_exists.return_value = True
            evolverstage.create_directory_if_not_exists("existing_dir")
            mock_mkdir.assert_not_called()
