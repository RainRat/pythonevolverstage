import sys
import os
import unittest
from unittest import mock
import io
import re

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestRunNormalization(unittest.TestCase):
    def setUp(self):
        self.filepath = "warrior.red"
        self.arena_idx = 0

        # Setup common mock configuration
        self.mock_config = {
            'LAST_ARENA': 1,
            'CORESIZE_LIST': [8000, 8000],
            'SANITIZE_LIST': [8000, 8000],
        }

    @mock.patch('builtins.print')
    def test_run_normalization_invalid_arena(self, mock_print):
        """Test normalization with invalid arena index."""
        with mock.patch.multiple(evolverstage, **self.mock_config):
             evolverstage.run_normalization(self.filepath, 2)

        mock_print.assert_any_call(f"Error: Arena 2 does not exist (LAST_ARENA=1)")

    @mock.patch('os.path.exists')
    @mock.patch('builtins.print')
    def test_run_normalization_file_not_found(self, mock_print, mock_exists):
        """Test normalization with missing file."""
        mock_exists.return_value = False

        with mock.patch.multiple(evolverstage, **self.mock_config):
             evolverstage.run_normalization(self.filepath, self.arena_idx)

        mock_print.assert_any_call(f"Error: Path '{self.filepath}' not found.")

    @mock.patch('builtins.open', new_callable=mock.mock_open, read_data="MOV 0, 1\n")
    @mock.patch('os.path.exists')
    @mock.patch('sys.stdout', new_callable=io.StringIO)
    @mock.patch('evolverstage.normalize_instruction')
    def test_run_normalization_success(self, mock_normalize, mock_stdout, mock_exists, mock_file):
        """Test successful normalization of a file."""
        mock_exists.return_value = True
        mock_normalize.return_value = "MOV.I $0,$1\n"

        with mock.patch.multiple(evolverstage, **self.mock_config):
             evolverstage.run_normalization(self.filepath, self.arena_idx)

        # Verify normalize called (note: ", " replaced by ",")
        mock_normalize.assert_called_with("MOV 0,1", 8000, 8000)
        # Verify output written to stdout
        self.assertEqual(mock_stdout.getvalue(), "MOV.I $0,$1\n")

    @mock.patch('builtins.open', new_callable=mock.mock_open, read_data="bad_instruction\n")
    @mock.patch('os.path.exists')
    @mock.patch('sys.stderr', new_callable=io.StringIO)
    @mock.patch('evolverstage.normalize_instruction')
    def test_run_normalization_warning(self, mock_normalize, mock_stderr, mock_exists, mock_file):
        """Test normalization warning when instruction is invalid."""
        mock_exists.return_value = True
        # Simulate ValueError from normalize_instruction
        mock_normalize.side_effect = ValueError("Invalid instruction")

        with mock.patch.multiple(evolverstage, **self.mock_config):
             evolverstage.run_normalization(self.filepath, self.arena_idx)

        # Verify stderr output
        self.assertIn("Warning: Could not normalize line: bad_instruction", mock_stderr.getvalue())

    @mock.patch('builtins.open', new_callable=mock.mock_open, read_data="; comment\n\nMOV 0, 1")
    @mock.patch('os.path.exists')
    @mock.patch('builtins.print')
    @mock.patch('evolverstage.normalize_instruction')
    def test_run_normalization_skips_comments_and_empty(self, mock_normalize, mock_print, mock_exists, mock_file):
        """Test that comments and empty lines are skipped."""
        mock_exists.return_value = True

        with mock.patch.multiple(evolverstage, **self.mock_config):
             evolverstage.run_normalization(self.filepath, self.arena_idx)

        # normalize_instruction should only be called once for "MOV 0, 1" -> "MOV 0,1"
        self.assertEqual(mock_normalize.call_count, 1)
        mock_normalize.assert_called_with("MOV 0,1", 8000, 8000)

    @mock.patch('builtins.open', new_callable=mock.mock_open, read_data="START MOV  0,  1")
    @mock.patch('os.path.exists')
    @mock.patch('builtins.print')
    @mock.patch('evolverstage.normalize_instruction')
    def test_run_normalization_cleanup(self, mock_normalize, mock_print, mock_exists, mock_file):
        """Test that input lines are cleaned up (START removed, spaces fixed)."""
        mock_exists.return_value = True

        with mock.patch.multiple(evolverstage, **self.mock_config):
             evolverstage.run_normalization(self.filepath, self.arena_idx)

        mock_normalize.assert_called_with("MOV 0,1", 8000, 8000)

    @mock.patch('builtins.open')
    @mock.patch('os.path.exists')
    @mock.patch('builtins.print')
    def test_run_normalization_file_error(self, mock_print, mock_exists, mock_open):
        """Test handling of file read exception."""
        mock_exists.return_value = True
        mock_open.side_effect = IOError("Read failed")

        with mock.patch.multiple(evolverstage, **self.mock_config):
             evolverstage.run_normalization(self.filepath, self.arena_idx)

        mock_print.assert_any_call("Error processing file: Read failed")
