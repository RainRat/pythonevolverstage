import sys
import os
import unittest
from unittest import mock

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestReadConfig(unittest.TestCase):
    def setUp(self):
        # Save the original config to restore later
        self.original_config = evolverstage.config
        # Create a mock config object
        self.mock_config = mock.MagicMock()
        # Apply the mock
        evolverstage.config = self.mock_config

    def tearDown(self):
        # Restore the original config
        evolverstage.config = self.original_config

    def set_config_value(self, key, value):
        """Helper to set the return value for config['DEFAULT'].get(key)"""
        # We need to handle the nested dictionary access config['DEFAULT']
        defaults = self.mock_config.__getitem__.return_value

        # Determine behavior based on whether key matches
        def get_side_effect(k, fallback=None):
            if k == key:
                return value
            return fallback

        def getboolean_side_effect(k, default=None):
             if k == key:
                 # In a real ConfigParser, getboolean parses strings like 'yes', 'true', '1', etc.
                 # Here we assume the value is already a boolean or we simulate what we need.
                 if isinstance(value, bool):
                     return value
                 if str(value).lower() in ('true', 'yes', 'on', '1'):
                     return True
                 if str(value).lower() in ('false', 'no', 'off', '0'):
                     return False
                 return default
             return default

        defaults.get.side_effect = get_side_effect
        defaults.getboolean.side_effect = getboolean_side_effect

    def test_read_int(self):
        self.set_config_value('TEST_INT', '42')
        result = evolverstage.read_config('TEST_INT', 'int')
        self.assertEqual(result, 42)

    def test_read_int_invalid(self):
        self.set_config_value('TEST_INT', 'invalid')
        with self.assertRaises(ValueError):
            evolverstage.read_config('TEST_INT', 'int')

    def test_read_float(self):
        self.set_config_value('TEST_FLOAT', '3.14')
        result = evolverstage.read_config('TEST_FLOAT', 'float')
        self.assertAlmostEqual(result, 3.14)

    def test_read_bool(self):
        # Test 'true' string handled by our mock simulation or real logic if we mocked deeper
        # read_config uses: config['DEFAULT'].getboolean(key, default)

        # Case 1: True
        self.set_config_value('TEST_BOOL', 'true')
        result = evolverstage.read_config('TEST_BOOL', 'bool')
        self.assertIs(result, True)

        # Case 2: False
        self.set_config_value('TEST_BOOL', 'false')
        result = evolverstage.read_config('TEST_BOOL', 'bool')
        self.assertIs(result, False)

    def test_read_int_list(self):
        self.set_config_value('TEST_INT_LIST', '1, 2, 3, 4')
        result = evolverstage.read_config('TEST_INT_LIST', 'int_list')
        self.assertEqual(result, [1, 2, 3, 4])

    def test_read_string_list(self):
        self.set_config_value('TEST_STR_LIST', 'foo, bar, baz')
        result = evolverstage.read_config('TEST_STR_LIST', 'string_list')
        self.assertEqual(result, ['foo', 'bar', 'baz'])

    def test_read_bool_list(self):
        self.set_config_value('TEST_BOOL_LIST', 'true, False, TRUE')
        result = evolverstage.read_config('TEST_BOOL_LIST', 'bool_list')
        self.assertEqual(result, [True, False, True])

    def test_default_value(self):
        # Ensure fallback is used when key is missing (get returns None/fallback)
        defaults = self.mock_config.__getitem__.return_value

        # Let's override get to simulate missing key
        defaults.get.side_effect = lambda k, fallback=None: fallback
        defaults.getboolean.side_effect = lambda k, default=None: default

        result = evolverstage.read_config('MISSING_KEY', 'int', default=100)
        self.assertEqual(result, 100)

    def test_empty_value(self):
        # read_config: if not value: return default
        self.set_config_value('EMPTY_KEY', '')
        result = evolverstage.read_config('EMPTY_KEY', 'int', default=99)
        self.assertEqual(result, 99)
