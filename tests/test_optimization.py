import sys
import os
import unittest
import shutil
import tempfile
from unittest import mock

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestOptimization(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

        # Mocking globals
        self.old_last_arena = evolverstage.LAST_ARENA
        self.old_coresize = evolverstage.CORESIZE_LIST
        self.old_warlen = evolverstage.WARLEN_LIST
        self.old_sanitize = evolverstage.SANITIZE_LIST
        self.old_battlerounds = evolverstage.BATTLEROUNDS_LIST
        self.old_nothing = evolverstage.NOTHING_LIST
        self.old_random = evolverstage.RANDOM_LIST
        self.old_nab = evolverstage.NAB_LIST
        self.old_mini = evolverstage.MINI_MUT_LIST
        self.old_micro = evolverstage.MICRO_MUT_LIST
        self.old_lib = evolverstage.LIBRARY_LIST
        self.old_magic = evolverstage.MAGIC_NUMBER_LIST
        self.old_trans = evolverstage.TRANSPOSITIONRATE_LIST
        self.old_cross = evolverstage.CROSSOVERRATE_LIST
        self.old_instr = evolverstage.INSTR_SET
        self.old_modif = evolverstage.INSTR_MODIF
        self.old_modes = evolverstage.INSTR_MODES

        evolverstage.LAST_ARENA = 0
        evolverstage.CORESIZE_LIST = [80]
        evolverstage.WARLEN_LIST = [1]
        evolverstage.SANITIZE_LIST = [80]
        evolverstage.BATTLEROUNDS_LIST = [1, 1, 1]
        evolverstage.NOTHING_LIST = [0, 0, 0]
        evolverstage.RANDOM_LIST = [0, 0, 1]
        evolverstage.NAB_LIST = [0, 0, 0]
        evolverstage.MINI_MUT_LIST = [0, 0, 0]
        evolverstage.MICRO_MUT_LIST = [0, 0, 0]
        evolverstage.LIBRARY_LIST = [0, 0, 0]
        evolverstage.MAGIC_NUMBER_LIST = [0, 0, 0]
        evolverstage.TRANSPOSITIONRATE_LIST = [1000, 1000, 1000]
        evolverstage.CROSSOVERRATE_LIST = [1000, 1000, 1000]
        evolverstage.INSTR_SET = ["MOV"]
        evolverstage.INSTR_MODIF = ["I"]
        evolverstage.INSTR_MODES = ["$"]

        self.test_warrior = "test_opt.red"
        with open(self.test_warrior, "w") as f:
            f.write("MOV.I $0,$1\n")

    def tearDown(self):
        # Restore globals
        evolverstage.LAST_ARENA = self.old_last_arena
        evolverstage.CORESIZE_LIST = self.old_coresize
        evolverstage.WARLEN_LIST = self.old_warlen
        evolverstage.SANITIZE_LIST = self.old_sanitize
        evolverstage.BATTLEROUNDS_LIST = self.old_battlerounds
        evolverstage.NOTHING_LIST = self.old_nothing
        evolverstage.RANDOM_LIST = self.old_random
        evolverstage.NAB_LIST = self.old_nab
        evolverstage.MINI_MUT_LIST = self.old_mini
        evolverstage.MICRO_MUT_LIST = self.old_micro
        evolverstage.LIBRARY_LIST = self.old_lib
        evolverstage.MAGIC_NUMBER_LIST = self.old_magic
        evolverstage.TRANSPOSITIONRATE_LIST = self.old_trans
        evolverstage.CROSSOVERRATE_LIST = self.old_cross
        evolverstage.INSTR_SET = self.old_instr
        evolverstage.INSTR_MODIF = self.old_modif
        evolverstage.INSTR_MODES = self.old_modes

        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    @mock.patch('evolverstage.run_nmars_subprocess')
    @mock.patch('evolverstage._resolve_warrior_path')
    @mock.patch('evolverstage.print_status_line')
    def test_run_optimization_success(self, mock_status, mock_resolve, mock_run):
        mock_resolve.return_value = self.test_warrior

        # Simulate tournament: mutation 1 wins everything
        def side_effect(cmd):
            p1 = cmd[1]
            p2 = cmd[2]
            if "mut_1.red" in p1: return "1 scores 100\n2 scores 0"
            if "mut_1.red" in p2: return "1 scores 0\n2 scores 100"
            return "1 scores 50\n2 scores 50"

        mock_run.side_effect = side_effect

        evolverstage.run_optimization("test_opt.red", 0)

        # Verify optimized file created
        self.assertTrue(os.path.exists("opt_test_opt.red"))
        with open("opt_test_opt.red", "r") as f:
            content = f.read()
            self.assertIn("MOV", content)

    @mock.patch('evolverstage.run_nmars_subprocess')
    @mock.patch('evolverstage._resolve_warrior_path')
    @mock.patch('evolverstage.print_status_line')
    def test_run_optimization_no_improvement(self, mock_status, mock_resolve, mock_run):
        mock_resolve.return_value = self.test_warrior

        # Original wins everything
        def side_effect(cmd):
            p1 = cmd[1]
            p2 = cmd[2]
            if "original.red" in p1: return "1 scores 100\n2 scores 0"
            if "original.red" in p2: return "1 scores 0\n2 scores 100"
            return "1 scores 50\n2 scores 50"

        mock_run.side_effect = side_effect

        evolverstage.run_optimization("test_opt.red", 0)

        # Verify optimized file NOT created
        self.assertFalse(os.path.exists("opt_test_opt.red"))

if __name__ == '__main__':
    unittest.main()
