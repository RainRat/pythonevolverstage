import unittest
import os
import sys
import csv
import tempfile
import shutil

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage
from evolver.logger import DataLogger, BaseCSVLogger

class TestDataLogger(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.test_dir, "test_log.csv")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_init(self):
        """Test DataLogger initialization."""
        logger = DataLogger(self.log_file)
        self.assertEqual(logger.filename, self.log_file)
        self.assertEqual(logger.fieldnames, ['era', 'arena', 'winner', 'loser', 'score1', 'score2', 'bred_with'])

    def test_base_csv_logger_init(self):
        """Test BaseCSVLogger initialization."""
        fields = ['a', 'b']
        logger = BaseCSVLogger(self.log_file, fields)
        self.assertEqual(logger.filename, self.log_file)
        self.assertEqual(logger.fieldnames, fields)

    def test_log_data_creates_new_file(self):
        """Test that log_data creates a new file with header if it doesn't exist."""
        logger = DataLogger(self.log_file)
        data = {
            'era': 1,
            'arena': 0,
            'winner': 10,
            'loser': 5,
            'score1': 100,
            'score2': 50,
            'bred_with': 'random'
        }
        logger.log_data(**data)

        self.assertTrue(os.path.exists(self.log_file))
        with open(self.log_file, 'r', newline='') as f:
            reader = csv.DictReader(f)
            self.assertEqual(reader.fieldnames, logger.fieldnames)
            rows = list(reader)
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(int(row['era']), 1)
            self.assertEqual(int(row['arena']), 0)
            self.assertEqual(int(row['winner']), 10)
            self.assertEqual(int(row['loser']), 5)
            self.assertEqual(int(row['score1']), 100)
            self.assertEqual(int(row['score2']), 50)
            self.assertEqual(row['bred_with'], 'random')

    def test_log_data_appends_to_existing_file(self):
        """Test that log_data appends to an existing file without rewriting header."""
        # Create file with header and one row manually or via logger
        logger = DataLogger(self.log_file)
        data1 = {
            'era': 1,
            'arena': 0,
            'winner': 10,
            'loser': 5,
            'score1': 100,
            'score2': 50,
            'bred_with': 'random1'
        }
        logger.log_data(**data1)

        data2 = {
            'era': 2,
            'arena': 1,
            'winner': 20,
            'loser': 15,
            'score1': 200,
            'score2': 150,
            'bred_with': 'random2'
        }
        logger.log_data(**data2)

        with open(self.log_file, 'r', newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]['bred_with'], 'random1')
            self.assertEqual(rows[1]['bred_with'], 'random2')

            # Verify header didn't get written again in the middle
            f.seek(0)
            content = f.read()
            # Count occurrences of a field name to ensure header appears only once
            self.assertEqual(content.count('bred_with'), 1)

    def test_log_data_no_filename(self):
        """Test that log_data does nothing if filename is None or empty."""
        logger = DataLogger(None)
        # Should not raise error
        logger.log_data(era=1)

        logger = DataLogger("")
        logger.log_data(era=1)

    def test_log_data_missing_fields(self):
        """Test log_data with missing fields (should be empty strings or similar in CSV)."""
        logger = DataLogger(self.log_file)
        # Missing 'score2'
        data = {
            'era': 1,
            'arena': 0,
            'winner': 10,
            'loser': 5,
            'score1': 100,
            # score2 missing
            'bred_with': 'random'
        }
        # csv.DictWriter defaults to raising ValueError if extrasaction='raise' (default),
        # but what about missing keys? restval defaults to empty string.
        # Let's verify behavior.

        logger.log_data(**data)

        with open(self.log_file, 'r', newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            # csv.DictWriter behavior on missing keys depends on 'restval' arg, default is ""
            # But let's check what DataLogger actually does.
            # Assuming it uses default DictWriter.
            self.assertEqual(rows[0]['score2'], '')

    def test_log_data_extra_fields(self):
        """Test log_data with extra fields (should raise ValueError by default)."""
        logger = DataLogger(self.log_file)
        data = {
            'era': 1,
            'extra_field': 'oops'
        }
        with self.assertRaises(ValueError):
            logger.log_data(**data)

if __name__ == '__main__':
    unittest.main()
