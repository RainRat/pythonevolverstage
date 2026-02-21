import sys
import os
import unittest
from unittest import mock
import tempfile
import shutil

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage
from evolverstage import Marble

class TestBreeding(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

        # Setup basic config for tests to ensure predictable environment
        self.old_last_arena = evolverstage.LAST_ARENA
        self.old_coresize = evolverstage.CORESIZE_LIST
        self.old_warlen = evolverstage.WARLEN_LIST
        self.old_sanitize = evolverstage.SANITIZE_LIST
        self.old_instr_set = evolverstage.INSTR_SET
        self.old_instr_modif = evolverstage.INSTR_MODIF
        self.old_instr_modes = evolverstage.INSTR_MODES
        self.old_trans_rate = evolverstage.TRANSPOSITIONRATE_LIST
        self.old_cross_rate = evolverstage.CROSSOVERRATE_LIST
        self.old_prefer = evolverstage.PREFER_WINNER_LIST
        self.old_lib_path = evolverstage.LIBRARY_PATH
        self.old_num_warriors = evolverstage.NUMWARRIORS

        evolverstage.LAST_ARENA = 0
        evolverstage.CORESIZE_LIST = [8000]
        evolverstage.WARLEN_LIST = [5]
        evolverstage.SANITIZE_LIST = [8000]
        evolverstage.INSTR_SET = ["MOV", "ADD"]
        evolverstage.INSTR_MODIF = ["I", "F"]
        evolverstage.INSTR_MODES = ["$", "#"]
        evolverstage.TRANSPOSITIONRATE_LIST = [100, 100, 100]
        evolverstage.CROSSOVERRATE_LIST = [100, 100, 100]
        evolverstage.PREFER_WINNER_LIST = [True, True, True]
        evolverstage.LIBRARY_PATH = "test_lib.txt"
        evolverstage.NUMWARRIORS = 10
        evolverstage.VERBOSE = False

    def tearDown(self):
        # Restore globals
        evolverstage.LAST_ARENA = self.old_last_arena
        evolverstage.CORESIZE_LIST = self.old_coresize
        evolverstage.WARLEN_LIST = self.old_warlen
        evolverstage.SANITIZE_LIST = self.old_sanitize
        evolverstage.INSTR_SET = self.old_instr_set
        evolverstage.INSTR_MODIF = self.old_instr_modif
        evolverstage.INSTR_MODES = self.old_instr_modes
        evolverstage.TRANSPOSITIONRATE_LIST = self.old_trans_rate
        evolverstage.CROSSOVERRATE_LIST = self.old_cross_rate
        evolverstage.PREFER_WINNER_LIST = self.old_prefer
        evolverstage.LIBRARY_PATH = self.old_lib_path
        evolverstage.NUMWARRIORS = self.old_num_warriors

        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_apply_mutation_do_nothing(self):
        instr = "MOV.I $0,$0\n"
        result = evolverstage.apply_mutation(instr, Marble.DO_NOTHING, 0, 123)
        self.assertEqual(result, instr)

    def test_apply_mutation_major(self):
        instr = "MOV.I $0,$0\n"
        with mock.patch('random.choice', side_effect=["ADD", "F", "#", "$"]):
            with mock.patch('evolverstage.weighted_random_number', side_effect=[10, 20]):
                result = evolverstage.apply_mutation(instr, Marble.MAJOR_MUTATION, 0, 123)
                self.assertEqual(result, "ADD.F #10,$20\n")

    def test_apply_mutation_nab(self):
        evolverstage.LAST_ARENA = 1
        os.makedirs("arena1", exist_ok=True)
        with open("arena1/5.red", "w") as f:
            f.write("SUB.F $5,$5\n")

        instr = "MOV.I $0,$0\n"
        # Mock random to select arena 1 and warrior 5
        with mock.patch('random.randint', side_effect=[1, 5]):
            result = evolverstage.apply_mutation(instr, Marble.NAB_INSTRUCTION, 0, 123)
            self.assertEqual(result.strip(), "SUB.F $5,$5")

    def test_apply_mutation_library(self):
        with open("test_lib.txt", "w") as f:
            f.write("JMP.B $100,$0\n")

        instr = "MOV.I $0,$0\n"
        result = evolverstage.apply_mutation(instr, Marble.INSTRUCTION_LIBRARY, 0, 123)
        self.assertEqual(result.strip(), "JMP.B $100,$0")

    def test_apply_mutation_minor_opcode(self):
        instr = "MOV.I $0,$0\n"
        # r=1 is opcode
        with mock.patch('random.randint', return_value=1):
            with mock.patch('random.choice', return_value="ADD"):
                result = evolverstage.apply_mutation(instr, Marble.MINOR_MUTATION, 0, 123)
                self.assertEqual(result, "ADD.I $0,$0\n")

    def test_apply_mutation_micro(self):
        instr = "MOV.I $10,$20\n"
        # r=1 (operand A), random.randint(1,2)=1 (increment)
        with mock.patch('random.randint', side_effect=[1, 1]):
            result = evolverstage.apply_mutation(instr, Marble.MICRO_MUTATION, 0, 123)
            self.assertEqual(result, "MOV.I $11,$20\n")

    def test_apply_mutation_magic_number(self):
        instr = "MOV.I $0,$0\n"
        # r=1 (operand A)
        with mock.patch('random.randint', return_value=1):
            result = evolverstage.apply_mutation(instr, Marble.MAGIC_NUMBER_MUTATION, 0, 42)
            self.assertEqual(result, "MOV.I $42,$0\n")

    def test_apply_mutation_with_space(self):
        """Regression test for bug where spaces after commas caused operand loss."""
        instr = "MOV.I $0, $1\n"
        # Use MINOR_MUTATION but r=1 (opcode change) so it doesn't try to parse operands as ints
        with mock.patch('random.randint', return_value=1):
            with mock.patch('random.choice', return_value="ADD"):
                result = evolverstage.apply_mutation(instr, Marble.MINOR_MUTATION, 0, 123)
                # Should be "ADD.I $0,$1\n" and definitely should contain "$1"
                self.assertIn("$1", result)
                self.assertEqual(result, "ADD.I $0,$1\n")

    def test_breed_warriors_basic(self):
        parent1 = ["MOV.I $1,$1\n"] * 5
        parent2 = ["ADD.F #2,#2\n"] * 5
        bag = [Marble.DO_NOTHING]

        with mock.patch('evolverstage.weighted_random_number', return_value=0):
            with mock.patch('random.randint', return_value=100):
                result = evolverstage.breed_warriors(parent1, parent2, 0, 0, bag)
                self.assertEqual(len(result), 5)
                # Should be all parent1 due to PREFER_WINNER=True
                self.assertEqual(result[0], "MOV.I $1,$1\n")

    def test_breed_warriors_crossover(self):
        parent1 = ["MOV.I $1,$1\n"] * 5
        parent2 = ["ADD.F #2,#2\n"] * 5
        bag = [Marble.DO_NOTHING]

        evolverstage.CROSSOVERRATE_LIST = [1, 1, 1]
        with mock.patch('evolverstage.weighted_random_number', return_value=0):
            with mock.patch('random.randint', side_effect=[100, 1, 1, 1, 1, 1]):
                result = evolverstage.breed_warriors(parent1, parent2, 0, 0, bag)
                # i=0: crossover -> pickingfrom=2 -> parent2[0]
                # i=1: crossover -> pickingfrom=1 -> parent1[1]
                self.assertEqual(result[0], "ADD.F #2,#2\n")
                self.assertEqual(result[1], "MOV.I $1,$1\n")

    def test_breed_warriors_transposition(self):
        parent1 = ["MOV.I $0,$0\n", "ADD.F $1,$1\n", "DAT.F $2,$2\n", "SUB.F $3,$3\n", "JMP.B $4,$4\n"]
        parent2 = ["DAT.F $0,$0\n"] * 5
        bag = [Marble.DO_NOTHING]

        evolverstage.TRANSPOSITIONRATE_LIST = [1, 1, 1]
        with mock.patch('evolverstage.weighted_random_number', return_value=0):
            # random.randint calls:
            # 1. transposition rate check (return 1 -> yes)
            # 2. number of swaps (randint(1, 3)) -> 2 (range(1, 2) runs once)
            # 3. fromline (randint(0, 4)) -> 0
            # 4. toline (randint(0, 4)) -> 1
            # 5. which parent (randint(1, 2)) -> 1 (winlines)
            # 6.. crossover checks (return 100 -> no)
            with mock.patch('random.randint', side_effect=[1, 2, 0, 1, 1, 100, 100, 100, 100, 100]):
                result = evolverstage.breed_warriors(parent1, parent2, 0, 0, bag)
                # Swapped parent1[0] and parent1[1]
                self.assertEqual(result[0], "ADD.F $1,$1\n")
                self.assertEqual(result[1], "MOV.I $0,$0\n")

if __name__ == '__main__':
    unittest.main()
