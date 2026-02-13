import sys
import os
import unittest
from unittest import mock

# Add the root directory to sys.path so we can import evolverstage
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestBattleLogic(unittest.TestCase):
    def test_parse_nmars_output_valid(self):
        """Test parsing of valid nmars output."""
        # Using format: ID Name Author scores Score
        # ensuring index 0 is ID and index 4 is Score
        raw_output = (
            "Header info\n"
            "1 Warrior1 Author scores 100\n"
            "2 Warrior2 Author scores 50\n"
            "Footer info"
        )
        scores, warriors = evolverstage.parse_nmars_output(raw_output)

        self.assertEqual(scores, [100, 50])
        self.assertEqual(warriors, [1, 2])

    def test_parse_nmars_output_none(self):
        """Test parsing None output."""
        scores, warriors = evolverstage.parse_nmars_output(None)
        self.assertEqual(scores, [])
        self.assertEqual(warriors, [])

    def test_parse_nmars_output_minimal(self):
        """Test parsing minimal output lines."""
        # Minimal format is now supported
        raw_output = (
            "1 scores 100\n"
            "2 Warrior2 Author scores 50"
        )
        scores, warriors = evolverstage.parse_nmars_output(raw_output)

        self.assertEqual(scores, [100, 50])
        self.assertEqual(warriors, [1, 2])

    def test_parse_nmars_output_with_spaces(self):
        """Test parsing lines with spaces in name/author."""
        raw_output = "1 My Warrior Author Name scores 100"
        scores, warriors = evolverstage.parse_nmars_output(raw_output)

        self.assertEqual(scores, [100])
        self.assertEqual(warriors, [1])

    def test_parse_nmars_output_actually_malformed(self):
        """Test parsing actually malformed lines."""
        # No score following "scores", or not a number
        raw_output = "1 scores\n2 scores not_a_number"
        scores, warriors = evolverstage.parse_nmars_output(raw_output)
        self.assertEqual(scores, [])
        self.assertEqual(warriors, [])

    def test_parse_nmars_output_no_scores_keyword(self):
        """Test lines without 'scores' keyword are ignored."""
        raw_output = "1 Warrior1 Author wins 100"
        scores, warriors = evolverstage.parse_nmars_output(raw_output)
        self.assertEqual(scores, [])
        self.assertEqual(warriors, [])

    def test_determine_winner_p2_wins(self):
        """Test player 2 (index 1) has higher score."""
        scores = [100, 200]
        warriors = [1, 2]
        winner, loser = evolverstage.determine_winner(scores, warriors)
        self.assertEqual(winner, 2)
        self.assertEqual(loser, 1)

    def test_determine_winner_p1_wins(self):
        """Test player 1 (index 0) has higher score."""
        scores = [200, 100]
        warriors = [1, 2]
        winner, loser = evolverstage.determine_winner(scores, warriors)
        self.assertEqual(winner, 1)
        self.assertEqual(loser, 2)

    @mock.patch('random.randint')
    def test_determine_winner_draw_pick_p2(self, mock_randint):
        """Test draw scenario where random picks player 2."""
        # random.randint(1, 2) returns 1 -> P2 wins (index 1 is winner, index 0 is loser)
        # Wait, let's check code:
        # if random.randint(1,2)==1: winner=warriors[1]...

        mock_randint.return_value = 1

        scores = [100, 100]
        warriors = [1, 2]
        winner, loser = evolverstage.determine_winner(scores, warriors)

        self.assertEqual(winner, 2)
        self.assertEqual(loser, 1)

    @mock.patch('random.randint')
    def test_determine_winner_draw_pick_p1(self, mock_randint):
        """Test draw scenario where random picks player 1."""
        # random.randint(1, 2) returns 2 -> P1 wins

        mock_randint.return_value = 2

        scores = [100, 100]
        warriors = [1, 2]
        winner, loser = evolverstage.determine_winner(scores, warriors)

        self.assertEqual(winner, 1)
        self.assertEqual(loser, 2)
