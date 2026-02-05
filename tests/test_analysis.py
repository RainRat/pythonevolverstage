
import unittest
import os
import shutil
import json
from evolverstage import analyze_warrior, analyze_population

class TestAnalysis(unittest.TestCase):
    def setUp(self):
        self.test_dir = "test_analysis_dir"
        if not os.path.exists(self.test_dir):
            os.makedirs(self.test_dir)

        # Create a sample warrior
        self.warrior1_path = os.path.join(self.test_dir, "w1.red")
        with open(self.warrior1_path, "w") as f:
            f.write("MOV.I #1, $2\n")
            f.write("SPL.A @3, <4\n")
            f.write("DAT.F $0, $0\n")
            f.write("; a comment\n")
            f.write("\n")
            f.write("MOV.I #1, $2\n") # Duplicate for vocabulary test

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_analyze_warrior(self):
        stats = analyze_warrior(self.warrior1_path)
        self.assertIsNotNone(stats)
        self.assertEqual(stats['instructions'], 4)
        self.assertEqual(stats['opcodes']['MOV'], 2)
        self.assertEqual(stats['opcodes']['SPL'], 1)
        self.assertEqual(stats['opcodes']['DAT'], 1)
        self.assertEqual(stats['modifiers']['I'], 2)
        self.assertEqual(stats['modifiers']['A'], 1)
        self.assertEqual(stats['modes']['#'], 2)
        self.assertEqual(stats['modes']['@'], 1)
        self.assertEqual(stats['modes']['$'], 4) # 2 from DAT, 2 from MOV dest
        self.assertEqual(stats['vocabulary_size'], 3) # MOV, SPL, DAT

    def test_analyze_population(self):
        # Create another warrior
        warrior2_path = os.path.join(self.test_dir, "w2.red")
        with open(warrior2_path, "w") as f:
            f.write("ADD.AB #5, $6\n")

        pop_stats = analyze_population(self.test_dir)
        self.assertIsNotNone(pop_stats)
        self.assertEqual(pop_stats['count'], 2)
        self.assertEqual(pop_stats['total_instructions'], 5) # 4 + 1
        self.assertEqual(pop_stats['opcodes']['ADD'], 1)
        self.assertEqual(pop_stats['opcodes']['MOV'], 2)

    def test_non_existent_file(self):
        stats = analyze_warrior("non_existent.red")
        self.assertIsNone(stats)

    def test_empty_directory(self):
        empty_dir = "empty_test_dir"
        os.makedirs(empty_dir, exist_ok=True)
        stats = analyze_population(empty_dir)
        self.assertIsNone(stats)
        os.rmdir(empty_dir)

if __name__ == '__main__':
    unittest.main()
