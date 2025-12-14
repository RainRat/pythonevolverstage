import sys
import pathlib
import pytest

# Add project root to sys.path
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from redcode import coremod

def test_coremod_positive_numbers():
    """Test coremod with positive numbers within and outside range."""
    assert coremod(5, 10) == 5
    assert coremod(15, 10) == 5
    assert coremod(25, 10) == 5

def test_coremod_negative_numbers():
    """Test coremod with negative numbers (wrapping behavior)."""
    assert coremod(-1, 10) == 9
    assert coremod(-5, 10) == 5
    assert coremod(-11, 10) == 9
    assert coremod(-20, 10) == 0

def test_coremod_zero_input():
    """Test coremod with zero input."""
    assert coremod(0, 10) == 0

def test_coremod_modulus_one():
    """Test coremod with modulus 1 (always 0)."""
    assert coremod(123, 1) == 0
    assert coremod(-123, 1) == 0
    assert coremod(0, 1) == 0

def test_coremod_rejects_zero_modulus():
    """Test that coremod raises ValueError for zero modulus."""
    with pytest.raises(ValueError, match="Modulus cannot be zero"):
        coremod(5, 0)

def test_coremod_large_numbers():
    """Test coremod with large numbers."""
    mod = 8000
    assert coremod(8001, mod) == 1
    assert coremod(-1, mod) == 7999
    assert coremod(mod * 10 + 5, mod) == 5
    assert coremod(-(mod * 10 + 5), mod) == mod - 5

def test_coremod_negative_modulus_consistency():
    """
    Test behavior with negative modulus.
    Note: Python's % operator returns result with same sign as divisor.
    5 % -3 = -1
    coremod should match this behavior if simplified.
    Current implementation: ((5 % -3) + -3) % -3 => (-1 -3) % -3 => -4 % -3 => -1.
    So it is consistent.
    """
    assert coremod(5, -3) == -1
    assert coremod(-5, -3) == -2
