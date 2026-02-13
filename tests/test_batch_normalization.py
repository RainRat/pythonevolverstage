import sys
import os
import unittest
from unittest import mock
from io import StringIO

# Add root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestBatchNormalization(unittest.TestCase):
    def setUp(self):
        # Mock global config lists used in run_normalization
        self.patcher1 = mock.patch('evolverstage.CORESIZE_LIST', [8000])
        self.patcher2 = mock.patch('evolverstage.SANITIZE_LIST', [8000])
        self.patcher3 = mock.patch('evolverstage.LAST_ARENA', 0)
        self.patcher1.start()
        self.patcher2.start()
        self.patcher3.start()

    def tearDown(self):
        self.patcher1.stop()
        self.patcher2.stop()
        self.patcher3.stop()

    @mock.patch('builtins.open')
    @mock.patch('os.path.exists')
    @mock.patch('os.path.isdir')
    @mock.patch('sys.stdout', new_callable=StringIO)
    def test_single_file_stdout(self, mock_stdout, mock_isdir, mock_exists, mock_open):
        """Test normalizing a single file to stdout (default behavior)."""
        mock_exists.return_value = True
        mock_isdir.return_value = False

        # Mock file content
        mock_file = mock.Mock()
        mock_file.readlines.return_value = ["MOV.I $0, $0\n"]
        # Make the file object a context manager
        mock_file.__enter__ = mock.Mock(return_value=mock_file)
        mock_file.__exit__ = mock.Mock(return_value=None)

        mock_open.return_value = mock_file

        evolverstage.run_normalization("warrior.red", 0)

        # Verify output
        self.assertIn("MOV.I $0,$0", mock_stdout.getvalue())
        # Verify open called for read
        mock_open.assert_called_with("warrior.red", 'r')

    @mock.patch('builtins.open')
    @mock.patch('os.path.exists')
    @mock.patch('os.path.isdir')
    def test_single_file_to_file(self, mock_isdir, mock_exists, mock_open):
        """Test normalizing a single file to an output file."""
        mock_exists.return_value = True
        mock_isdir.return_value = False

        # Setup mocks for read and write
        mock_read_handle = mock.Mock()
        mock_read_handle.readlines.return_value = ["MOV.I $0, $0\n"]
        mock_read_handle.__enter__ = mock.Mock(return_value=mock_read_handle)
        mock_read_handle.__exit__ = mock.Mock(return_value=None)

        mock_write_handle = mock.Mock()
        mock_write_handle.__enter__ = mock.Mock(return_value=mock_write_handle)
        mock_write_handle.__exit__ = mock.Mock(return_value=None)

        def open_side_effect(file, mode='r'):
            if mode == 'r':
                return mock_read_handle
            elif mode == 'w':
                return mock_write_handle
            return mock.Mock()

        mock_open.side_effect = open_side_effect

        evolverstage.run_normalization("warrior.red", 0, output_path="clean.red")

        # Verify write happened
        mock_write_handle.write.assert_called_with("MOV.I $0,$0\n")

    @mock.patch('os.makedirs')
    @mock.patch('os.path.isdir')
    @mock.patch('os.listdir')
    @mock.patch('os.path.exists')
    @mock.patch('builtins.open')
    def test_directory_processing(self, mock_open, mock_exists, mock_listdir, mock_isdir, mock_makedirs):
        """Test that directory input triggers processing of all .red files."""
        # Setup: input path IS a directory
        def isdir_side_effect(path):
            if path == "in_dir": return True
            return False
        mock_isdir.side_effect = isdir_side_effect

        # Fix: ensure os.path.exists returns True for input and output paths
        mock_exists.return_value = True

        mock_listdir.return_value = ["w1.red", "readme.txt"]

        # Setup mock file reading/writing
        mock_read_handle = mock.Mock()
        mock_read_handle.readlines.return_value = ["MOV.I $0, $0\n"]
        mock_read_handle.__enter__ = mock.Mock(return_value=mock_read_handle)
        mock_read_handle.__exit__ = mock.Mock(return_value=None)

        mock_write_handle = mock.Mock()
        mock_write_handle.__enter__ = mock.Mock(return_value=mock_write_handle)
        mock_write_handle.__exit__ = mock.Mock(return_value=None)

        def open_side_effect(file, mode='r'):
            # Allow reading w1.red
            if 'w1.red' in file and mode == 'r':
                return mock_read_handle
            # Allow writing w1.red
            if 'w1.red' in file and mode == 'w':
                return mock_write_handle
            return mock.Mock()

        mock_open.side_effect = open_side_effect

        evolverstage.run_normalization("in_dir", 0, output_path="out_dir")

        # Verify makedirs called
        mock_makedirs.assert_called_with("out_dir", exist_ok=True)

        # Verify calls
        in_file = os.path.join("in_dir", "w1.red")
        out_file = os.path.join("out_dir", "w1.red")

        mock_open.assert_any_call(in_file, 'r')
        mock_open.assert_any_call(out_file, 'w')

        # Ensure readme.txt was skipped
        readme_in = os.path.join("in_dir", "readme.txt")
        try:
            mock_open.assert_any_call(readme_in, 'r')
            raise AssertionError("Should not have opened readme.txt")
        except AssertionError as e:
            if "Should not have" in str(e): raise e
            pass # Expected behavior

    @mock.patch('os.path.isdir')
    @mock.patch('os.path.exists')
    def test_directory_without_output_error(self, mock_exists, mock_isdir):
        """Test that directory input without output path raises error."""
        # Fix: os.path.exists must return True for the input dir for the check in run_normalization to pass
        mock_exists.return_value = True
        mock_isdir.return_value = True

        with mock.patch('sys.stdout', new=StringIO()) as fake_out:
             evolverstage.run_normalization("in_dir", 0, output_path=None)
             self.assertIn("Error: You must specify an output folder", fake_out.getvalue())
