import sys
import pathlib
import unittest

# Add project root to sys.path
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evolverstage import _get_benchmark_id, _BENCHMARK_WARRIOR_ID_BASE

class TestBenchmarkUtils(unittest.TestCase):

    def test_get_benchmark_id_basic(self):
        """Test basic benchmark ID calculation."""
        # arena=0, bench_index=0
        # Expected: BASE - (0*1000 + 0) = BASE
        self.assertEqual(_get_benchmark_id(0, 0), _BENCHMARK_WARRIOR_ID_BASE)

    def test_get_benchmark_id_with_indices(self):
        """Test benchmark ID calculation with non-zero indices."""
        # arena=2, bench_index=5
        # Expected: BASE - (2*1000 + 5) = BASE - 2005
        expected = _BENCHMARK_WARRIOR_ID_BASE - 2005
        self.assertEqual(_get_benchmark_id(2, 5), expected)

    def test_get_benchmark_id_clamping(self):
        """Test that benchmark ID is clamped to minimum 1."""
        # Make the subtraction result in something <= 0
        # BASE is typically large (MAX - 10000 = ~55534)
        # We need (arena * 1000 + bench) >= BASE

        # Let's say BASE is 55534.
        # Arena = 60. 60 * 1000 = 60000.
        # BASE - 60000 = negative.
        # Result should be 1.

        large_arena_index = int(_BENCHMARK_WARRIOR_ID_BASE / 1000) + 10
        self.assertEqual(_get_benchmark_id(large_arena_index, 0), 1)

if __name__ == "__main__":
    unittest.main()
