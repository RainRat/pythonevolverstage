import os
import sys
import csv
import pytest

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage
from evolver.logger import DataLogger, BaseCSVLogger

class TestDataLogger:
    @pytest.fixture
    def log_file(self, tmp_path):
        """Fixture to provide a path to a log file in a temporary directory."""
        return tmp_path / "test_log.csv"

    def test_init(self, log_file):
        """Test DataLogger initialization."""
        logger = DataLogger(str(log_file))
        assert logger.filename == str(log_file)
        assert logger.fieldnames == ['era', 'arena', 'winner', 'loser', 'score1', 'score2', 'bred_with']

    def test_base_csv_logger_init(self, log_file):
        """Test BaseCSVLogger initialization."""
        fields = ['a', 'b']
        logger = BaseCSVLogger(str(log_file), fields)
        assert logger.filename == str(log_file)
        assert logger.fieldnames == fields

    def test_log_data_creates_new_file(self, log_file):
        """Test that log_data creates a new file with header if it doesn't exist."""
        logger = DataLogger(str(log_file))
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

        assert log_file.exists()
        with open(log_file, 'r', newline='') as f:
            reader = csv.DictReader(f)
            assert reader.fieldnames == logger.fieldnames
            rows = list(reader)
            assert len(rows) == 1
            row = rows[0]
            assert int(row['era']) == 1
            assert int(row['arena']) == 0
            assert int(row['winner']) == 10
            assert int(row['loser']) == 5
            assert int(row['score1']) == 100
            assert int(row['score2']) == 50
            assert row['bred_with'] == 'random'

    def test_log_data_appends_to_existing_file(self, log_file):
        """Test that log_data appends to an existing file without rewriting header."""
        # Create file with header and one row manually or via logger
        logger = DataLogger(str(log_file))
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

        with open(log_file, 'r', newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 2
            assert rows[0]['bred_with'] == 'random1'
            assert rows[1]['bred_with'] == 'random2'

            # Verify header didn't get written again in the middle
            f.seek(0)
            content = f.read()
            # Count occurrences of a field name to ensure header appears only once
            assert content.count('bred_with') == 1
            # (once in header. data values are distinct)

    def test_log_data_no_filename(self):
        """Test that log_data does nothing if filename is None or empty."""
        logger = DataLogger(None)
        # Should not raise error
        logger.log_data(era=1)

        logger = DataLogger("")
        logger.log_data(era=1)

    def test_log_data_missing_fields(self, log_file):
        """Test log_data with missing fields (should be empty strings or similar in CSV)."""
        logger = DataLogger(str(log_file))
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

        with open(log_file, 'r', newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert rows[0]['score2'] == ''

    def test_log_data_extra_fields(self, log_file):
        """Test log_data with extra fields (should raise ValueError by default)."""
        logger = DataLogger(str(log_file))
        data = {
            'era': 1,
            'extra_field': 'oops'
        }
        with pytest.raises(ValueError):
            logger.log_data(**data)
