import os
import sys
import csv
import unittest
import tempfile
import shutil

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from evolver.logger import DataLogger, BaseCSVLogger

class TestDataLogger(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for test logs
        self.test_dir = tempfile.mkdtemp()
        self.log_file_path = os.path.join(self.test_dir, "test_log.csv")

    def tearDown(self):
        # Remove the temporary directory
        shutil.rmtree(self.test_dir)

    def test_init(self):
        """Test DataLogger initialization."""
        logger = DataLogger(self.log_file_path)
        self.assertEqual(logger.filename, self.log_file_path)
        self.assertEqual(logger.fieldnames, ['era', 'arena', 'winner', 'loser', 'score1', 'score2', 'bred_with'])

    def test_base_csv_logger_init(self):
        """Test BaseCSVLogger initialization."""
        fields = ['a', 'b']
        logger = BaseCSVLogger(self.log_file_path, fields)
        self.assertEqual(logger.filename, self.log_file_path)
        self.assertEqual(logger.fieldnames, fields)

    def test_log_row_creates_new_file(self):
        """Test that log_row creates a new file with header if it doesn't exist."""
        logger = DataLogger(self.log_file_path)
        data = {
            'era': 1,
            'arena': 0,
            'winner': 10,
            'loser': 5,
            'score1': 100,
            'score2': 50,
            'bred_with': 'random'
        }
        logger.log_row(**data)

        self.assertTrue(os.path.exists(self.log_file_path))
        with open(self.log_file_path, 'r', newline='') as f:
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

    def test_log_row_appends_to_existing_file(self):
        """Test that log_row appends to an existing file without rewriting header."""
        logger = DataLogger(self.log_file_path)
        data1 = {
            'era': 1,
            'arena': 0,
            'winner': 10,
            'loser': 5,
            'score1': 100,
            'score2': 50,
            'bred_with': 'random1'
        }
        logger.log_row(**data1)

        data2 = {
            'era': 2,
            'arena': 1,
            'winner': 20,
            'loser': 15,
            'score1': 200,
            'score2': 150,
            'bred_with': 'random2'
        }
        logger.log_row(**data2)

        with open(self.log_file_path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]['bred_with'], 'random1')
            self.assertEqual(rows[1]['bred_with'], 'random2')

            # Verify header didn't get written again in the middle
            f.seek(0)
            content = f.read()
            self.assertEqual(content.count('bred_with'), 1)

    def test_log_row_no_filename(self):
        """Test that log_row does nothing if filename is None or empty."""
        logger = DataLogger(None)
        # Should not raise error
        logger.log_row(era=1)

        logger = DataLogger("")
        logger.log_row(era=1)

    def test_log_row_missing_fields(self):
        """Test log_row with missing fields (should be empty strings or similar in CSV)."""
        logger = DataLogger(self.log_file_path)
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
        logger.log_row(**data)

        with open(self.log_file_path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            self.assertEqual(rows[0]['score2'], '')

    def test_log_row_extra_fields(self):
        """Test log_row with extra fields (should be ignored gracefully)."""
        logger = DataLogger(self.log_file_path)
        data = {
            'era': 1,
            'arena': 0,
            'winner': 10,
            'loser': 5,
            'score1': 100,
            'score2': 50,
            'bred_with': 'random',
            'extra_field': 'oops'
        }
        # Should NOT raise ValueError
        logger.log_row(**data)

        self.assertTrue(os.path.exists(self.log_file_path))
        with open(self.log_file_path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            self.assertEqual(len(rows), 1)
            self.assertNotIn('extra_field', rows[0])
            self.assertEqual(int(rows[0]['era']), 1)

if __name__ == '__main__':
    unittest.main()
