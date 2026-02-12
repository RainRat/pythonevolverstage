
import unittest
import os
import shutil
import json
import io
import sys
from unittest.mock import patch

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from evolverstage import analyze_warrior, analyze_population, print_analysis, strip_ansi

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
            f.write("MOV 10, 20\n") # Non-standard modes (defaults to $)
            f.write("; a comment\n")
            f.write("\n")
            f.write("MOV.I #1, $2\n") # Duplicate for vocabulary test

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_analyze_warrior(self):
        stats = analyze_warrior(self.warrior1_path)
        self.assertIsNotNone(stats)
        self.assertEqual(stats['instructions'], 5)
        self.assertEqual(stats['opcodes']['MOV'], 3)
        self.assertEqual(stats['opcodes']['SPL'], 1)
        self.assertEqual(stats['opcodes']['DAT'], 1)
        self.assertEqual(stats['modifiers']['I'], 2)
        self.assertEqual(stats['modifiers']['A'], 1)
        self.assertEqual(stats['modes']['#'], 2)
        self.assertEqual(stats['modes']['@'], 1)
        self.assertEqual(stats['modes']['$'], 6) # 2 from DAT, 2 from MOV dest, 2 from MOV 10, 20
        self.assertEqual(stats['vocabulary_size'], 4) # MOV, SPL, DAT, MOV (Wait, MOV.I vs MOV)

    def test_analyze_population(self):
        # Use a dedicated subdirectory for population test to avoid interference
        pop_dir = os.path.join(self.test_dir, "pop_test")
        os.makedirs(pop_dir, exist_ok=True)

        # Create warriors in pop_dir
        with open(os.path.join(pop_dir, "p1.red"), "w") as f:
            f.write("MOV.I #1, $2\n")
        with open(os.path.join(pop_dir, "p2.red"), "w") as f:
            f.write("ADD.AB #5, $6\n")

        pop_stats = analyze_population(pop_dir)
        self.assertIsNotNone(pop_stats)
        self.assertEqual(pop_stats['count'], 2)
        self.assertEqual(pop_stats['opcodes']['ADD'], 1)
        self.assertEqual(pop_stats['opcodes']['MOV'], 1)

    def test_non_existent_file(self):
        stats = analyze_warrior("non_existent.red")
        self.assertIsNone(stats)

    def test_empty_directory(self):
        empty_dir = "empty_test_dir"
        os.makedirs(empty_dir, exist_ok=True)
        stats = analyze_population(empty_dir)
        self.assertIsNone(stats)
        os.rmdir(empty_dir)

    def test_analyze_warrior_no_operands(self):
        path = os.path.join(self.test_dir, "no_ops.red")
        with open(path, "w") as f:
            f.write("DAT.I\n")
            f.write("END\n")

        stats = analyze_warrior(path)
        self.assertIsNotNone(stats)
        self.assertEqual(stats['instructions'], 2)
        self.assertEqual(stats['opcodes']['DAT'], 1)
        self.assertEqual(stats['opcodes']['END'], 1)
        self.assertEqual(stats['modifiers']['I'], 1)

    def test_analyze_warrior_fallback(self):
        path = os.path.join(self.test_dir, "fallback.red")
        with open(path, "w") as f:
            f.write("123 MOV\n") # Does not start with [A-Z], hits fallback

        stats = analyze_warrior(path)
        self.assertIsNotNone(stats)
        self.assertEqual(stats['opcodes']['123'], 1)

    def test_analyze_warrior_error_handling(self):
        # Trying to analyze a directory instead of a file
        stats = analyze_warrior(self.test_dir)
        self.assertIsNone(stats)

    def test_print_analysis_single(self):
        stats = analyze_warrior(self.warrior1_path)

        captured_output = io.StringIO()
        sys.stdout = captured_output
        try:
            print_analysis(stats)
        finally:
            sys.stdout = sys.__stdout__

        output = strip_ansi(captured_output.getvalue())
        self.assertIn("Analysis Report: " + self.warrior1_path, output)
        self.assertIn("Instructions:      5", output)
        self.assertIn("Opcode Distribution:", output)
        self.assertIn("MOV :    3", output)
        self.assertIn("Modifier Distribution:", output)
        self.assertIn(".I :    2", output)

    def test_print_analysis_population(self):
        pop_dir = os.path.join(self.test_dir, "pop_print_test")
        os.makedirs(pop_dir, exist_ok=True)
        with open(os.path.join(pop_dir, "p1.red"), "w") as f:
            f.write("MOV.I #1, $2\n")

        pop_stats = analyze_population(pop_dir)

        captured_output = io.StringIO()
        sys.stdout = captured_output
        try:
            print_analysis(pop_stats)
        finally:
            sys.stdout = sys.__stdout__

        output = strip_ansi(captured_output.getvalue())
        self.assertIn("Analysis Report: " + pop_dir, output)
        self.assertEqual(pop_stats['count'], 1)
        self.assertIn("Warriors Analyzed: 1", output)

    def test_print_analysis_none(self):
        captured_output = io.StringIO()
        sys.stdout = captured_output
        try:
            print_analysis(None)
        finally:
            sys.stdout = sys.__stdout__

        output = strip_ansi(captured_output.getvalue())
        self.assertIn("No data to analyze.", output)

if __name__ == '__main__':
    unittest.main()
