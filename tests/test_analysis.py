
import unittest
import os
import shutil
import json
import io
import sys
from unittest.mock import patch

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from evolverstage import analyze_warrior, analyze_population, print_analysis, strip_ansi, identify_strategy, run_meta_analysis

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
        if os.path.exists("arena0"):
            shutil.rmtree("arena0")

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

    def test_identify_strategy_all_branches(self):
        # 1. Paper: spl > 20, mov > 30
        self.assertEqual(identify_strategy({'instructions': 100, 'opcodes': {'SPL': 21, 'MOV': 31}}), "Paper (Replicator)")

        # 2. Stone: djn > 10, mov > 30
        self.assertEqual(identify_strategy({'instructions': 100, 'opcodes': {'DJN': 11, 'MOV': 31}}), "Stone (Bomb-thrower)")

        # 3. Imp: add > 20, mov > 40
        self.assertEqual(identify_strategy({'instructions': 100, 'opcodes': {'ADD': 21, 'MOV': 41}}), "Imp (Pulse)")

        # 4. Vampire: jmp > 15 AND (mov > 20 OR add > 20)
        self.assertEqual(identify_strategy({'instructions': 100, 'opcodes': {'JMP': 16, 'MOV': 21}}), "Vampire / Pittrap")
        self.assertEqual(identify_strategy({'instructions': 100, 'opcodes': {'JMP': 16, 'ADD': 21}}), "Vampire / Pittrap")

        # 5. Mover: mov > 70
        self.assertEqual(identify_strategy({'instructions': 100, 'opcodes': {'MOV': 71}}), "Mover / Runner")

        # 6. Wait: dat > 50
        self.assertEqual(identify_strategy({'instructions': 100, 'opcodes': {'DAT': 51}}), "Wait / Shield")

        # 7. Experimental: none of the above
        self.assertEqual(identify_strategy({'instructions': 100, 'opcodes': {'MOV': 10}}), "Experimental")

        # 8. Unknown: no instructions
        self.assertEqual(identify_strategy({'instructions': 0, 'opcodes': {}}), "Unknown")
        self.assertEqual(identify_strategy(None), "Unknown")

    def test_run_meta_analysis_folder(self):
        pop_dir = os.path.join(self.test_dir, "meta_test")
        os.makedirs(pop_dir, exist_ok=True)
        # 100% MOV -> Mover / Runner
        with open(os.path.join(pop_dir, "mover.red"), "w") as f:
            f.write("MOV.I $0, $1\n")

        captured_output = io.StringIO()
        sys.stdout = captured_output
        try:
            run_meta_analysis(pop_dir, 0, json_output=True)
        finally:
            sys.stdout = sys.__stdout__

        res = json.loads(captured_output.getvalue())
        self.assertEqual(res['target']['Mover / Runner'], 1)

    @patch('evolverstage.get_leaderboard')
    def test_run_meta_analysis_arena(self, mock_leaderboard):
        # Setup arena population (1.red is a Stone)
        os.makedirs("arena0", exist_ok=True)
        with open("arena0/1.red", "w") as f:
            f.write("MOV.I $0, $1\nDJN.B $0, $1\n") # DJN 50% -> Stone

        # Mock leaderboard: warrior 1 is the meta
        mock_leaderboard.return_value = {0: [('1', 10)]}

        captured_output = io.StringIO()
        sys.stdout = captured_output
        try:
            run_meta_analysis("arena0", 0, json_output=True)
        finally:
            sys.stdout = sys.__stdout__

        res = json.loads(captured_output.getvalue())
        self.assertEqual(res['target']['Stone (Bomb-thrower)'], 1)
        self.assertEqual(res['meta']['Stone (Bomb-thrower)'], 1)

if __name__ == '__main__':
    unittest.main()
