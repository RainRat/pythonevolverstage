import sys
import os
import unittest
import shutil
import tempfile

# Add the root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestDiversityGaps(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_get_population_diversity_case_insensitivity(self):
        """Test that diversity calculation is case-insensitive."""
        os.makedirs("arena0", exist_ok=True)
        # Warrior 1: Uppercase
        with open("arena0/1.red", "w") as f:
            f.write("MOV.I $0, $1\n")
        # Warrior 2: Lowercase, logically same
        with open("arena0/2.red", "w") as f:
            f.write("mov.i $0, $1\n")

        # They should be considered the same logic. 1 unique / 2 total = 50%
        diversity = evolverstage.get_population_diversity(0)
        self.assertEqual(diversity, 50.0, "Diversity should be 50.0% for case-identical warriors")

    def test_get_population_diversity_line_joining(self):
        """Test that line joining doesn't cause collisions between different instruction sequences."""
        os.makedirs("arena0", exist_ok=True)
        # Warrior 1: Two instructions
        with open("arena0/1.red", "w") as f:
            f.write("MOV.I $0, $1\nADD.I $0, $1\n")
        # Warrior 2: Single instruction that could look like joined Warrior 1
        with open("arena0/2.red", "w") as f:
            f.write("MOV.I $0, $1ADD.I $0, $1\n")

        # They should be considered different. 2 unique / 2 total = 100%
        diversity = evolverstage.get_population_diversity(0)
        self.assertEqual(diversity, 100.0, "Diversity should be 100% for distinct instruction sequences")

if __name__ == '__main__':
    unittest.main()
