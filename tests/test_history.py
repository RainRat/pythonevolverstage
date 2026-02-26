import sys
import os
import unittest
from unittest import mock
import io
import json
import shutil

# Add the root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import evolverstage

class TestHistory(unittest.TestCase):
    def setUp(self):
        self.test_log = "battle_log_test.csv"
        self.old_log = evolverstage.BATTLE_LOG_FILE
        evolverstage.BATTLE_LOG_FILE = self.test_log

        # Create a dummy log file
        with open(self.test_log, 'w') as f:
            f.write("era,arena,winner,loser,score1,score2,bred_with\n")
            f.write("1,0,45,12,100,50,88\n")
            f.write("1,0,12,45,100,100,99\n") # Draw, 12 wins randomly
            f.write("1,0,77,45,200,150,11\n") # 45 loses

        self.test_arena_dir = "arena999"
        if os.path.exists(self.test_arena_dir):
            shutil.rmtree(self.test_arena_dir)
        os.makedirs(self.test_arena_dir)

    def tearDown(self):
        evolverstage.BATTLE_LOG_FILE = self.old_log
        if os.path.exists(self.test_log):
            os.remove(self.test_log)
        if os.path.exists(self.test_arena_dir):
            shutil.rmtree(self.test_arena_dir)

    @mock.patch('evolverstage._resolve_warrior_path')
    def test_run_history_json(self, mock_resolve):
        warrior_path = os.path.join(self.test_arena_dir, "45.red")
        with open(warrior_path, "w") as f:
            f.write("MOV 0, 1")
        mock_resolve.return_value = warrior_path

        # Capture stdout
        captured_output = io.StringIO()
        with mock.patch('sys.stdout', new=captured_output):
            evolverstage.run_history("45", 999, limit=10, json_output=True)

        results = json.loads(captured_output.getvalue())
        # The history matches by warrior_id and arena.
        # My dummy log has arena 0, but I'm passing arena 999.
        # Wait, if I pass arena 999, but the log has 0, it should find nothing unless it infers 0 from path.
        # run_history infers arena from path:
        # match = re.search(r'arena(\d+)', os.path.dirname(path))
        # if match: target_arena = int(match.group(1))
        # So it should find arena 999 matches.

        # Let's update dummy log to have arena 999
        with open(self.test_log, 'w') as f:
            f.write("era,arena,winner,loser,score1,score2,bred_with\n")
            f.write("1,999,45,12,100,50,88\n")
            f.write("1,999,12,45,100,100,99\n")
            f.write("1,999,77,45,200,150,11\n")

        captured_output = io.StringIO()
        with mock.patch('sys.stdout', new=captured_output):
            evolverstage.run_history("45", 999, limit=10, json_output=True)

        results = json.loads(captured_output.getvalue())
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]['winner'], '77') # Reversed order (newest first)
        self.assertEqual(results[1]['winner'], '12')
        self.assertEqual(results[2]['winner'], '45')

    @mock.patch('evolverstage._resolve_warrior_path')
    def test_run_history_text(self, mock_resolve):
        warrior_path = os.path.join(self.test_arena_dir, "45.red")
        with open(warrior_path, "w") as f:
            f.write("MOV 0, 1")
        mock_resolve.return_value = warrior_path

        with open(self.test_log, 'w') as f:
            f.write("era,arena,winner,loser,score1,score2,bred_with\n")
            f.write("1,999,45,12,100,50,88\n")
            f.write("1,999,12,45,100,100,99\n")
            f.write("1,999,77,45,200,150,11\n")

        captured_output = io.StringIO()
        with mock.patch('sys.stdout', new=captured_output):
            evolverstage.run_history("45", 999, limit=10, json_output=False)

        output = captured_output.getvalue()
        self.assertIn("Match History: Warrior #45 (Arena 999)", output)
        self.assertIn("WIN", output)
        self.assertIn("DRAW/L", output)
        self.assertIn("LOSS", output)
        self.assertIn("12", output)
        self.assertIn("77", output)

if __name__ == '__main__':
    unittest.main()
