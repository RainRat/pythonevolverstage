import sys
import os
import unittest
from unittest import mock

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestInstructionCollection(unittest.TestCase):
    @mock.patch('evolverstage._resolve_warrior_path')
    @mock.patch('os.path.isdir')
    @mock.patch('os.path.exists')
    @mock.patch('os.listdir')
    @mock.patch('builtins.open', new_callable=mock.mock_open, read_data="MOV.I #0, 1\nSPL.I #0, 0\n")
    def test_run_instruction_collection_single_file(self, mock_file, mock_listdir, mock_exists, mock_isdir, mock_resolve):
        """Test collecting instructions from a single file."""
        mock_resolve.return_value = 'warrior1.red'
        mock_isdir.return_value = False
        mock_exists.return_value = True

        # Mock coresize and sanitize lists to avoid index errors
        with mock.patch('evolverstage.CORESIZE_LIST', [80]), \
             mock.patch('evolverstage.SANITIZE_LIST', [80]), \
             mock.patch('evolverstage.LAST_ARENA', 0):

            evolverstage.run_instruction_collection(['warrior1.red'], 'library.txt', 0)

        # Verify output file was opened for writing
        mock_file.assert_any_call('library.txt', 'w')

        # Check that we wrote the expected normalized instructions
        handle = mock_file()
        handle.write.assert_any_call("MOV.I #0,$1\n")
        handle.write.assert_any_call("SPL.I #0,$0\n")

    @mock.patch('evolverstage._resolve_warrior_path')
    @mock.patch('os.path.isdir')
    @mock.patch('os.path.exists')
    @mock.patch('os.listdir')
    def test_run_instruction_collection_directory(self, mock_listdir, mock_exists, mock_isdir, mock_resolve):
        """Test collecting instructions from a directory."""
        mock_resolve.return_value = 'my_dir'
        mock_isdir.return_value = True
        mock_exists.return_value = True
        mock_listdir.return_value = ['w1.red', 'w2.red']

        # Setup mock_open to handle multiple files
        file_contents = {
            'w1.red': "MOV.I #0, 1\n",
            'w2.red': "JMP.I -1, 0\n",
            'library.txt': ""
        }

        # We need to track the writes to library.txt
        library_writes = []

        def mock_open_func(filepath, mode='r'):
            fname = os.path.basename(filepath)
            content = file_contents.get(fname, "")
            m = mock.mock_open(read_data=content).return_value
            if fname == 'library.txt' and 'w' in mode:
                m.write.side_effect = library_writes.append
            return m

        with mock.patch('builtins.open', side_effect=mock_open_func), \
             mock.patch('evolverstage.CORESIZE_LIST', [80]), \
             mock.patch('evolverstage.SANITIZE_LIST', [80]), \
             mock.patch('evolverstage.LAST_ARENA', 0):

            evolverstage.run_instruction_collection(['my_dir'], 'library.txt', 0)

        # Assertions
        self.assertIn("MOV.I #0,$1\n", library_writes)
        self.assertIn("JMP.I $-1,$0\n", library_writes)
        self.assertEqual(len(library_writes), 2)

if __name__ == '__main__':
    unittest.main()
