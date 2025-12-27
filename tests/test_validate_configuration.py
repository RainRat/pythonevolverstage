import sys
import os
import unittest
from unittest import mock
import shutil
import io

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestValidateConfiguration(unittest.TestCase):
    def setUp(self):
        # Default valid configuration
        self.default_config = {
            'LAST_ARENA': 0,
            'CORESIZE_LIST': [8000],
            'SANITIZE_LIST': [8000],
            'CYCLES_LIST': [80000],
            'PROCESSES_LIST': [8000],
            'WARLEN_LIST': [100],
            'WARDISTANCE_LIST': [100],
            'NOTHING_LIST': [1, 1, 1],
            'RANDOM_LIST': [1, 1, 1],
            'NAB_LIST': [1, 1, 1],
            'MINI_MUT_LIST': [1, 1, 1],
            'MICRO_MUT_LIST': [1, 1, 1],
            'LIBRARY_LIST': [0, 0, 0],
            'MAGIC_NUMBER_LIST': [1, 1, 1],
            'ARCHIVE_LIST': [1, 1, 1],
            'UNARCHIVE_LIST': [1, 1, 1],
            'CROSSOVERRATE_LIST': [1, 1, 1],
            'TRANSPOSITIONRATE_LIST': [1, 1, 1],
            'BATTLEROUNDS_LIST': [1, 1, 1],
            'PREFER_WINNER_LIST': [True, True, True],
            'LIBRARY_PATH': None,
            'ALREADYSEEDED': True
        }
        # Start a patcher for all these
        self.patcher = mock.patch.multiple(evolverstage, **self.default_config)
        self.patcher.start()

        # Mock sys.stdout to capture print output
        self.mock_stdout = mock.patch('sys.stdout', new_callable=io.StringIO)
        self.stdout = self.mock_stdout.start()

    def tearDown(self):
        self.patcher.stop()
        self.mock_stdout.stop()

    @mock.patch('shutil.which')
    @mock.patch('os.path.exists')
    def test_valid_configuration(self, mock_exists, mock_which):
        # Setup executable check to pass
        # nmars check: shutil.which(nmars) OR os.path.exists(nmars)
        mock_which.return_value = '/path/to/nmars'
        mock_exists.return_value = False # For other checks

        result = evolverstage.validate_configuration()
        self.assertTrue(result)
        self.assertIn("Configuration and environment are valid.", self.stdout.getvalue())

    @mock.patch('shutil.which')
    @mock.patch('os.path.exists')
    def test_missing_executable(self, mock_exists, mock_which):
        # Executable missing
        mock_which.return_value = None
        mock_exists.return_value = False

        result = evolverstage.validate_configuration()
        self.assertFalse(result)
        self.assertIn("Executable", self.stdout.getvalue())
        self.assertIn("not found in PATH or current directory", self.stdout.getvalue())

    @mock.patch('shutil.which')
    @mock.patch('os.path.exists')
    def test_invalid_arena_list_length(self, mock_exists, mock_which):
        # Setup executable valid
        mock_which.return_value = True

        # Override one list to be too short
        # LAST_ARENA is 0 (set in setUp), so need length 1.
        with mock.patch.object(evolverstage, 'CORESIZE_LIST', []):
            result = evolverstage.validate_configuration()
            self.assertFalse(result)
            self.assertIn("CORESIZE_LIST has 0 elements, expected at least 1", self.stdout.getvalue())

    @mock.patch('shutil.which')
    @mock.patch('os.path.exists')
    def test_invalid_era_list_length(self, mock_exists, mock_which):
        mock_which.return_value = True

        # Era lists need length 3
        with mock.patch.object(evolverstage, 'NOTHING_LIST', [1, 1]):
            result = evolverstage.validate_configuration()
            self.assertFalse(result)
            self.assertIn("NOTHING_LIST has 2 elements, expected at least 3", self.stdout.getvalue())

    @mock.patch('shutil.which')
    @mock.patch('os.path.exists')
    def test_library_warning(self, mock_exists, mock_which):
        mock_which.return_value = True

        # LIBRARY_PATH is set, but does not exist
        # And LIBRARY_LIST has > 0
        with mock.patch.object(evolverstage, 'LIBRARY_PATH', '/bad/path'), \
             mock.patch.object(evolverstage, 'LIBRARY_LIST', [1, 0, 0]):

            # mock_exists returns False by default for the path check
            mock_exists.return_value = False
            # Note: mock_exists is also called for nmars check if which fails,
            # but we set which to True, so nmars check passes.
            # It is called for library path.

            result = evolverstage.validate_configuration()

            # Should be valid (warnings don't fail validation)
            self.assertTrue(result)
            self.assertIn("Warnings:", self.stdout.getvalue())
            self.assertIn("LIBRARY_PATH '/bad/path' does not exist", self.stdout.getvalue())

    @mock.patch('shutil.which')
    @mock.patch('os.path.exists')
    def test_seeding_warning(self, mock_exists, mock_which):
        mock_which.return_value = True

        # ALREADYSEEDED is False
        # And arena directory exists
        with mock.patch.object(evolverstage, 'ALREADYSEEDED', False):

            # mock_exists needs to return True for "arena0"
            def side_effect(path):
                if path == "arena0":
                    return True
                return False
            mock_exists.side_effect = side_effect

            result = evolverstage.validate_configuration()

            self.assertTrue(result)
            self.assertIn("ALREADYSEEDED is False, but arena directories exist", self.stdout.getvalue())
