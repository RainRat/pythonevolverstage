import sys
import os
import unittest
from unittest import mock

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestSelectors(unittest.TestCase):

    @mock.patch('os.path.exists')
    def test_resolve_existing_file(self, mock_exists):
        mock_exists.return_value = True
        result = evolverstage._resolve_warrior_path("my_warrior.red", 0)
        self.assertEqual(result, "my_warrior.red")

    @mock.patch('os.path.exists')
    @mock.patch('os.listdir')
    @mock.patch('random.choice')
    def test_resolve_random(self, mock_choice, mock_listdir, mock_exists):
        mock_exists.side_effect = lambda p: p == "arena0"
        mock_listdir.return_value = ["1.red", "2.red", "not_red.txt"]
        mock_choice.return_value = "2.red"

        result = evolverstage._resolve_warrior_path("random", 0)

        self.assertEqual(result, os.path.join("arena0", "2.red"))
        mock_choice.assert_called_once_with(["1.red", "2.red"])

    @mock.patch('os.path.exists')
    @mock.patch('evolverstage.get_leaderboard')
    def test_resolve_top(self, mock_leaderboard, mock_exists):
        mock_exists.side_effect = lambda p: p == "arena0/42.red"
        mock_leaderboard.return_value = {0: [('42', 10), ('12', 5)]}

        result = evolverstage._resolve_warrior_path("top", 0)
        self.assertEqual(result, "arena0/42.red")

        mock_exists.side_effect = lambda p: p == "arena0/12.red"
        result = evolverstage._resolve_warrior_path("top2", 0)
        self.assertEqual(result, "arena0/12.red")

    @mock.patch('os.path.exists')
    @mock.patch('evolverstage.get_leaderboard')
    def test_resolve_top_no_data(self, mock_leaderboard, mock_exists):
        mock_exists.return_value = False
        mock_leaderboard.return_value = {}

        result = evolverstage._resolve_warrior_path("top", 0)
        self.assertEqual(result, "top")

    @mock.patch('os.path.exists')
    def test_resolve_unrecognized(self, mock_exists):
        mock_exists.return_value = False
        result = evolverstage._resolve_warrior_path("something_else", 0)
        self.assertEqual(result, "something_else")

    @mock.patch('os.path.exists')
    def test_resolve_numeric_to_arena_path(self, mock_exists):
        mock_exists.side_effect = lambda p: p == os.path.join("arena0", "1.red")

        result = evolverstage._resolve_warrior_path("1", 0)
        self.assertEqual(result, os.path.join("arena0", "1.red"))

    @mock.patch('os.path.exists')
    def test_resolve_numeric_with_arena_override_to_arena_path(self, mock_exists):
        mock_exists.side_effect = lambda p: p == os.path.join("arena5", "42.red")

        result = evolverstage._resolve_warrior_path("42@5", 0)
        self.assertEqual(result, os.path.join("arena5", "42.red"))

    @mock.patch('os.path.exists')
    @mock.patch('evolverstage.get_leaderboard')
    def test_resolve_top_with_arena_override_suffix(self, mock_leaderboard, mock_exists):
        mock_leaderboard.return_value = {5: [('99', 20)]}
        mock_exists.side_effect = lambda p: p == "arena5/99.red"

        result = evolverstage._resolve_warrior_path("top@5", 0)
        self.assertEqual(result, "arena5/99.red")
        mock_leaderboard.assert_called_with(arena_idx=5, limit=1)

    @mock.patch('os.path.exists')
    @mock.patch('os.listdir')
    @mock.patch('random.choice')
    def test_resolve_random_with_arena_override_suffix(self, mock_choice, mock_listdir, mock_exists):
        mock_exists.side_effect = lambda p: p == "arena2"
        mock_listdir.return_value = ["w1.red"]
        mock_choice.return_value = "w1.red"

        result = evolverstage._resolve_warrior_path("random@2", 0)
        self.assertEqual(result, os.path.join("arena2", "w1.red"))
        mock_listdir.assert_called_once_with("arena2")

if __name__ == '__main__':
    unittest.main()
