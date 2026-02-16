import sys
import os
import unittest
from unittest import mock

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestGetEvolutionStatus(unittest.TestCase):
    def setUp(self):
        self.mock_config = {
            'LAST_ARENA': 0,
            'CORESIZE_LIST': [8000],
            'CYCLES_LIST': [80000],
            'PROCESSES_LIST': [8000],
            'BATTLE_LOG_FILE': 'test_log.csv'
        }
        self.patcher = mock.patch.multiple(evolverstage, **self.mock_config)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    @mock.patch('evolverstage.get_recent_log_entries')
    @mock.patch('evolverstage.get_leaderboard')
    @mock.patch('os.path.exists')
    @mock.patch('os.listdir')
    def test_get_evolution_status_basic(self, mock_listdir, mock_exists, mock_leaderboard, mock_get_recent):
        """Test basic status gathering for a single arena."""
        mock_get_recent.return_value = [{'era': '1', 'arena': '0', 'winner': '5', 'loser': '10', 'score1': '150', 'score2': '50'}]
        mock_leaderboard.return_value = {0: [('5', 10)]}

        def exists_side_effect(path):
            if path == "arena0": return True
            if path == "archive": return False
            return False
        mock_exists.side_effect = exists_side_effect

        mock_listdir.return_value = ['1.red', '2.red']

        mock_file_content = "MOV.I $0, $1\nDAT.F $0, $0\n"
        with mock.patch('builtins.open', mock.mock_open(read_data=mock_file_content)):
            status = evolverstage.get_evolution_status()

        self.assertEqual(status['latest_log']['winner'], '5')
        self.assertEqual(len(status['arenas']), 1)
        arena0 = status['arenas'][0]
        self.assertEqual(arena0['id'], 0)
        self.assertTrue(arena0['exists'])
        self.assertEqual(arena0['population'], 2)
        self.assertEqual(arena0['champion'], '5')
        self.assertEqual(arena0['champion_wins'], 10)
        self.assertEqual(arena0['avg_length'], 2.0)
        self.assertFalse(status['archive']['exists'])

    @mock.patch('evolverstage.get_recent_log_entries')
    @mock.patch('evolverstage.get_leaderboard')
    @mock.patch('os.path.exists')
    def test_get_evolution_status_no_arena_dir(self, mock_exists, mock_leaderboard, mock_get_recent):
        """Test status when arena directory is missing."""
        mock_get_recent.return_value = []
        mock_leaderboard.return_value = {}
        mock_exists.return_value = False

        status = evolverstage.get_evolution_status()

        self.assertEqual(len(status['arenas']), 1)
        self.assertFalse(status['arenas'][0]['exists'])
        self.assertEqual(status['arenas'][0]['population'], 0)

    @mock.patch('evolverstage.get_recent_log_entries')
    @mock.patch('evolverstage.get_leaderboard')
    @mock.patch('os.path.exists')
    @mock.patch('os.listdir')
    def test_get_evolution_status_archive(self, mock_listdir, mock_exists, mock_leaderboard, mock_get_recent):
        """Test status when archive exists."""
        mock_get_recent.return_value = []
        mock_leaderboard.return_value = {}

        def exists_side_effect(path):
            if path == "archive": return True
            return False
        mock_exists.side_effect = exists_side_effect

        mock_listdir.return_value = ['arch1.red', 'arch2.red', 'other.txt']

        status = evolverstage.get_evolution_status()

        self.assertTrue(status['archive']['exists'])
        self.assertEqual(status['archive']['count'], 2)

if __name__ == '__main__':
    unittest.main()
