import csv
import os

class BaseCSVLogger:
    """
    Base class for logging data to CSV files.
    """
    def __init__(self, filename, fieldnames):
        self.filename = filename
        self.fieldnames = fieldnames

    def log_row(self, **row):
        """
        Writes a single row of data to the CSV file.
        Creates the file with a header row if it doesn't exist.
        """
        if self.filename:
            # Use extrasaction='ignore' to handle extra fields gracefully.
            with open(self.filename, 'a', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=self.fieldnames, extrasaction='ignore')
                if file.tell() == 0:
                    writer.writeheader()
                writer.writerow(row)

class DataLogger(BaseCSVLogger):
    """
    Logs battle results to a CSV file.
    """
    def __init__(self, filename):
        super().__init__(filename, ['era', 'arena', 'winner', 'loser', 'score1', 'score2', 'bred_with'])
