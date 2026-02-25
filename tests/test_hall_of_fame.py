import sys
import os
import unittest
import csv
import tempfile
import io
from unittest import mock

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestHallOfFame(unittest.TestCase):
    def setUp(self):
        # Use a temporary file for the log
        self.test_log = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.csv')
        self.log_path = self.test_log.name
        self.original_log_file = evolverstage.BATTLE_LOG_FILE
        evolverstage.BATTLE_LOG_FILE = self.log_path

        # Write header
        writer = csv.DictWriter(self.test_log, fieldnames=['era', 'arena', 'winner', 'loser', 'score1', 'score2', 'bred_with'])
        writer.writeheader()
        self.writer = writer

        # Populate log with some history
        # Arena 0: 1 beats 2 twice (Win rate 100% for 1, 2 battles)
        self.writer.writerow({'era': '0', 'arena': '0', 'winner': '1', 'loser': '2', 'score1': '100', 'score2': '0', 'bred_with': '3'})
        self.writer.writerow({'era': '0', 'arena': '0', 'winner': '1', 'loser': '2', 'score1': '100', 'score2': '0', 'bred_with': '3'})
        # Arena 0: 4 beats 5 once (Win rate 100% for 4, 1 battle)
        self.writer.writerow({'era': '0', 'arena': '0', 'winner': '4', 'loser': '5', 'score1': '100', 'score2': '0', 'bred_with': '6'})

        self.test_log.flush()

    def tearDown(self):
        # Restore original log file path and remove temporary file
        evolverstage.BATTLE_LOG_FILE = self.original_log_file
        if os.path.exists(self.log_path):
            os.remove(self.log_path)

    @mock.patch('evolverstage.analyze_warrior')
    @mock.patch('evolverstage.identify_strategy')
    @mock.patch('evolverstage._resolve_warrior_path')
    @mock.patch('os.path.exists')
    def test_run_hall_of_fame_basic(self, mock_exists, mock_resolve, mock_identify, mock_analyze):
        """Test that Hall of Fame correctly categorizes and picks best win rates."""
        mock_exists.return_value = True
        mock_resolve.side_effect = lambda wid, a: f"arena{a}/{wid}.red"

        # Mock strategies: 1 is Paper, 4 is Stone
        def side_effect_identify(stats):
            if "1.red" in stats.get('file', ''): return "Paper"
            if "4.red" in stats.get('file', ''): return "Stone"
            return "Experimental"

        mock_identify.side_effect = side_effect_identify
        mock_analyze.side_effect = lambda path: {'file': path}

        # Capture output
        with mock.patch('sys.stdout', new=io.StringIO()) as fake_out:
            evolverstage.run_hall_of_fame()
            output = fake_out.getvalue()

        self.assertIn("STRATEGIC HALL OF FAME", output)
        self.assertIn("Paper", output)
        self.assertIn("#1", output)
        self.assertIn("Stone", output)
        self.assertIn("#4", output)
        self.assertIn("100.0%", output)

    @mock.patch('evolverstage.analyze_warrior')
    @mock.patch('evolverstage.identify_strategy')
    @mock.patch('evolverstage._resolve_warrior_path')
    @mock.patch('os.path.exists')
    def test_run_hall_of_fame_json(self, mock_exists, mock_resolve, mock_identify, mock_analyze):
        """Test JSON output format and tiebreaking logic."""
        mock_exists.return_value = True
        mock_resolve.side_effect = lambda wid, a: f"arena{a}/{wid}.red"
        mock_identify.return_value = "TestStrategy"
        mock_analyze.return_value = {}

        import json
        with mock.patch('sys.stdout', new=io.StringIO()) as fake_out:
            evolverstage.run_hall_of_fame(json_output=True)
            output = fake_out.getvalue()
            data = json.loads(output)

        self.assertIn("TestStrategy", data)
        # Warrior 1 should be the champion for TestStrategy (more battles than 4)
        self.assertEqual(data["TestStrategy"]["warrior_id"], "1")
        self.assertEqual(data["TestStrategy"]["rate"], 100.0)
        self.assertEqual(data["TestStrategy"]["battles"], 2)

if __name__ == '__main__':
    unittest.main()
