import sys
import os
import unittest
import tempfile
import shutil

# Add the root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestPopulationDiversityGaps(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_diversity_internal_whitespace(self):
        """Test that internal whitespace doesn't affect diversity."""
        os.makedirs("arena0", exist_ok=True)
        # Warrior 1: Standard whitespace
        with open("arena0/1.red", "w") as f:
            f.write("MOV.I $0, $1\n")
        # Warrior 2: Logical duplicate but different internal whitespace
        with open("arena0/2.red", "w") as f:
            f.write("MOV.I  $0,   $1\n")

        # They should be considered identical, so diversity = (1/2) * 100 = 50%
        diversity = evolverstage.get_population_diversity(0)
        self.assertEqual(diversity, 50.0)

    def test_diversity_trailing_comments(self):
        """Test that trailing comments don't affect diversity."""
        os.makedirs("arena0", exist_ok=True)
        # Warrior 1: No comment
        with open("arena0/1.red", "w") as f:
            f.write("MOV.I $0, $1\n")
        # Warrior 2: Logical duplicate with trailing comment
        with open("arena0/2.red", "w") as f:
            f.write("MOV.I $0, $1 ; this is a comment\n")

        # They should be considered identical, so diversity = 50%
        diversity = evolverstage.get_population_diversity(0)
        self.assertEqual(diversity, 50.0)

    def test_diversity_unreadable_files(self):
        """Test that unreadable files don't skew the percentage denominator."""
        os.makedirs("arena0", exist_ok=True)
        # Unique warrior
        with open("arena0/1.red", "w") as f:
            f.write("MOV.I $0, $1\n")

        # Create another file but make it unreadable
        bad_file = "arena0/2.red"
        with open(bad_file, "w") as f:
            f.write("CANNOT READ ME\n")
        os.chmod(bad_file, 0) # No permissions

        # If it skips bad_file, it should only count 1 file in total.
        # Diversity among readable files is 100% (1 unique out of 1 total).
        # Currently, it counts 2 files, so result would be (1/2)*100 = 50%
        diversity = evolverstage.get_population_diversity(0)

        # We expect it to be 100% if we only count successfully analyzed files
        self.assertEqual(diversity, 100.0)

if __name__ == '__main__':
    unittest.main()
