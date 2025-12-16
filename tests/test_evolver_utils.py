import sys
import os
import pytest

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
