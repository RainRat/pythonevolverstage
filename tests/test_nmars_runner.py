import sys
import os
import unittest
import subprocess
from unittest import mock

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestNmarsRunner(unittest.TestCase):
    def setUp(self):
        # Common test data
        self.arena = 0
        self.cont1 = 1
        self.cont2 = 2
        self.file1 = os.path.join(f"arena{self.arena}", f"{self.cont1}.red")
        self.file2 = os.path.join(f"arena{self.arena}", f"{self.cont2}.red")
        self.coresize = 8000
        self.cycles = 80000
        self.processes = 8000
        self.warlen = 100
        self.wardistance = 100
        self.battlerounds = 1

    @mock.patch('evolverstage.os.name', 'posix')
    def test_construct_battle_command_posix(self):
        """Test that construct_battle_command builds the correct list on POSIX."""
        cmd = evolverstage.construct_battle_command(
            self.file1, self.file2, self.arena,
            coresize=self.coresize, cycles=self.cycles,
            processes=self.processes, warlen=self.warlen,
            wardistance=self.wardistance, rounds=self.battlerounds
        )

        expected_cmd = [
            "nmars",
            self.file1,
            self.file2,
            "-s", str(self.coresize),
            "-c", str(self.cycles),
            "-p", str(self.processes),
            "-l", str(self.warlen),
            "-d", str(self.wardistance),
            "-r", str(self.battlerounds)
        ]
        self.assertEqual(cmd, expected_cmd)

    @mock.patch('evolverstage.os.name', 'nt')
    def test_construct_battle_command_windows(self):
        """Test that construct_battle_command uses nmars.exe on Windows."""
        cmd = evolverstage.construct_battle_command(self.file1, self.file2, self.arena)
        self.assertEqual(cmd[0], "nmars.exe")

    @mock.patch('evolverstage.subprocess.run')
    def test_run_nmars_subprocess_success(self, mock_run):
        """Test successful execution of run_nmars_subprocess."""
        mock_run.return_value.stdout = "Battle Output"
        cmd = ["nmars", "f1.red", "f2.red"]

        output = evolverstage.run_nmars_subprocess(cmd)

        self.assertEqual(output, "Battle Output")
        mock_run.assert_called_once()
        self.assertEqual(mock_run.call_args[0][0], cmd)
        self.assertEqual(mock_run.call_args[1]['capture_output'], True)
        self.assertEqual(mock_run.call_args[1]['text'], True)

    @mock.patch('evolverstage.subprocess.run')
    def test_run_nmars_subprocess_file_not_found(self, mock_run):
        """Test handling of FileNotFoundError in run_nmars_subprocess."""
        mock_run.side_effect = FileNotFoundError("nmars not found")
        cmd = ["nmars", "f1.red", "f2.red"]

        output = evolverstage.run_nmars_subprocess(cmd)
        self.assertIsNone(output)

    @mock.patch('evolverstage.subprocess.run')
    def test_run_nmars_subprocess_error(self, mock_run):
        """Test handling of general SubprocessError in run_nmars_subprocess."""
        mock_run.side_effect = subprocess.SubprocessError("Crash")
        cmd = ["nmars", "f1.red", "f2.red"]

        output = evolverstage.run_nmars_subprocess(cmd)
        self.assertIsNone(output)

if __name__ == '__main__':
    unittest.main()
