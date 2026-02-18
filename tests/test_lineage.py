import unittest
from unittest.mock import patch, MagicMock
import os
import tempfile
import csv
import sys

# Import functions from evolverstage
# We mock settings.ini reading to avoid dependency on the actual file content during import
with patch('configparser.ConfigParser.read'):
    with patch('evolverstage.read_config', side_effect=lambda key, **kwargs: 0 if 'LAST_ARENA' in key else [] if 'LIST' in key else 1):
        import evolverstage

class TestLineage(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.log_file = os.path.join(self.test_dir.name, 'battle_log.csv')
        self.old_log = evolverstage.BATTLE_LOG_FILE
        evolverstage.BATTLE_LOG_FILE = self.log_file

        # Disable colors for easier matching
        self.old_colors = {
            'BOLD': evolverstage.Colors.BOLD,
            'HEADER': evolverstage.Colors.HEADER,
            'GREEN': evolverstage.Colors.GREEN,
            'CYAN': evolverstage.Colors.CYAN,
            'YELLOW': evolverstage.Colors.YELLOW,
            'ENDC': evolverstage.Colors.ENDC
        }
        evolverstage.Colors.BOLD = ""
        evolverstage.Colors.HEADER = ""
        evolverstage.Colors.GREEN = ""
        evolverstage.Colors.CYAN = ""
        evolverstage.Colors.YELLOW = ""
        evolverstage.Colors.ENDC = ""

    def tearDown(self):
        evolverstage.BATTLE_LOG_FILE = self.old_log
        evolverstage.Colors.BOLD = self.old_colors['BOLD']
        evolverstage.Colors.HEADER = self.old_colors['HEADER']
        evolverstage.Colors.GREEN = self.old_colors['GREEN']
        evolverstage.Colors.CYAN = self.old_colors['CYAN']
        evolverstage.Colors.YELLOW = self.old_colors['YELLOW']
        evolverstage.Colors.ENDC = self.old_colors['ENDC']
        self.test_dir.cleanup()

    def create_log(self, rows):
        with open(self.log_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['era', 'arena', 'winner', 'loser', 'score1', 'score2', 'bred_with'])
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def test_get_lineage_simple(self):
        # Warrior 5 born from 1 and 2
        self.create_log([
            {'era': '0', 'arena': '0', 'winner': '1', 'loser': '5', 'score1': '10', 'score2': '5', 'bred_with': '2'}
        ])

        lineage = evolverstage.get_lineage('5', 0)
        self.assertIsNotNone(lineage)
        self.assertEqual(lineage['warrior'], '5')
        self.assertEqual(lineage['era'], 1)
        self.assertEqual(len(lineage['parents']), 2)
        self.assertEqual(lineage['parents'][0]['warrior'], '1')
        self.assertTrue(lineage['parents'][0]['initial'])
        self.assertEqual(lineage['parents'][1]['warrior'], '2')
        self.assertTrue(lineage['parents'][1]['initial'])

    def test_get_lineage_nested(self):
        # Chronological log:
        # 1. 10+11 -> 1
        # 2. 1+2 -> 5
        self.create_log([
            {'era': '0', 'arena': '0', 'winner': '10', 'loser': '1', 'score1': '10', 'score2': '5', 'bred_with': '11'},
            {'era': '1', 'arena': '0', 'winner': '1', 'loser': '5', 'score1': '10', 'score2': '5', 'bred_with': '2'}
        ])

        lineage = evolverstage.get_lineage('5', 0)
        self.assertIsNotNone(lineage)
        self.assertEqual(lineage['warrior'], '5')
        p1 = lineage['parents'][0]
        self.assertEqual(p1['warrior'], '1')
        self.assertEqual(p1['era'], 1)
        self.assertEqual(p1['parents'][0]['warrior'], '10')
        self.assertTrue(p1['parents'][0]['initial'])

    def test_get_lineage_max_depth(self):
        # Deep lineage
        self.create_log([
            {'era': '0', 'arena': '0', 'winner': '10', 'loser': '9', 'score1': '1', 'score2': '0', 'bred_with': '11'},
            {'era': '1', 'arena': '0', 'winner': '9', 'loser': '8', 'score1': '1', 'score2': '0', 'bred_with': '12'},
            {'era': '2', 'arena': '0', 'winner': '8', 'loser': '7', 'score1': '1', 'score2': '0', 'bred_with': '13'}
        ])

        # depth 1: 7 -> 8, 13 (parents are None because depth limit reached)
        lineage = evolverstage.get_lineage('7', 0, max_depth=1)
        self.assertEqual(lineage['warrior'], '7')
        self.assertIsNone(lineage['parents'][0])
        self.assertIsNone(lineage['parents'][1])

        # depth 2: 7 -> 8 (born from 9,12), 13 (initial)
        lineage = evolverstage.get_lineage('7', 0, max_depth=2)
        self.assertIsNotNone(lineage['parents'][0])
        self.assertEqual(lineage['parents'][0]['warrior'], '8')
        # Parents of 8 are None because we reached depth 2 (7 is depth 0, 8 is depth 1)
        # Wait, if depth=2, 7 (0) -> 8 (1) -> 9 (2) is stopped.
        self.assertIsNone(lineage['parents'][0]['parents'][0])

    @patch('evolverstage._resolve_warrior_path')
    @patch('builtins.print')
    def test_run_lineage(self, mock_print, mock_resolve):
        mock_resolve.return_value = "arena0/5.red"
        self.create_log([
            {'era': '0', 'arena': '0', 'winner': '1', 'loser': '5', 'score1': '10', 'score2': '5', 'bred_with': '2'}
        ])

        evolverstage.run_lineage('5', 0)

        # Check if output contains expected keywords
        printed_text = "\n".join([call[0][0] for call in mock_print.call_args_list])
        self.assertIn("Lineage Tracer: Warrior 5", printed_text)
        self.assertIn("Warrior 5", printed_text)
        self.assertIn("Warrior 1", printed_text)
        self.assertIn("Warrior 2", printed_text)
        self.assertIn("(Born in Era 1)", printed_text)
        self.assertIn("(Initial Population / Unarchived)", printed_text)

if __name__ == '__main__':
    unittest.main()
