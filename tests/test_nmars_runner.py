import sys
import os
import unittest
import subprocess
from unittest import mock

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestRunNmarsCommand(unittest.TestCase):
    def setUp(self):
        # Common test data
        self.arena = 0
        self.cont1 = 1
        self.cont2 = 2
        self.coresize = 8000
        self.cycles = 80000
        self.processes = 8000
        self.warlen = 100
        self.wardistance = 100
        self.battlerounds = 1

    @mock.patch('evolverstage.subprocess.run')
    @mock.patch('evolverstage.os.name', 'posix') # Default to linux/mac
    def test_run_command_success_posix(self, mock_run):
        """Test successful execution on POSIX systems."""
        mock_run.return_value.stdout = "Battle Output"

        output = evolverstage.run_nmars_command(
            self.arena, self.cont1, self.cont2, self.coresize,
            self.cycles, self.processes, self.warlen,
            self.wardistance, self.battlerounds
        )

        self.assertEqual(output, "Battle Output")

        expected_cmd = [
            "nmars",
            os.path.join(f"arena{self.arena}", f"{self.cont1}.red"),
            os.path.join(f"arena{self.arena}", f"{self.cont2}.red"),
            "-s", str(self.coresize),
            "-c", str(self.cycles),
            "-p", str(self.processes),
            "-l", str(self.warlen),
            "-d", str(self.wardistance),
            "-r", str(self.battlerounds)
        ]

        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        self.assertEqual(args[0], expected_cmd)
        self.assertEqual(kwargs['capture_output'], True)
        self.assertEqual(kwargs['text'], True)

    @mock.patch('evolverstage.subprocess.run')
    @mock.patch('evolverstage.os.name', 'nt') # Windows
    def test_run_command_success_windows(self, mock_run):
        """Test successful execution on Windows systems."""
        mock_run.return_value.stdout = "Win Output"

        output = evolverstage.run_nmars_command(
            self.arena, self.cont1, self.cont2, self.coresize,
            self.cycles, self.processes, self.warlen,
            self.wardistance, self.battlerounds
        )

        self.assertEqual(output, "Win Output")
        expected_cmd_start = "nmars.exe"
        self.assertEqual(mock_run.call_args[0][0][0], expected_cmd_start)

    @mock.patch('evolverstage.subprocess.run')
    def test_file_not_found_error(self, mock_run):
        """Test handling of FileNotFoundError (nmars missing)."""
        mock_run.side_effect = FileNotFoundError("nmars not found")

        output = evolverstage.run_nmars_command(
            self.arena, self.cont1, self.cont2, self.coresize,
            self.cycles, self.processes, self.warlen,
            self.wardistance, self.battlerounds
        )

        self.assertIsNone(output)

    @mock.patch('evolverstage.subprocess.run')
    def test_subprocess_error(self, mock_run):
        """Test handling of general SubprocessError."""
        mock_run.side_effect = subprocess.SubprocessError("Crash")

        output = evolverstage.run_nmars_command(
            self.arena, self.cont1, self.cont2, self.coresize,
            self.cycles, self.processes, self.warlen,
            self.wardistance, self.battlerounds
        )

        self.assertIsNone(output)
