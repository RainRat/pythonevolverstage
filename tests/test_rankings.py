import sys
import os
import unittest
import csv
import tempfile
import shutil
from unittest import mock
import io

# Add the root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestRankings(unittest.TestCase):
    def setUp(self):
        # Temp dir for arenas
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

        # Temp log file
        self.test_log = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.csv')
        self.log_path = self.test_log.name
        self.original_log_file = evolverstage.BATTLE_LOG_FILE
        evolverstage.BATTLE_LOG_FILE = self.log_path

        # Write header
        writer = csv.DictWriter(self.test_log, fieldnames=['era', 'arena', 'winner', 'loser', 'score1', 'score2', 'bred_with'])
        writer.writeheader()
        self.writer = writer
        self.test_log.flush()

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)
        evolverstage.BATTLE_LOG_FILE = self.original_log_file
        if os.path.exists(self.log_path):
            os.remove(self.log_path)

    def test_run_rankings_per_arena(self):
        """Test run_rankings output for a specific arena."""
        self.writer.writerow({'era': '0', 'arena': '0', 'winner': '1', 'loser': '2', 'score1': '100', 'score2': '0', 'bred_with': ''})
        self.test_log.flush()

        os.makedirs("arena0", exist_ok=True)
        with open("arena0/1.red", "w") as f:
            f.write("MOV.I $0,$1\n")
        with open("arena0/2.red", "w") as f:
            f.write("DAT.F $0,$0\n")

        with mock.patch('sys.stdout', new=io.StringIO()) as fake_out:
            evolverstage.run_rankings(arena_idx=0, min_battles=1)
            output = fake_out.getvalue()
            self.assertIn("LIFETIME RANKINGS: Arena 0", output)
            self.assertIn(" 1.  1 ", output) # Rank 1, Warrior 1

    def test_run_rankings_global(self):
        """Test run_rankings output for global view."""
        self.writer.writerow({'era': '0', 'arena': '0', 'winner': '1', 'loser': '2', 'score1': '100', 'score2': '0', 'bred_with': ''})
        self.writer.writerow({'era': '0', 'arena': '1', 'winner': '10', 'loser': '11', 'score1': '100', 'score2': '0', 'bred_with': ''})
        self.test_log.flush()

        os.makedirs("arena0", exist_ok=True)
        os.makedirs("arena1", exist_ok=True)
        with open("arena0/1.red", "w") as f: f.write("MOV.I $0,$1\n")
        with open("arena1/10.red", "w") as f: f.write("MOV.I $0,$1\n")

        with mock.patch('sys.stdout', new=io.StringIO()) as fake_out:
            evolverstage.run_rankings(arena_idx=None, min_battles=1)
            output = fake_out.getvalue()
            self.assertIn("GLOBAL LIFETIME RANKINGS", output)
            self.assertIn("Arena", output)
            self.assertIn(" 0      1 ", output) # Arena 0, Warrior 1
            self.assertIn(" 1      10 ", output) # Arena 1, Warrior 10

    def test_rank_selector(self):
        """Test rankN selector resolution."""
        self.writer.writerow({'era': '0', 'arena': '0', 'winner': '42', 'loser': '1', 'score1': '100', 'score2': '0', 'bred_with': ''})
        self.test_log.flush()

        os.makedirs("arena0", exist_ok=True)
        path = os.path.abspath("arena0/42.red")
        with open(path, "w") as f:
            f.write("MOV.I $0,$1\n")

        # Resolve rank1@0
        resolved = evolverstage._resolve_warrior_path("rank1@0", arena_idx=0)
        self.assertEqual(os.path.abspath(resolved), path)

        # Resolve rank1 without @ but with default arena 0
        resolved = evolverstage._resolve_warrior_path("rank1", arena_idx=0)
        self.assertEqual(os.path.abspath(resolved), path)

    def test_run_rankings_json(self):
        """Test run_rankings JSON output."""
        self.writer.writerow({'era': '0', 'arena': '0', 'winner': '1', 'loser': '2', 'score1': '100', 'score2': '0', 'bred_with': ''})
        self.test_log.flush()

        with mock.patch('sys.stdout', new=io.StringIO()) as fake_out:
            evolverstage.run_rankings(arena_idx=0, min_battles=1, json_output=True)
            import json
            data = json.loads(fake_out.getvalue())
            self.assertIn("0", data)
            self.assertEqual(data["0"][0][0], "1")

if __name__ == '__main__':
    unittest.main()
